"""Synthetic in-memory selection contracts; no artifact files or case fixtures."""

import ast
import builtins
import inspect
import json
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from evidence_engine.dossier import selection as s
from evidence_engine.errors import EvidenceError


def item(role="report_snapshot", label="anchor", reference=None):
    classes = {
        "consolidated_report": "CANONICAL_TECHNICAL",
        "report_snapshot": "CANONICAL_TECHNICAL",
        "technical_review": "SUPPLEMENTAL_TECHNICAL",
        "structured_support": "SUPPLEMENTAL_TECHNICAL",
        "validation_report": "VALIDATION_ARTIFACT",
        "contextual_visual": "VISUAL_EXHIBIT",
    }
    value = {
        "input_reference": reference or f"inputs/{label}.synthetic",
        "local_label": label,
        "source_class": classes[role],
        "role": role,
    }
    if role == "contextual_visual":
        value.update(
            display_caption="Imagem sintética — contexto explícito.",
            operator_selected=True,
            display_approved=True,
        )
    return value


def minimal():
    return {
        "policy_id": "dossier.selection",
        "policy_version": "1.0.0",
        "delivery_profile": "directory-v1",
        "canonical_inputs": [item("consolidated_report", "report"), item()],
    }


def parse(value):
    return s.parse_selection_bytes(json.dumps(value, ensure_ascii=True).encode("utf-8"))


def reject(value, code="INVALID_SELECTION"):
    with pytest.raises(EvidenceError) as caught:
        parse(value)
    assert str(caught.value) == f"DOSSIER_{code}"


def reject_bytes(value, code="INVALID_SELECTION"):
    with pytest.raises(EvidenceError) as caught:
        s.parse_selection_bytes(value)
    assert str(caught.value) == f"DOSSIER_{code}"


def visual_selection():
    value = minimal()
    value["visual_exhibits"] = [item("contextual_visual", "visual")]
    return value


def test_minimal_immutable_dtos_and_no_defaults():
    result = parse(minimal())
    assert isinstance(result, s.DossierSelection)
    assert result.policy_id == "dossier.selection"
    assert result.policy_version == "1.0.0"
    assert result.delivery_profile == "directory-v1"
    assert result.issued_date is result.case_reference is None
    assert result.supplemental_inputs == result.validation_artifacts == result.visual_exhibits == ()
    assert result.canonical_inputs == (
        s.SelectedInput(**minimal()["canonical_inputs"][0]),
        s.SelectedInput(**minimal()["canonical_inputs"][1]),
    )
    with pytest.raises(FrozenInstanceError):
        result.policy_id = "changed"
    with pytest.raises(FrozenInstanceError):
        result.canonical_inputs[0].role = "changed"
    with pytest.raises(TypeError):
        result.canonical_inputs[0] = result.canonical_inputs[1]
    assert not hasattr(result, "__dict__")


def test_omitted_equals_empty_and_all_list_permutations():
    empty = minimal()
    for name in ("supplemental_inputs", "validation_artifacts", "visual_exhibits"):
        empty[name] = []
    assert parse(empty) == parse(minimal())
    value = minimal()
    value["canonical_inputs"] += [item(label="z-window"), item(label="a-window")]
    value["supplemental_inputs"] = [
        item("technical_review", "review"),
        item("structured_support", "support"),
    ]
    value["validation_artifacts"] = [item("validation_report", f"validation-{i}") for i in (2, 1)]
    value["visual_exhibits"] = [item("contextual_visual", f"visual-{i}") for i in (2, 1)]
    result = parse(value)
    for name in (
        "canonical_inputs",
        "supplemental_inputs",
        "validation_artifacts",
        "visual_exhibits",
    ):
        reordered = deepcopy(value)
        reordered[name].reverse()
        assert parse(reordered) == result
        rows = getattr(result, name)
        assert isinstance(rows, tuple)
        assert [(r.role, r.local_label) for r in rows] == sorted(
            (r.role, r.local_label) for r in rows
        )
    assert isinstance(result.visual_exhibits[0], s.VisualExhibitInput)


@pytest.mark.parametrize(
    "key", ["policy_id", "policy_version", "delivery_profile", "canonical_inputs"]
)
def test_required_top_fields(key):
    value = minimal()
    del value[key]
    reject(value)


