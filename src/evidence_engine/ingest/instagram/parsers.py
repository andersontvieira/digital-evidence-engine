"""Extract only explicit values from documented path/schema combinations."""

import ipaddress
import re
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath

from evidence_engine.ingest.parsing.framework import (
    MAX_RECORDS,
    Diagnostic,
    ExtractedRecord,
    JSONValue,
    ParseError,
    Parser,
    ParserContext,
    ParserResult,
    child_locator,
)

PROFILE_FIELDS = {
    "timestamp",
    "timestamp_ms",
    "action",
    "event",
    "event_type",
    "ip",
    "ip_address",
    "port",
    "application",
    "service",
    "user_agent",
    "device_id",
    "device_identifier",
    "profile_field",
    "previous_value",
    "new_value",
    "location",
    "title",
    "string_map_data",
}
DELETED_FIELDS = {
    "timestamp",
    "creation_timestamp",
    "published",
    "is_published",
    "caption",
    "text",
    "device_id",
    "id",
    "media_id",
    "uri",
    "media_uri",
    "media_type",
    "media",
    "title",
    "string_map_data",
    "ip",
    "ip_address",
    "model",
}
MESSAGE_FIELDS = {
    "sender_name",
    "timestamp_ms",
    "timestamp",
    "content",
    "photos",
    "videos",
    "audio_files",
    "files",
    "gifs",
    "sticker",
    "share",
    "reactions",
    "is_geoblocked_for_viewer",
    "is_unsent",
    "type",
    "call_duration",
    "ip",
    "ip_address",
}
CONVERSATION_FIELDS = {
    "title",
    "participants",
    "thread_path",
    "messages",
    "is_still_participant",
    "magic_words",
    "image",
    "joinable_mode",
}
TIMESTAMP_FIELDS = {"timestamp", "timestamp_ms", "creation_timestamp"}


def canonical_source_path(context: ParserContext) -> bool:
    path = context.relative_path
    return (
        bool(path)
        and "\\" not in path
        and not PureWindowsPath(path).drive
        and all(part not in {"", ".", ".."} for part in path.split("/"))
    )


def field_name(name: str) -> str:
    return name.lower().replace(" ", "_")


def observe(
    record: dict[str, JSONValue], locator: str, expected: set[str], *, user_agent: bool = False
) -> tuple[JSONValue, list[dict[str, JSONValue]], list[Diagnostic]]:
    warnings: list[Diagnostic] = []
    annotations: list[dict[str, JSONValue]] = []
    timestamps: list[JSONValue] = []

    def scalar(name: str, value: JSONValue, path: str) -> None:
        if name in TIMESTAMP_FIELDS or name in {"time", "date"}:
            if value is not None:
                if isinstance(value, (dict, list, bool)):
                    warnings.append(Diagnostic("TIMESTAMP_UNRECOGNIZED", path))
                else:
                    timestamps.append(value)
                    # No conversion or guessed units/timezone in this milestone.
                    if isinstance(value, str):
                        warnings.append(Diagnostic("TIMESTAMP_RAW_ONLY", path))
        if name in {"ip", "ip_address"} and value is not None:
            try:
                if not isinstance(value, str):
                    raise ValueError
                address = ipaddress.ip_address(value)
                annotations.append(
                    {"kind": "ip_syntax", "source_locator": path, "version": address.version}
                )
            except ValueError:
                warnings.append(Diagnostic("INVALID_IP_SYNTAX", path))
        if user_agent and name == "user_agent" and isinstance(value, str):
            for code in sorted(set(re.findall(r"\biPhone[0-9]+,[0-9]+\b", value))):
                annotations.append(
                    {"kind": "model_code_from_user_agent", "source_locator": path, "value": code}
                )

    for name, value in record.items():
        path = child_locator(locator, name)
        if name not in expected:
            warnings.append(Diagnostic("UNEXPECTED_FIELD", path))
        scalar(field_name(name), value, path)
        if name == "string_map_data":
            if not isinstance(value, dict):
                raise ParseError("INVALID_STRING_MAP")
            for label, item in value.items():
                item_path = child_locator(path, label)
                if not isinstance(item, dict):
                    raise ParseError("INVALID_STRING_MAP_ENTRY")
                if "value" in item:
                    scalar(field_name(label), item["value"], child_locator(item_path, "value"))
                for key, nested in item.items():
                    if key in TIMESTAMP_FIELDS:
                        scalar(key, nested, child_locator(item_path, key))
                    elif key not in {"value", "href"}:
                        warnings.append(
                            Diagnostic("UNKNOWN_OPTIONAL_FIELD", child_locator(item_path, key))
                        )
    if len(timestamps) > 1:
        warnings.append(Diagnostic("MULTIPLE_TIMESTAMPS_RAW_ONLY", locator))
    timestamp = timestamps[0] if len(timestamps) == 1 else None
    return timestamp, annotations, warnings


