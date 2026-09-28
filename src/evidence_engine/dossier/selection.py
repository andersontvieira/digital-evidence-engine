"""Pure selection validation under ADR 0037; never opens selected artifacts.

Byte-bounded stdlib decoding precedes iterative depth/node checks. These are
operational guards, not an exact process-memory bound or semantic privacy check.
"""

import json
import math
import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from typing import NoReturn, cast

from evidence_engine.errors import EvidenceError

MAX_SELECTION_BYTES = 1024 * 1024
MAX_JSON_DEPTH = 64
MAX_JSON_NODES_PER_FILE = 1_000_000
MAX_NUMBER_CHARS = 128
MAX_SELECTED_ITEMS = 256
MAX_SUPPLEMENTAL_ITEMS = 64
MAX_VALIDATION_ARTIFACTS = 32
MAX_VISUAL_EXHIBITS = 32
MAX_CAPTION_CHARS = 500
MAX_REFERENCE_BYTES = 1024
MAX_REFERENCE_COMPONENTS = 32
MAX_COMPONENT_BYTES = 255

_LABEL = re.compile(r"[a-z][a-z0-9-]{0,47}")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_LONG_HEX = re.compile(r"[0-9a-f]{32,}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
# Match a whole scheme token with URI content immediately after the colon;
# ordinary prose such as "Nota: imagem" is not a URI.
_URI = re.compile(r"(?<![\w+.-])[a-zA-Z][a-zA-Z0-9+.-]*:(?=\S)|www\.|//", re.IGNORECASE)
_EMAIL_LINK = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
_MARKDOWN_BLOCK = re.compile(r"^(?:#{1,6}(?:\s|$)|[-+](?:\s|$)|[0-9]+[.)]\s|={3,}$|-{3,}$)")
_BIDI = frozenset("\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")
# Same reserved stems as Foundation validate_name; its ZIP helper permits colons
# and imports archive/filesystem machinery, so cannot serve this stricter API.
_RESERVED = frozenset({"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}) | frozenset(
    f"{prefix}{digit}" for prefix in ("COM", "LPT") for digit in "123456789¹²³"
)
_LISTS = {
    "canonical_inputs": ("CANONICAL_TECHNICAL", ("consolidated_report", "report_snapshot")),
    "supplemental_inputs": ("SUPPLEMENTAL_TECHNICAL", ("technical_review", "structured_support")),
    "validation_artifacts": ("VALIDATION_ARTIFACT", ("validation_report",)),
    "visual_exhibits": ("VISUAL_EXHIBIT", ("contextual_visual",)),
}
_TOP_REQUIRED = frozenset({"policy_id", "policy_version", "delivery_profile", "canonical_inputs"})
_TOP_OPTIONAL = frozenset(
    {
        "issued_date",
        "case_reference",
        "supplemental_inputs",
        "validation_artifacts",
        "visual_exhibits",
    }
)
_ITEM_REQUIRED = frozenset({"input_reference", "local_label", "source_class", "role"})
_APPROVALS = ("operator_selected", "display_approved")


@dataclass(frozen=True, slots=True, kw_only=True)
class SelectedInput:
    input_reference: str
    local_label: str
    source_class: str
    role: str
    expected_sha256: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class VisualExhibitInput(SelectedInput):
    display_caption: str
    operator_selected: bool
    display_approved: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class DossierSelection:
    policy_id: str
    policy_version: str
    delivery_profile: str
    issued_date: str | None
    case_reference: str | None
    canonical_inputs: tuple[SelectedInput, ...]
    supplemental_inputs: tuple[SelectedInput, ...]
    validation_artifacts: tuple[SelectedInput, ...]
    visual_exhibits: tuple[VisualExhibitInput, ...]


def _fail(code: str = "INVALID_SELECTION") -> NoReturn:
    raise EvidenceError(f"DOSSIER_{code}")


def _require(condition: bool, code: str = "INVALID_SELECTION") -> None:
    if not condition:
        _fail(code)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _constant(value: str) -> NoReturn:
    _fail()


def _integer(value: str) -> int:
    _require(len(value) <= MAX_NUMBER_CHARS, "RESOURCE_LIMIT")
    return int(value)


def _float(value: str) -> float:
    _require(len(value) <= MAX_NUMBER_CHARS, "RESOURCE_LIMIT")
    number = float(value)
    _require(math.isfinite(number))
    return number


def _check_structure(document: object, *, allow_null: bool = False) -> int:
    """Count values (including containers) and keys without recursive traversal."""
    stack: list[tuple[Iterator[object], int]] = [(iter((document,)), 0)]
    nodes = 0
    while stack:
        iterator, parent_depth = stack[-1]
        try:
            value = next(iterator)
        except StopIteration:
            stack.pop()
            continue
        nodes += 1
        _require(nodes <= MAX_JSON_NODES_PER_FILE, "RESOURCE_LIMIT")
        _require(allow_null or value is not None)
        if isinstance(value, (dict, list)):
            depth = parent_depth + 1
            _require(depth <= MAX_JSON_DEPTH, "RESOURCE_LIMIT")
            if isinstance(value, dict):
                nodes += len(value)
                _require(nodes <= MAX_JSON_NODES_PER_FILE, "RESOURCE_LIMIT")
                stack.append((iter(value.values()), depth))
            else:
                stack.append((iter(value), depth))
    return nodes


def _object(value: object) -> dict[str, object]:
    _require(type(value) is dict)
    return cast(dict[str, object], value)


def _string(value: object) -> str:
    _require(type(value) is str)
    return cast(str, value)


def _shape(value: dict[str, object], required: frozenset[str], optional: frozenset[str]) -> None:
    _require(required <= value.keys() and value.keys() <= required | optional)


def _label(value: object) -> str:
    text = _string(value)
    _require(_LABEL.fullmatch(text) is not None)
    _require(_UUID.fullmatch(text) is None and _LONG_HEX.search(text) is None)
    return text


def _issued_date(value: object) -> str:
    text = _string(value)
    _require(_DATE.fullmatch(text) is not None)
    try:
        date.fromisoformat(text)
    except ValueError:
        _fail()
    return text


def _control(char: str) -> bool:
    return ord(char) < 32 or 127 <= ord(char) <= 159


def _input_reference(value: object) -> str:
    text = _string(value)
    try:
        encoded = text.encode("utf-8")
    except UnicodeError:
        _fail("INVALID_PATH")
    _require(len(encoded) <= MAX_REFERENCE_BYTES, "RESOURCE_LIMIT")
    _require(bool(text) and unicodedata.is_normalized("NFC", text), "INVALID_PATH")
    _require(not any(_control(c) or c in '\\:<>"|?*' for c in text), "INVALID_PATH")
    parts = text.split("/")
    _require(len(parts) <= MAX_REFERENCE_COMPONENTS, "RESOURCE_LIMIT")
    for part in parts:
        _require(len(part.encode("utf-8")) <= MAX_COMPONENT_BYTES, "RESOURCE_LIMIT")
        _require(part not in ("", ".", "..") and not part.endswith((".", " ")), "INVALID_PATH")
        _require(part.split(".")[0].upper() not in _RESERVED, "INVALID_PATH")
        _require(part.casefold() not in ("originals", "working"), "INVALID_PATH")
    _require(parts[-1].casefold() != "evidence.db", "INVALID_PATH")
    return text


def _caption(value: object) -> str:
    text = _string(value)
    _require(len(text) <= MAX_CAPTION_CHARS, "RESOURCE_LIMIT")
    _require(bool(text) and text == text.strip(), "PRIVACY_CONTRACT_VIOLATION")
    _require(unicodedata.is_normalized("NFC", text), "PRIVACY_CONTRACT_VIOLATION")
    _require(
        not any(
            _control(c) or 0xD800 <= ord(c) <= 0xDFFF or c in _BIDI or c in "\u2028\u2029"
            for c in text
        ),
        "PRIVACY_CONTRACT_VIOLATION",
    )
    # Deliberately plain text: reject markup delimiters, block markers and link
    # forms structurally. No interpretation of truth, names or image content.
    _require(
        not any(c in "<>[]`*_~\\|" for c in text)
        and _MARKDOWN_BLOCK.search(text) is None
        and _URI.search(text) is None
        and _EMAIL_LINK.search(text) is None,
        "PRIVACY_CONTRACT_VIOLATION",
    )
    return text


def _item(value: object, list_name: str) -> SelectedInput:
    item = _object(value)
    source_class = _string(item.get("source_class"))
    role = _string(item.get("role"))
    expected_class, roles = _LISTS[list_name]
    _require(source_class == expected_class and role in roles, "INVALID_ROLE_CLASS")
    required = _ITEM_REQUIRED
    visual = list_name == "visual_exhibits"
    if visual:
        for approval in _APPROVALS:
            _require(approval in item, "PRIVACY_CONTRACT_VIOLATION")
            _require(type(item[approval]) is bool)
            _require(item[approval] is True, "PRIVACY_CONTRACT_VIOLATION")
        required |= frozenset({"display_caption", *_APPROVALS})
    _shape(item, required, frozenset({"expected_sha256"}))
    reference = _input_reference(item["input_reference"])
    label = _label(item["local_label"])
    expected_hash = None
    if "expected_sha256" in item:
        expected_hash = _string(item["expected_sha256"])
        _require(_SHA256.fullmatch(expected_hash) is not None)
    if visual:
        return VisualExhibitInput(
            input_reference=reference,
            local_label=label,
            source_class=source_class,
            role=role,
            expected_sha256=expected_hash,
            display_caption=_caption(item["display_caption"]),
            operator_selected=True,
            display_approved=True,
        )
    return SelectedInput(
        input_reference=reference,
        local_label=label,
        source_class=source_class,
        role=role,
        expected_sha256=expected_hash,
    )


def _collisions(items: tuple[SelectedInput, ...]) -> None:
    labels: set[str] = set()
    references: set[str] = set()
    folded_files: set[tuple[str, ...]] = set()
    prefixes: dict[tuple[str, ...], tuple[str, ...]] = {}
    for item in items:
        _require(item.local_label not in labels and item.input_reference not in references)
        labels.add(item.local_label)
        references.add(item.input_reference)
        parts = tuple(item.input_reference.split("/"))
        folded = tuple(part.casefold() for part in parts)
        _require(folded not in folded_files, "INVALID_PATH")
        folded_files.add(folded)
        for size in range(1, len(parts) + 1):
            key, spelling = folded[:size], parts[:size]
            _require(key not in prefixes or prefixes[key] == spelling, "INVALID_PATH")
            prefixes[key] = spelling
    for parts in folded_files:
        _require(
            not any(parts[:size] in folded_files for size in range(1, len(parts))), "INVALID_PATH"
        )


def _selection(document: object) -> DossierSelection:
    root = _object(document)
    _shape(root, _TOP_REQUIRED, _TOP_OPTIONAL)
    for key, expected in (
        ("policy_id", "dossier.selection"),
        ("policy_version", "1.0.0"),
        ("delivery_profile", "directory-v1"),
    ):
        _require(_string(root[key]) == expected, "UNSUPPORTED_POLICY_VERSION")
    issued = _issued_date(root["issued_date"]) if "issued_date" in root else None
    reference = _label(root["case_reference"]) if "case_reference" in root else None
    lists: dict[str, list[object]] = {}
    for name in _LISTS:
        value = root.get(name, [])
        _require(type(value) is list)
        lists[name] = cast(list[object], value)
    _require(sum(map(len, lists.values())) <= MAX_SELECTED_ITEMS, "RESOURCE_LIMIT")
    for name, limit in (
        ("supplemental_inputs", MAX_SUPPLEMENTAL_ITEMS),
        ("validation_artifacts", MAX_VALIDATION_ARTIFACTS),
        ("visual_exhibits", MAX_VISUAL_EXHIBITS),
    ):
        _require(len(lists[name]) <= limit, "RESOURCE_LIMIT")
    normalized = {
        name: tuple(sorted((_item(v, name) for v in values), key=lambda i: (i.role, i.local_label)))
        for name, values in lists.items()
    }
    canonical = normalized["canonical_inputs"]
    _require(sum(i.role == "consolidated_report" for i in canonical) == 1)
    _require(any(i.role == "report_snapshot" for i in canonical))
    _collisions(tuple(i for group in normalized.values() for i in group))
    return DossierSelection(
        policy_id="dossier.selection",
        policy_version="1.0.0",
        delivery_profile="directory-v1",
        issued_date=issued,
        case_reference=reference,
        canonical_inputs=canonical,
        supplemental_inputs=normalized["supplemental_inputs"],
        validation_artifacts=normalized["validation_artifacts"],
        visual_exhibits=cast(tuple[VisualExhibitInput, ...], normalized["visual_exhibits"]),
    )


def parse_selection_bytes(content: bytes) -> DossierSelection:
    """Validate already captured bytes; return immutable, canonically ordered DTOs.

    No filesystem, artifact-content, hash, containment or identity validation.
    Errors contain only stable dossier codes, never selection values.
    """
    try:
        _require(type(content) is bytes)
        _require(len(content) <= MAX_SELECTION_BYTES, "RESOURCE_LIMIT")
        _require(not content.startswith(b"\xef\xbb\xbf"))
        document: object = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_constant,
            parse_int=_integer,
            parse_float=_float,
        )
        _check_structure(document)
        return _selection(document)
    except (MemoryError, RecursionError):
        raise EvidenceError("DOSSIER_RESOURCE_LIMIT") from None
    except (UnicodeError, ValueError):
        raise EvidenceError("DOSSIER_INVALID_SELECTION") from None