@pytest.mark.parametrize(
    "key",
    [
        "person_name",
        "client_name",
        "party_name",
        "CPF",
        "process_number",
        "court",
        "jurisdiction",
        "metadata",
    ],
)
def test_unknown_top_fields(key):
    value = minimal()
    value[key] = "synthetic"
    reject(value)


@pytest.mark.parametrize(
    "key",
    [
        "issued_date",
        "case_reference",
        "supplemental_inputs",
        "validation_artifacts",
        "visual_exhibits",
        "canonical_inputs",
        "policy_id",
        "policy_version",
        "delivery_profile",
    ],
)
@pytest.mark.parametrize("bad", [None, True, 1, {}])
def test_top_types_and_null(key, bad):
    value = minimal()
    value[key] = bad
    reject(value)


@pytest.mark.parametrize("key", ["policy_id", "policy_version", "delivery_profile"])
def test_unsupported_policy(key):
    value = minimal()
    value[key] = "future"
    reject(value, "UNSUPPORTED_POLICY_VERSION")


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"{",
        b"[]",
        b"null",
        b"true",
        b'"text"',
        b"\xff",
        b"\xef\xbb\xbf{}",
        b'{"x":1,"x":2}',
        b'{"x":{"a":1,"a":2}}',
        b"NaN",
        b"Infinity",
        b"-Infinity",
        b"1e999",
    ],
)
def test_invalid_json(raw):
    reject_bytes(raw)


@pytest.mark.parametrize("kind", ["integer", "float"])
def test_number_lexical_budget(kind):
    value = "1" * 128 if kind == "integer" else "0." + "1" * 126
    reject_bytes(value.encode())  # Decodes within budget, but is not a selection object.
    reject_bytes((value + "1").encode(), "RESOURCE_LIMIT")


def test_selection_byte_cap_precedes_decode(monkeypatch):
    content = json.dumps(minimal()).encode()
    assert s.parse_selection_bytes(
        content + b" " * (s.MAX_SELECTION_BYTES - len(content))
    ) == parse(minimal())

    def forbidden(*args, **kwargs):
        raise AssertionError("decoder must not run")

    monkeypatch.setattr(s.json, "loads", forbidden)
    reject_bytes(b" " * (s.MAX_SELECTION_BYTES + 1), "RESOURCE_LIMIT")


def test_depth_64_65():
    reject_bytes(b"[" * 64 + b"0" + b"]" * 64)
    reject_bytes(b"[" * 65 + b"0" + b"]" * 65, "RESOURCE_LIMIT")
    reject_bytes(b"[" * 2000 + b"0" + b"]" * 2000, "RESOURCE_LIMIT")


def test_node_guard_counts_keys_values_and_containers(monkeypatch):
    # Root, key a, array, bool, nested object, key b, integer: exactly seven nodes.
    document = {"a": [True, {"b": 2}]}
    monkeypatch.setattr(s, "MAX_JSON_NODES_PER_FILE", 7)
    s._check_structure(document)
    monkeypatch.setattr(s, "MAX_JSON_NODES_PER_FILE", 6)
    reject(document, "RESOURCE_LIMIT")


@pytest.mark.parametrize("error", [MemoryError, RecursionError])
@pytest.mark.parametrize("phase", ["decode", "traversal"])
def test_exhaustion_mapping(monkeypatch, error, phase):
    content = json.dumps(minimal()).encode()

    def exhausted(*args, **kwargs):
        raise error("synthetic private detail")

    if phase == "decode":
        monkeypatch.setattr(s.json, "loads", exhausted)
    else:
        monkeypatch.setattr(s, "_check_structure", exhausted)
    reject_bytes(content, "RESOURCE_LIMIT")


@pytest.mark.parametrize(
    "source_class",
    [
        "UNKNOWN",
        "ORIGINAL_EVIDENCE",
        "LEGACY_MANUAL_WORK_PRODUCT",
        "GENERATED_PRESENTATION",
        "GENERATED_METADATA",
        "VISUAL_EXHIBIT",
    ],
)
def test_rejected_classes(source_class):
    value = minimal()
    value["canonical_inputs"][0]["source_class"] = source_class
    reject(value, "INVALID_ROLE_CLASS")


@pytest.mark.parametrize(
    "list_name,role",
    [
        ("supplemental_inputs", "technical_review"),
        ("supplemental_inputs", "structured_support"),
        ("validation_artifacts", "validation_report"),
        ("visual_exhibits", "contextual_visual"),
    ],
)
def test_allowed_pair_and_wrong_list(list_name, role):
    value = minimal()
    value[list_name] = [item(role, "extra")]
    assert len(getattr(parse(value), list_name)) == 1
    value["canonical_inputs"].append(value.pop(list_name)[0])
    reject(value, "INVALID_ROLE_CLASS")


