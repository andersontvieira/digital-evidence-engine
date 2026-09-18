"""Two versioned observers; every fact depends on exactly one ParsedRecord."""

import ipaddress
import re
from dataclasses import dataclass

from evidence_engine.ingest.parsing.framework import JSONValue, child_locator, json_text
from evidence_engine.observations.framework import (
    DeviceDraft,
    NetworkDraft,
    ObservationContext,
    ObservationResult,
    Observer,
    field_value,
)

# No message/conversation contract: no supported device fields and no IP association.
CONTRACTS = {
    "meta.profile_activity": ("profile_activity", {"1.0.0", "1.1.0"}),
    "meta.recently_deleted_content": ("recently_deleted_content", {"1.0.0", "1.1.0"}),
    "google.subscriber_info": ("google_security_activity", {"1.0.0"}),
    "google.change_history": ("google_account_change", {"1.0.0"}),
    "apple.device_inventory": ("apple_device_inventory", {"1.0.0"}),
    "apple.sign_on_activity": ("apple_sign_on_activity", {"1.0.0"}),
    "apple.media_device_activity": ("apple_media_device_activity", {"1.0.0"}),
}
GOOGLE_MODEL = re.compile(r"(?<![\w,])iPhone[0-9]+_[0-9]+(?![\w,])")
APPLE_ABSENCE = {"", "n/a", "not available", "not applicable", "null", "none", "-"}


@dataclass(frozen=True)
class Field:
    value: JSONValue
    locator: str
    name: str


def present(value: JSONValue, warnings: list[str]) -> bool:
    if value is None or isinstance(value, str) and not value.strip():
        return False
    if isinstance(value, (dict, list)):
        warnings.append("NONSCALAR_FIELD")
        return False
    return True


def direct(context: ObservationContext, name: str) -> Field:
    return Field(context.payload.get(name), child_locator(context.source_locator, name), name)


def meta_fields(context: ObservationContext, names: tuple[str, ...]) -> list[Field]:
    """Explicit root/map fields, then validated parser annotations; no recursive scan."""
    fields = [direct(context, name) for name in names if name in context.payload]
    mapping = context.payload.get("string_map_data")
    if isinstance(mapping, dict):
        for label in sorted(mapping):
            item = mapping[label]
            if label.lower().replace(" ", "_") in names and isinstance(item, dict):
                locator = child_locator(
                    child_locator(context.source_locator, "string_map_data"), label
                )
                fields.append(Field(item.get("value"), child_locator(locator, "value"), label))
    for annotation in context.annotations:
        if annotation.get("kind") != "observed_field" or annotation.get("field") not in names:
            continue
        annotation_locator = annotation.get("source_locator")
        name = annotation.get("field")
        if not isinstance(annotation_locator, str) or not isinstance(name, str):
            raise ValueError("INVALID_FIELD_ANNOTATION")
        value = annotation.get("value")
        if json_text(field_value(context, annotation_locator)) != json_text(value):
            raise ValueError("FIELD_ANNOTATION_MISMATCH")
        fields.append(Field(value, annotation_locator, name))
    # One occurrence represented twice (payload plus annotation) is still one field.
    unique: dict[str, Field] = {}
    for field in fields:
        unique.setdefault(field.locator, field)
    return list(unique.values())


