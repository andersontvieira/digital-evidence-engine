"""Two explicit Takeout table contracts; values remain observations, not events."""

import ipaddress
import re
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import cast

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

SUBSCRIBER_HEADERS = {
    "Timestamp",
    "IP Address",
    "Activity Type",
    "Interactive",
    "Initiating Service",
    "Geo",
    "Raw User Agents",
    "Challenges (timestamp, outcome, dusi)",
}
CHANGE_HEADERS = {"Timestamp", "IP Address", "Change Type", "Old Value", "New Value"}


@dataclass(frozen=True)
class GoogleTableParser:
    parser_id: str
    filename: str
    record_type: str
    headers: frozenset[str]
    parser_version: str = "1.0.0"

    @property
    def required_headers(self) -> frozenset[str]:
        return (
            self.headers - {"Old Value", "New Value"}
            if self.parser_id == "google.change_history"
            else self.headers
        )

    def matches_path(self, context: ParserContext) -> bool:
        path = context.relative_path
        if (
            not path
            or "\\" in path
            or PureWindowsPath(path).drive
            or any(part in {"", ".", ".."} for part in path.split("/"))
        ):
            return False
        name = PurePosixPath(path).name
        return name == self.filename or (
            name.endswith("." + self.filename) and len(name) > len(self.filename) + 1
        )

    def matching_tables(self, document: JSONValue) -> list[tuple[int, dict[str, JSONValue]]]:
        if not isinstance(document, dict) or not isinstance(document.get("tables"), list):
            return []
        result = []
        for index, table in enumerate(cast(list[JSONValue], document["tables"])):
            if not isinstance(table, dict):
                continue
            headers = table.get("headers")
            if (
                isinstance(headers, list)
                and all(isinstance(h, str) for h in headers)
                and self.required_headers <= set(cast(list[str], headers))
                and isinstance(table.get("rows"), list)
            ):
                result.append((index, table))
        return result

    def supports(self, context: ParserContext, document: JSONValue) -> bool:
        return self.matches_path(context) and bool(self.matching_tables(document))

    def parse(self, context: ParserContext, document: JSONValue) -> ParserResult:
        if not self.supports(context, document):
            raise ParseError("UNSUPPORTED_SCHEMA")
        records: list[ExtractedRecord] = []
        warnings: list[Diagnostic] = []
        for table_index, table in self.matching_tables(document):
            rows = cast(list[JSONValue], table["rows"])
            if len(records) + len(rows) > MAX_RECORDS:
                raise ParseError("RECORD_LIMIT")
            for row_index, row in enumerate(rows):
                if not isinstance(row, dict) or not self.required_headers <= row.keys():
                    raise ParseError("INVALID_GOOGLE_ROW")
                locator = f"$/tables/{table_index}/rows/{row_index}"
                if not all(isinstance(v, str) for v in row.values()):
                    raise ParseError("INVALID_GOOGLE_CELL")
                annotations: list[dict[str, JSONValue]] = []
                for header in row:
                    if header not in self.headers:
                        warnings.append(
                            Diagnostic("UNKNOWN_GOOGLE_COLUMN", child_locator(locator, header))
                        )
                raw_ip = cast(str, row["IP Address"])
                if raw_ip:
                    ip_locator = child_locator(locator, "IP Address")
                    try:
                        address = ipaddress.ip_address(raw_ip)
                        annotations.append(
                            {
                                "kind": "ip_syntax",
                                "source_locator": ip_locator,
                                "version": address.version,
                            }
                        )
                    except ValueError:
                        warnings.append(Diagnostic("INVALID_IP_SYNTAX", ip_locator))
                agent = (
                    row.get("Raw User Agents")
                    if self.parser_id == "google.subscriber_info"
                    else None
                )
                if isinstance(agent, str):
                    for code in sorted(set(re.findall(r"\biPhone[0-9]+,[0-9]+\b", agent))):
                        annotations.append(
                            {
                                "kind": "model_code_from_user_agent",
                                "value": code,
                                "source_locator": child_locator(locator, "Raw User Agents"),
                            }
                        )
                records.append(
                    ExtractedRecord(
                        self.record_type, locator, row_index, row["Timestamp"], row, annotations
                    )
                )
        return ParserResult(records, warnings)


PARSERS: tuple[Parser, ...] = (
    GoogleTableParser(
        "google.subscriber_info",
        "SubscriberInfo.html",
        "google_security_activity",
        frozenset(SUBSCRIBER_HEADERS),
    ),
    GoogleTableParser(
        "google.change_history",
        "ChangeHistory.html",
        "google_account_change",
        frozenset(CHANGE_HEADERS),
    ),
)