def test_unknown_role():
    value = minimal()
    value["canonical_inputs"][0]["role"] = "unknown"
    reject(value, "INVALID_ROLE_CLASS")


@pytest.mark.parametrize("reports,snapshots", [(0, 1), (2, 1), (1, 0), (0, 0)])
def test_canonical_cardinality(reports, snapshots):
    value = minimal()
    value["canonical_inputs"] = [item("consolidated_report", f"report-{i}") for i in range(reports)]
    value["canonical_inputs"] += [item(label=f"snapshot-{i}") for i in range(snapshots)]
    reject(value)


def test_many_snapshots_no_twenty_limit_and_total_budget():
    value = minimal()
    value["canonical_inputs"] = [item("consolidated_report", "report")]
    value["canonical_inputs"] += [item(label=f"snapshot-{i}") for i in range(255)]
    result = parse(value)
    assert len(result.canonical_inputs) == 256  # Includes 255 unopened snapshots.
    value["canonical_inputs"].append(item(label="snapshot-extra"))
    reject(value, "RESOURCE_LIMIT")


@pytest.mark.parametrize(
    "name,role,limit",
    [
        ("supplemental_inputs", "technical_review", 64),
        ("validation_artifacts", "validation_report", 32),
        ("visual_exhibits", "contextual_visual", 32),
    ],
)
def test_optional_list_budgets(name, role, limit):
    value = minimal()
    value[name] = [item(role, f"extra-{i}") for i in range(limit)]
    assert len(getattr(parse(value), name)) == limit
    value[name].append(item(role, "extra-last"))
    reject(value, "RESOURCE_LIMIT")


@pytest.mark.parametrize(
    "field", ["unknown", "display_caption", "operator_selected", "display_approved"]
)
def test_unknown_and_visual_only_item_fields(field):
    value = minimal()
    value["canonical_inputs"][0][field] = "synthetic"
    reject(value)


@pytest.mark.parametrize("field", ["input_reference", "local_label", "source_class", "role"])
@pytest.mark.parametrize("bad", [None, False, 4, [], {}])
def test_item_types(field, bad):
    value = minimal()
    value["canonical_inputs"][0][field] = bad
    reject(value)


@pytest.mark.parametrize(
    "field",
    [
        "input_reference",
        "local_label",
        "source_class",
        "role",
        "display_caption",
        "operator_selected",
        "display_approved",
    ],
)
def test_visual_missing_required(field):
    value = visual_selection()
    del value["visual_exhibits"][0][field]
    reject(
        value,
        "PRIVACY_CONTRACT_VIOLATION"
        if field in ("operator_selected", "display_approved")
        else "INVALID_SELECTION",
    )


@pytest.mark.parametrize("bad", ["A" * 64, "a" * 63, "a" * 65, "g" * 64, None, True])
def test_expected_hash_invalid(bad):
    value = minimal()
    value["canonical_inputs"][0]["expected_sha256"] = bad
    reject(value)


def test_expected_hash_preserved_without_verification():
    value = minimal()
    value["canonical_inputs"][0]["expected_sha256"] = "a" * 64
    assert parse(value).canonical_inputs[0].expected_sha256 == "a" * 64


@pytest.mark.parametrize("label", ["z", "z" * 48, "g" + "a" * 31, "nome-sintetico"])
@pytest.mark.parametrize("field", ["local_label", "case_reference"])
def test_valid_labels_no_person_detector(label, field):
    value = minimal()
    target = value if field == "case_reference" else value["canonical_inputs"][0]
    target[field] = label
    result = parse(value)
    assert (
        result.case_reference
        if field == "case_reference"
        else result.canonical_inputs[0].local_label
    ) == label


@pytest.mark.parametrize(
    "label",
    [
        "",
        "1a",
        "UPPER",
        "under_score",
        " white",
        "white ",
        "white\n",
        "z" * 49,
        "abcabcab-abca-abca-abca-abcabcabcabc",
        "ABCABCAB-ABCA-ABCA-ABCA-ABCABCABCABC",
        "g" + "a" * 32,
        "é",
    ],
)
@pytest.mark.parametrize("field", ["local_label", "case_reference"])
def test_invalid_labels(label, field):
    value = minimal()
    target = value if field == "case_reference" else value["canonical_inputs"][0]
    target[field] = label
    reject(value)


