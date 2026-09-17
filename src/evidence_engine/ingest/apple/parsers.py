"""Three explicit Apple CSV contracts; no identifier or timestamp normalization."""

import ipaddress
from dataclasses import dataclass
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

ACCOUNT_PATH = "Informações da Conta Apple e do dispositivo/"
DEVICE_HEADERS = frozenset(
    (
        "Device Name",
        "Device Added Date",
        "Device IMEI",
        "Device Serial Number",
        "Device Last Heartbeat IP",
        "Device Last Heartbeat Timestamp",
        "Device Model Name",
        "Device Phone Number",
        "Device ICCID",
        "Device MEID",
        "Device Time Zone",
        "Device Locale Language",
        "Stolen Device Protection",
        "Latest Biometric Timestamp",
        "Stolen Device Protection - Turned On Timestamp",
        "Stolen Device Protection - Turned Off Timestamp",
        "Device Color Code",
        "Device OS Version",
    )
)
SIGN_ON_HEADERS = frozenset(
    (
        "Application",
        "Apple ID Number",
        "Device Identifier",
        "IP Address",
        "Logged In Date",
        "Signon Status",
        "StoreFront Name",
    )
)
MEDIA_HEADERS = frozenset(
    (
        "Device Hardware Family",
        "Device Hardware Model",
        "Device Identifier",
        "Event Date",
        "Event Time",
        "Metrics Event Time",
        "Event Type",
        "Application Name",
        "Operating System",
        "Operating System Version",
        "User Agent",
        "IP",
    )
)


@dataclass(frozen=True)
class AppleCSVParser:
    parser_id: str
    paths: frozenset[str]
    record_type: str
    required_headers: frozenset[str]
    projected_headers: frozenset[str]
    ip_header: str
    timestamp_header: str
    parser_version: str = "1.0.0"

    def matches_path(self, context: ParserContext) -> bool:
        return context.relative_path in self.paths

    def supports(self, context: ParserContext, document: JSONValue) -> bool:
        if not self.matches_path(context) or not isinstance(document, dict):
            return False
        headers = document.get("headers")
        return (
            isinstance(headers, list)
            and all(isinstance(header, str) for header in headers)
            and len(set(cast(list[str], headers))) == len(headers)
            and self.required_headers <= set(cast(list[str], headers))
            and isinstance(document.get("rows"), list)
        )

    def parse(self, context: ParserContext, document: JSONValue) -> ParserResult:
        if not self.supports(context, document):
            raise ParseError("UNSUPPORTED_SCHEMA")
        assert isinstance(document, dict)
        rows = cast(list[JSONValue], document["rows"])
        if len(rows) > MAX_RECORDS:
            raise ParseError("RECORD_LIMIT")
        records: list[ExtractedRecord] = []
        warnings: list[Diagnostic] = []
        for index, row in enumerate(rows):
            if (
                not isinstance(row, dict)
                or not self.required_headers <= row.keys()
                or not all(isinstance(value, str) for value in row.values())
            ):
                raise ParseError("INVALID_APPLE_ROW")
            locator = f"$/rows/{index}"
            payload = {key: value for key, value in row.items() if key in self.projected_headers}
            annotations: list[dict[str, JSONValue]] = [
                {
                    "kind": "timestamp_role",
                    "field": self.timestamp_header,
                    "source_locator": child_locator(locator, self.timestamp_header),
                }
            ]
            raw_ip = cast(str, row[self.ip_header])
            if raw_ip:
                ip_locator = child_locator(locator, self.ip_header)
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
            records.append(
                ExtractedRecord(
                    self.record_type,
                    locator,
                    index,
                    row[self.timestamp_header],
                    payload,
                    annotations,
                )
            )
        return ParserResult(records, warnings)


PARSERS: tuple[Parser, ...] = (
    AppleCSVParser(
        "apple.device_inventory",
        frozenset({ACCOUNT_PATH + "Apple ID Device Information.csv"}),
        "apple_device_inventory",
        frozenset(
            {
                "Device Name",
                "Device IMEI",
                "Device Serial Number",
                "Device Model Name",
                "Device Last Heartbeat IP",
                "Device Last Heartbeat Timestamp",
            }
        ),
        DEVICE_HEADERS,
        "Device Last Heartbeat IP",
        "Device Last Heartbeat Timestamp",
    ),
    AppleCSVParser(
        "apple.sign_on_activity",
        frozenset({ACCOUNT_PATH + "Apple ID SignOn Information.csv"}),
        "apple_sign_on_activity",
        SIGN_ON_HEADERS,
        SIGN_ON_HEADERS,
        "IP Address",
        "Logged In Date",
    ),
    AppleCSVParser(
        "apple.media_device_activity",
        frozenset(
            {
                "Apple_Media_Services/Stores Activity/Other Activity/Purchase Server Events.csv",
                "Apple_Media_Services/Apple Media Services/Stores Activity/Other Activity/"
                "Purchase Server Events.csv",
            }
        ),
        "apple_media_device_activity",
        frozenset(
            {
                "Device Identifier",
                "Device Hardware Model",
                "Device Hardware Family",
                "Event Time",
                "Event Type",
                "Application Name",
                "IP",
            }
        ),
        MEDIA_HEADERS,
        "IP",
        "Event Time",
    ),
)
