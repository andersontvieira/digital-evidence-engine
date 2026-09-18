"""Three static contracts. Copy explicit scalars; never join observations."""

from dataclasses import dataclass

from evidence_engine.ingest.parsing.framework import JSONValue, json_text
from evidence_engine.normalization.framework import (
    EventDraft,
    NormalizationResult,
    Normalizer,
    NormalizerContext,
)
from evidence_engine.normalization.time import normalize_google_time, normalize_time

# parser_id -> (record_type, event_kind, accepted parser versions)
CONTRACTS = {
    "meta.profile_activity": ("profile_activity", "account.profile_activity", {"1.0.0", "1.1.0"}),
    "meta.recently_deleted_content": (
        "recently_deleted_content",
        "content.activity",
        {"1.0.0", "1.1.0"},
    ),
    "meta.instagram_messages": ("instagram_message", "communication.message", {"1.0.0"}),
    "google.subscriber_info": ("google_security_activity", "account.security_activity", {"1.0.0"}),
    "google.change_history": ("google_account_change", "account.change", {"1.0.0"}),
    "apple.sign_on_activity": ("apple_sign_on_activity", "account.sign_on", {"1.0.0"}),
    "apple.media_device_activity": ("apple_media_device_activity", "media.activity", {"1.0.0"}),
}


def select_scalar(values: list[JSONValue], warnings: list[str]) -> JSONValue:
    scalars = [v for v in values if v is not None and not isinstance(v, (dict, list))]
    if len(scalars) != len([v for v in values if v is not None]):
        warnings.append("NONSCALAR_FIELD")
    unique = {json_text(v): v for v in scalars}
    if len(unique) > 1:
        warnings.append("AMBIGUOUS_FIELD")
        return None
    return next(iter(unique.values()), None)


def meta_values(context: NormalizerContext, names: set[str]) -> list[JSONValue]:
    values = [value for key, value in context.payload.items() if key in names]
    values.extend(
        annotation.get("value")
        for annotation in context.annotations
        if annotation.get("kind") == "observed_field" and annotation.get("field") in names
    )
    mapping = context.payload.get("string_map_data")
    if isinstance(mapping, dict):
        for label, item in mapping.items():
            if label.lower().replace(" ", "_") in names and isinstance(item, dict):
                values.append(item.get("value"))
    return values


def meta_epoch_unit(context: NormalizerContext) -> str | None:
    """Select units by named source fields, never by the number's magnitude."""
    if type(context.timestamp_raw) is not int:
        return None
    units = []
    for key, unit in (
        ("timestamp", "seconds"),
        ("timestamp_ms", "milliseconds"),
        ("creation_timestamp", "seconds"),
    ):
        if key in context.payload and json_text(context.payload[key]) == json_text(
            context.timestamp_raw
        ):
            units.append(unit)
    # Unknown or competing time roles are not reinterpreted from annotations.
    return units[0] if len(units) == 1 else None


@dataclass(frozen=True)
class PlatformNormalizer:
    platform: str
    normalizer_version: str = "1.0.0"

    @property
    def normalizer_id(self) -> str:
        return self.platform + ".event_normalizer"

    def supports(self, parser_id: str, parser_version: str, record_type: str) -> bool:
        contract = CONTRACTS.get(parser_id)
        return bool(
            contract
            and parser_id.startswith(self.platform + ".")
            and record_type == contract[0]
            and parser_version in contract[2]
        )

    def normalize(self, context: NormalizerContext) -> NormalizationResult:
        if not self.supports(context.parser_id, context.parser_version, context.record_type):
            raise ValueError("UNSUPPORTED_NORMALIZATION_CONTRACT")
        warnings: list[str] = []
        raw = context.payload
        fields: list[JSONValue]
        if self.platform == "meta":
            fields = [
                select_scalar(meta_values(context, names), warnings)
                for names in (
                    {"ip", "ip_address"},
                    {"device_id", "device_identifier"},
                    {"model", "device_model"},
                    {"action", "event", "event_type"},
                    {"status"},
                )
            ]
        elif self.platform == "google":
            fields = [
                raw.get("IP Address"),
                None,
                None,
                raw.get(
                    "Activity Type"
                    if context.parser_id == "google.subscriber_info"
                    else "Change Type"
                ),
                None,
            ]
        elif context.parser_id == "apple.sign_on_activity":
            fields = [
                raw.get("IP Address"),
                raw.get("Device Identifier"),
                None,
                None,
                raw.get("Signon Status"),
            ]
        else:
            fields = [
                raw.get("IP"),
                raw.get("Device Identifier"),
                raw.get("Device Hardware Model"),
                raw.get("Event Type"),
                None,
            ]
        if self.platform in {"meta", "google"}:
            # Copy only codes already projected by the parser. Do not scan user agents.
            models = [
                a.get("value")
                for a in context.annotations
                if a.get("kind") == "model_code_from_user_agent"
            ]
            fields[2] = select_scalar([fields[2], *models], warnings)
        fields = [select_scalar([value], warnings) for value in fields]
        time = normalize_time(
            context.timestamp_raw, meta_epoch_unit(context) if self.platform == "meta" else None
        )
        if self.platform == "google" and self.normalizer_version == "1.1.0":
            time = normalize_google_time(context.timestamp_raw)
        if time.status == "raw_only":
            warnings.append("TIMESTAMP_RAW_ONLY")
        return NormalizationResult(
            EventDraft(
                self.platform,
                CONTRACTS[context.parser_id][1],
                time.utc,
                time.status,
                time.basis,
                *fields,
            ),
            tuple(warnings),
        )


NORMALIZERS: tuple[Normalizer, ...] = (
    PlatformNormalizer("meta"),
    PlatformNormalizer("google", "1.1.0"),
    PlatformNormalizer("apple"),
)