@pytest.mark.parametrize("issued", ["2000-02-29", "0001-01-01", "9999-12-31"])
def test_dates(issued):
    value = minimal()
    value["issued_date"] = issued
    assert parse(value).issued_date == issued


@pytest.mark.parametrize(
    "issued",
    [
        "1900-02-29",
        "0000-01-01",
        "2000-2-29",
        " 2000-02-29",
        "2000-02-29Z",
        "２０００-02-29",
        "2000-13-01",
        "2000-01-00",
    ],
)
def test_invalid_dates(issued):
    value = minimal()
    value["issued_date"] = issued
    reject(value)


@pytest.mark.parametrize(
    "caption",
    [
        "",
        " ",
        " prefix",
        "suffix ",
        "a\nb",
        "a\rb",
        "a\tb",
        "a\x00b",
        "a\x85b",
        "a\u202eb",
        "a\u2066b",
        "a\ud800b",
        "a\u2028b",
        "e\u0301",
        "<b>synthetic</b>",
        "[link](synthetic)",
        "https://example.invalid",
        "//example.invalid/synthetic",
        "www.example.invalid",
        "mailto:synthetic@example.invalid",
        "**bold**",
        "_emphasis_",
        "`code`",
        "# Heading",
        "+ list",
        "1. list",
        "---",
    ],
)
def test_caption_structural_privacy(caption):
    value = visual_selection()
    value["visual_exhibits"][0]["display_caption"] = caption
    reject(value, "PRIVACY_CONTRACT_VIOLATION")


@pytest.mark.parametrize(
    "caption",
    [
        "Nota: imagem sintética.",
        "Foto: contexto explícito.",
        "Figura 1: imagem contextual.",
        "Observacao: material selecionado.",
    ],
)
def test_caption_plain_colon_preserved(caption):
    value = visual_selection()
    value["visual_exhibits"][0]["display_caption"] = caption
    assert parse(value).visual_exhibits[0].display_caption == caption


@pytest.mark.parametrize(
    "uri",
    [
        "https://example.invalid",
        "http://example.invalid",
        "ftp://example.invalid",
        "file://example.invalid/path",
        "mailto:synthetic@example.invalid",
        "data:text/plain,synthetic",
        "urn:synthetic:test",
        "www.example.invalid",
        "//example.invalid/path",
    ],
)
@pytest.mark.parametrize("prefix", ["", "Nota: "])
def test_caption_uri_rejected_standalone_or_in_prose(uri, prefix):
    value = visual_selection()
    value["visual_exhibits"][0]["display_caption"] = prefix + uri
    reject(value, "PRIVACY_CONTRACT_VIOLATION")


def test_caption_budget_and_approved_unicode():
    value = visual_selection()
    assert (
        parse(value).visual_exhibits[0].display_caption == "Imagem sintética — contexto explícito."
    )
    value["visual_exhibits"][0]["display_caption"] = "é" * 500
    assert len(parse(value).visual_exhibits[0].display_caption) == 500
    value["visual_exhibits"][0]["display_caption"] += "é"
    reject(value, "RESOURCE_LIMIT")


@pytest.mark.parametrize("field", ["operator_selected", "display_approved"])
@pytest.mark.parametrize(
    "value,code",
    [
        (False, "PRIVACY_CONTRACT_VIOLATION"),
        (1, "INVALID_SELECTION"),
        ("true", "INVALID_SELECTION"),
        (None, "INVALID_SELECTION"),
    ],
)
def test_approval(field, value, code):
    selection = visual_selection()
    selection["visual_exhibits"][0][field] = value
    reject(selection, code)


@pytest.mark.parametrize(
    "reference",
    ["nested/ação.synthetic", "%2e%2e/%2fsynthetic.json", "conifer.txt", "com0.txt", "lpt10.txt"],
)
def test_valid_reference_literal_percent(reference):
    value = minimal()
    value["canonical_inputs"][0]["input_reference"] = reference
    assert parse(value).canonical_inputs[0].input_reference == reference