def device_facts(context: ObservationContext, warnings: list[str]) -> list[DeviceDraft]:
    platform = context.parser_id.split(".")[0]
    facts: list[DeviceDraft] = []

    def add(field: Field, namespace: str, kind: str) -> None:
        if present(field.value, warnings):
            facts.append(
                DeviceDraft(platform, kind, namespace, field.value, field.locator, field.name)
            )

    if platform == "meta":
        for field in meta_fields(context, ("device_id", "device_identifier")):
            add(field, "meta.device_id", "identifier")
        seen: set[tuple[str, str]] = set()
        for annotation in context.annotations:
            if annotation.get("kind") != "model_code_from_user_agent":
                continue
            locator, value = annotation.get("source_locator"), annotation.get("value")
            if not isinstance(locator, str) or not isinstance(value, str) or not value:
                raise ValueError("INVALID_MODEL_ANNOTATION")
            source = field_value(context, locator)
            if not isinstance(source, str) or value not in source:
                raise ValueError("MODEL_ANNOTATION_MISMATCH")
            if (locator, value) not in seen:
                add(Field(value, locator, "user_agent"), "meta.user_agent.model_code", "model")
                seen.add((locator, value))
    elif context.parser_id == "google.subscriber_info":
        field = direct(context, "Raw User Agents")
        if isinstance(field.value, str):
            # Distinct tokens in first-occurrence order within this one field only.
            for token in dict.fromkeys(GOOGLE_MODEL.findall(field.value)):
                add(
                    Field(token, field.locator, field.name), "google.user_agent.model_code", "model"
                )
    elif platform == "apple":
        rules = {
            "apple.device_inventory": (
                ("Device Serial Number", "apple.serial_number", "identifier"),
                ("Device IMEI", "apple.imei", "identifier"),
                ("Device MEID", "apple.meid", "identifier"),
                ("Device Model Name", "apple.hardware_model", "model"),
            ),
            "apple.sign_on_activity": (
                ("Device Identifier", "apple.device_identifier", "identifier"),
            ),
            "apple.media_device_activity": (
                ("Device Identifier", "apple.device_identifier", "identifier"),
                ("Device Hardware Model", "apple.hardware_model", "model"),
            ),
        }
        for name, namespace, kind in rules[context.parser_id]:
            field = direct(context, name)
            if isinstance(field.value, str) and field.value.strip().casefold() in APPLE_ABSENCE:
                continue
            add(field, namespace, kind)
    return facts


def network_facts(context: ObservationContext, warnings: list[str]) -> list[NetworkDraft]:
    platform = context.parser_id.split(".")[0]
    if platform == "meta":
        fields, role = meta_fields(context, ("ip", "ip_address")), "meta.activity_ip"
    else:
        name, role = {
            "google.subscriber_info": ("IP Address", "google.activity_ip"),
            "google.change_history": ("IP Address", "google.change_ip"),
            "apple.device_inventory": ("Device Last Heartbeat IP", "apple.heartbeat_ip"),
            "apple.sign_on_activity": ("IP Address", "apple.signon_ip"),
            "apple.media_device_activity": ("IP", "apple.media_ip"),
        }[context.parser_id]
        fields = [direct(context, name)]
    facts = []
    for field in fields:
        if not present(field.value, warnings):
            continue
        canonical = None
        version = None
        try:
            # Do not reinterpret numeric scalars as integer-encoded IPv4 addresses.
            if not isinstance(field.value, str):
                raise ValueError("NONSTRING_IP")
            address = ipaddress.ip_address(field.value)
            canonical, version = str(address), address.version
        except ValueError:
            warnings.append("INVALID_IP_SYNTAX")
        facts.append(
            NetworkDraft(platform, role, field.value, canonical, version, field.locator, field.name)
        )
    return facts


@dataclass(frozen=True)
class TechnicalObserver:
    observer_id: str
    observer_version: str = "1.0.0"

    def supports(self, parser_id: str, parser_version: str, record_type: str) -> bool:
        contract = CONTRACTS.get(parser_id)
        return bool(contract and record_type == contract[0] and parser_version in contract[1])

    def observe(self, context: ObservationContext) -> ObservationResult:
        if not self.supports(context.parser_id, context.parser_version, context.record_type):
            raise ValueError("UNSUPPORTED_OBSERVATION_CONTRACT")
        warnings: list[str] = []
        if self.observer_id == "device.observer":
            facts = tuple(device_facts(context, warnings))
        elif self.observer_id == "network.observer":
            return ObservationResult(tuple(network_facts(context, warnings)), tuple(warnings))
        else:
            raise ValueError("UNKNOWN_OBSERVER")
        return ObservationResult(facts, tuple(warnings))


OBSERVERS: tuple[Observer, ...] = (
    TechnicalObserver("device.observer"),
    TechnicalObserver("network.observer"),
)
