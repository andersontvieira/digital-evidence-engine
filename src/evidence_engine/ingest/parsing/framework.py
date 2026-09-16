"""Small parser contracts, strict JSON decoding and deterministic locators."""

import json
from dataclasses import dataclass, field
from typing import Protocol, cast

type JSONValue = None | bool | int | float | str | list[JSONValue] | dict[str, JSONValue]

MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_RECORDS = 100_000


class ParseError(Exception):
    """Only fixed technical codes, never source values or decoder error messages."""


@dataclass(frozen=True)
class ParserContext:
    relative_path: str


@dataclass(frozen=True)
class Diagnostic:
    code: str
    source_locator: str


@dataclass(frozen=True)
class ExtractedRecord:
    record_type: str
    source_locator: str
    record_index: int | None
    timestamp_raw: JSONValue
    payload: dict[str, JSONValue]
    annotations: list[dict[str, JSONValue]] = field(default_factory=list)


@dataclass(frozen=True)
class ParserResult:
    records: list[ExtractedRecord]
    warnings: list[Diagnostic]


class Parser(Protocol):
    @property
    def parser_id(self) -> str: ...

    @property
    def parser_version(self) -> str: ...

    def matches_path(self, context: ParserContext) -> bool: ...

    def supports(self, context: ParserContext, document: JSONValue) -> bool: ...

    def parse(self, context: ParserContext, document: JSONValue) -> ParserResult: ...


def child_locator(parent: str, key: str | int) -> str:
    """'$' followed by JSON Pointer tokens; slash and tilde are escaped reversibly."""
    return parent + "/" + str(key).replace("~", "~0").replace("/", "~1")


def json_text(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")
    )


def resolve_locator(document: JSONValue, locator: str) -> JSONValue:
    if locator == "$":
        return document
    if not locator.startswith("$/"):
        raise ParseError("INVALID_SOURCE_LOCATOR")
    value = document
    for encoded in locator[2:].split("/"):
        key = encoded.replace("~1", "/").replace("~0", "~")
        if child_locator("$", key)[2:] != encoded:
            raise ParseError("INVALID_SOURCE_LOCATOR")
        if isinstance(value, dict) and key in value:
            value = value[key]
        elif isinstance(value, list) and key.isascii() and key.isdecimal() and str(int(key)) == key:
            if int(key) >= len(value):
                raise ParseError("INVALID_SOURCE_LOCATOR")
            value = value[int(key)]
        else:
            raise ParseError("INVALID_SOURCE_LOCATOR")
    return value


def strict_json(data: bytes) -> JSONValue:
    def pairs(items: list[tuple[str, JSONValue]]) -> dict[str, JSONValue]:
        result: dict[str, JSONValue] = {}
        for key, value in items:
            if key in result:
                raise ParseError("JSON_DUPLICATE_KEY")
            result[key] = value
        return result

    def constant(value: str) -> None:
        raise ParseError("JSON_NONFINITE_NUMBER")

    try:
        document = cast(
            JSONValue,
            json.loads(data.decode("utf-8-sig"), object_pairs_hook=pairs, parse_constant=constant),
        )
        # Includes overflowed numbers such as 1e999 and bounds nested traversal.
        json_text(document)

        def depth(value: JSONValue, level: int = 0) -> None:
            if level > 64:
                raise ParseError("JSON_DEPTH_LIMIT")
            if isinstance(value, dict):
                for item in value.values():
                    depth(item, level + 1)
            elif isinstance(value, list):
                for item in value:
                    depth(item, level + 1)

        depth(document)
        return document
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ParseError("INVALID_JSON") from error