@pytest.mark.parametrize(
    "reference",
    [
        "",
        "/abs",
        "C:/synthetic",
        "//synthetic/share",
        "\\\\synthetic\\share",
        "a\\b",
        "../a",
        "a/../b",
        "./a",
        "a//b",
        "a/",
        "a\x00b",
        "a\x7fb",
        "a\x9fb",
        "a:b",
        "a<b",
        "a>b",
        'a"b',
        "a|b",
        "a?b",
        "a*b",
        "a.",
        "a ",
        "e\u0301/a",
        "a\ud800b",
        "originals/a",
        "a/ORIGINALS/b",
        "Working/a",
        "a/EVIDENCE.DB",
        "NUL.txt",
        "aux",
        "CON",
        "PRN.txt",
        "CONIN$",
        "CONOUT$.x",
        *[f"{prefix}{digit}.txt" for prefix in ("COM", "LPT") for digit in "123456789¹²³"],
    ],
)
def test_invalid_reference(reference):
    value = minimal()
    value["canonical_inputs"][0]["input_reference"] = reference
    reject(value, "INVALID_PATH")


@pytest.mark.parametrize(
    "valid,invalid",
    [
        ("a" * 255, "a" * 256),
        ("/".join(["a"] * 32), "/".join(["a"] * 33)),
        (
            "/".join(["a" * 255] * 3 + ["b" * 254, "z"]),
            "/".join(["a" * 255] * 3 + ["b" * 254, "zz"]),
        ),
    ],
)
def test_reference_budgets(valid, invalid):
    value = minimal()
    value["canonical_inputs"][0]["input_reference"] = valid
    assert parse(value).canonical_inputs[0].input_reference == valid
    value["canonical_inputs"][0]["input_reference"] = invalid
    reject(value, "RESOURCE_LIMIT")


def test_unicode_reference_bytes_not_characters():
    value = minimal()
    value["canonical_inputs"][0]["input_reference"] = "é" * 127 + "a"
    parse(value)
    value["canonical_inputs"][0]["input_reference"] = "é" * 128
    reject(value, "RESOURCE_LIMIT")


@pytest.mark.parametrize(
    "left,right,code",
    [
        ("inputs/a", "inputs/a", "INVALID_SELECTION"),
        ("inputs/a", "inputs/A", "INVALID_PATH"),
        ("inputs/a", "INPUTS/b", "INVALID_PATH"),
        ("inputs/a", "inputs/a/b", "INVALID_PATH"),
        ("inputs/a/b", "inputs/a", "INVALID_PATH"),
    ],
)
def test_reference_collisions(left, right, code):
    value = minimal()
    value["canonical_inputs"][0]["input_reference"] = left
    value["canonical_inputs"][1]["input_reference"] = right
    reject(value, code)


def test_global_label_collision_across_lists():
    value = minimal()
    value["supplemental_inputs"] = [item("technical_review", "anchor", "different/synthetic.md")]
    reject(value)


def test_dependency_boundary_and_pure_execution(monkeypatch):
    tree = ast.parse(inspect.getsource(s))
    allowed = {
        "json",
        "math",
        "re",
        "unicodedata",
        "collections.abc",
        "dataclasses",
        "datetime",
        "typing",
        "evidence_engine.errors",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name in allowed for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module in allowed
    content = json.dumps(visual_selection()).encode()

    def forbidden(*args, **kwargs):
        raise AssertionError("filesystem input access forbidden")

    monkeypatch.setattr(builtins, "open", forbidden)
    for name in ("open", "stat", "lstat", "resolve"):
        monkeypatch.setattr(Path, name, forbidden)
    assert s.parse_selection_bytes(content).visual_exhibits[0].operator_selected is True


def test_errors_do_not_echo_payload():
    value = visual_selection()
    value["visual_exhibits"][0]["display_caption"] = "<synthetic-private-marker>"
    reject(value, "PRIVACY_CONTRACT_VIOLATION")


@pytest.mark.parametrize("bad", [None, True, 1, [], {}])
def test_caption_type_is_not_coerced(bad):
    value = visual_selection()
    value["visual_exhibits"][0]["display_caption"] = bad
    reject(value)


@pytest.mark.parametrize("bad", [None, True, 1, "item", []])
def test_item_must_be_object(bad):
    value = minimal()
    value["canonical_inputs"][0] = bad
    reject(value)


def test_total_budget_sums_all_lists():
    value = visual_selection()
    value["canonical_inputs"] += [item(label=f"snapshot-{i}") for i in range(253)]
    assert len(parse(value).canonical_inputs) == 255
    value["validation_artifacts"] = [item("validation_report", "validation")]
    reject(value, "RESOURCE_LIMIT")