@dataclass(frozen=True)
class MetaListParser:
    parser_id: str
    filename: str
    collection: str
    record_type: str
    expected_fields: frozenset[str]
    parser_version: str = "1.0.0"

    def matches_path(self, context: ParserContext) -> bool:
        return (
            canonical_source_path(context)
            and PurePosixPath(context.relative_path).name == self.filename
        )

    def supports(self, context: ParserContext, document: JSONValue) -> bool:
        return (
            self.matches_path(context)
            and isinstance(document, dict)
            and isinstance(document.get(self.collection), list)
        )

    def parse(self, context: ParserContext, document: JSONValue) -> ParserResult:
        if not self.supports(context, document) or not isinstance(document, dict):
            raise ParseError("UNSUPPORTED_SCHEMA")
        items = document[self.collection]
        assert isinstance(items, list)
        if len(items) > MAX_RECORDS:
            raise ParseError("RECORD_LIMIT")
        warnings = [
            Diagnostic("UNEXPECTED_TOP_LEVEL_FIELD", child_locator("$", name))
            for name in document
            if name != self.collection
        ]
        records: list[ExtractedRecord] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict) or not (set(item) & self.expected_fields):
                raise ParseError("INVALID_RECORD_SHAPE")
            locator = child_locator(child_locator("$", self.collection), index)
            timestamp, annotations, diagnostics = observe(
                item,
                locator,
                set(self.expected_fields),
                user_agent=self.parser_id == "meta.profile_activity",
            )
            for key in ("media",):
                if key in item and not isinstance(item[key], list):
                    diagnostics.append(
                        Diagnostic("UNKNOWN_OPTIONAL_STRUCTURE", child_locator(locator, key))
                    )
            records.append(
                ExtractedRecord(self.record_type, locator, index, timestamp, item, annotations)
            )
            warnings.extend(diagnostics)
        return ParserResult(records, warnings)


@dataclass(frozen=True)
class InstagramMessagesParser:
    parser_id: str = "meta.instagram_messages"
    parser_version: str = "1.0.0"

    def matches_path(self, context: ParserContext) -> bool:
        return (
            canonical_source_path(context)
            and re.fullmatch(
                r"(?:[^/]+/)*messages/inbox/(?:[^/]+/)+message_[0-9]+\.json", context.relative_path
            )
            is not None
        )

    def supports(self, context: ParserContext, document: JSONValue) -> bool:
        return (
            self.matches_path(context)
            and isinstance(document, dict)
            and isinstance(document.get("messages"), list)
            and (
                isinstance(document.get("title"), str)
                or isinstance(document.get("participants"), list)
            )
        )

    def parse(self, context: ParserContext, document: JSONValue) -> ParserResult:
        if not self.supports(context, document) or not isinstance(document, dict):
            raise ParseError("UNSUPPORTED_SCHEMA")
        messages = document["messages"]
        assert isinstance(messages, list)
        if len(messages) + 1 > MAX_RECORDS:
            raise ParseError("RECORD_LIMIT")
        warnings: list[Diagnostic] = []
        conversation = {key: value for key, value in document.items() if key != "messages"}
        for key in conversation:
            if key not in CONVERSATION_FIELDS:
                warnings.append(Diagnostic("UNEXPECTED_FIELD", child_locator("$", key)))
        participants = document.get("participants")
        if participants is not None and (
            not isinstance(participants, list)
            or any(
                not isinstance(person, dict) or not isinstance(person.get("name"), str)
                for person in participants
            )
        ):
            warnings.append(Diagnostic("UNKNOWN_PARTICIPANTS_STRUCTURE", "$/participants"))
        thread = document.get("thread_path")
        if isinstance(thread, str):
            # Compare the declared path, never turn the directory name into a recipient.
            actual = PurePosixPath(context.relative_path).parent.as_posix()
            if actual != thread and not actual.endswith("/" + thread):
                warnings.append(Diagnostic("THREAD_PATH_MISMATCH", "$/thread_path"))
        elif thread is not None:
            warnings.append(Diagnostic("UNKNOWN_OPTIONAL_STRUCTURE", "$/thread_path"))
        records = [ExtractedRecord("instagram_conversation", "$", None, None, conversation)]
        for index, item in enumerate(messages):
            if not isinstance(item, dict) or not (set(item) & MESSAGE_FIELDS):
                raise ParseError("INVALID_MESSAGE_SHAPE")
            locator = child_locator("$/messages", index)
            timestamp, annotations, diagnostics = observe(item, locator, MESSAGE_FIELDS)
            for key in ("photos", "videos", "audio_files", "files", "gifs", "reactions"):
                if key in item and not isinstance(item[key], list):
                    diagnostics.append(
                        Diagnostic("UNKNOWN_OPTIONAL_STRUCTURE", child_locator(locator, key))
                    )
            records.append(
                ExtractedRecord("instagram_message", locator, index, timestamp, item, annotations)
            )
            warnings.extend(diagnostics)
        return ParserResult(records, warnings)


PARSERS: tuple[Parser, ...] = (
    MetaListParser(
        "meta.profile_activity",
        "profile_activity.json",
        "profile_account_insights",
        "profile_activity",
        frozenset(PROFILE_FIELDS),
    ),
    MetaListParser(
        "meta.recently_deleted_content",
        "recently_deleted_content.json",
        "recently_deleted_media",
        "recently_deleted_content",
        frozenset(DELETED_FIELDS),
    ),
    InstagramMessagesParser(),
)
