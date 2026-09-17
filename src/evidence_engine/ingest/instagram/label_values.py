"""Explicit Meta array shapes; raw values and unknown fields stay in the item payload."""

import ipaddress
import re

from evidence_engine.ingest.parsing.framework import Diagnostic, JSONValue, child_locator

# Exact schema labels, including observed textual variants. No input text repair.
PROFILE_LABELS = {
    "Tipo": "event_type",
    "App": "application",
    "Idioma": "language",
    "Cookie": "cookie",
    "Endere\u00c3\u00a7o IP": "ip_address",
    "N\u00c3\u00bamero da porta": "port",
    "Agente de usu\u00c3\u00a1rio": "user_agent",
    "Identifica\u00c3\u00a7\u00c3\u00a3o do dispositivo": "device_id",
    "Vers\u00c3\u00a3o do app": "application_version",
    "\u00c3\u009altimo login": "last_login",
    "Endereço IP": "ip_address",
    "Número da porta": "port",
    "Agente de usuário": "user_agent",
    "Identificação do dispositivo": "device_id",
    "Versão do app": "application_version",
    "Último login": "last_login",
}
DETAIL_LABELS = {
    "Tipo": "profile_field",
    "Novo valor": "new_value",
    "Valor anterior": "previous_value",
    "Localiza\u00c3\u00a7\u00c3\u00a3o": "location",
    "Localização": "location",
}
DELETED_LABELS = {
    "Publicado": "published",
    "Legenda": "caption",
    "T\u00c3\u00adtulo": "title",
    "Título": "title",
    "Identificador de carregamento": "upload_id",
    "Identificador de rascunho": "draft_id",
    "Data/hora de cria\u00c3\u00a7\u00c3\u00a3o": "creation_timestamp",
    "Data/hora de criação": "creation_timestamp",
    "Hor\u00c3\u00a1rio da atualiza\u00c3\u00a7\u00c3\u00a3o": "updated_timestamp",
    "Horário da atualização": "updated_timestamp",
    "Hora de expira\u00c3\u00a7\u00c3\u00a3o": "expiration_timestamp",
    "Hora de expiração": "expiration_timestamp",
}
TIMED_LABELS = {"last_login", "creation_timestamp", "updated_timestamp", "expiration_timestamp"}


def observe_labels(
    entries: list[JSONValue], locator: str, *, profile: bool
) -> tuple[list[dict[str, JSONValue]], list[Diagnostic]]:
    annotations: list[dict[str, JSONValue]] = []
    warnings: list[Diagnostic] = []
    handled_containers: set[str] = set()

    def warn(path: str, code: str = "UNKNOWN_LABEL_STRUCTURE") -> None:
        warnings.append(Diagnostic(code, path))

    def scalar(field: str, value: JSONValue, path: str) -> None:
        if isinstance(value, (list, dict)):
            warn(path)
            return
        annotations.append(
            {"kind": "observed_field", "field": field, "value": value, "source_locator": path}
        )
        if field in TIMED_LABELS and isinstance(value, bool):
            warn(path, "TIMESTAMP_UNRECOGNIZED")
        if profile and field == "ip_address" and value is not None:
            try:
                if not isinstance(value, str):
                    raise ValueError
                address = ipaddress.ip_address(value)
                annotations.append(
                    {"kind": "ip_syntax", "source_locator": path, "version": address.version}
                )
            except ValueError:
                warn(path, "INVALID_IP_SYNTAX")
        if profile and field == "user_agent" and isinstance(value, str):
            for code in sorted(set(re.findall(r"\biPhone[0-9]+,[0-9]+\b", value))):
                annotations.append(
                    {"kind": "model_code_from_user_agent", "value": code, "source_locator": path}
                )

    def labels(items: list[JSONValue], path: str, mapping: dict[str, str]) -> None:
        seen: set[str] = set()
        for index, entry in enumerate(items):
            entry_path = child_locator(path, index)
            if entry_path in handled_containers:
                continue
            if not isinstance(entry, dict):
                warn(entry_path)
                continue
            label = entry.get("label")
            field = mapping.get(label) if isinstance(label, str) else None
            if field is None:
                warn(entry_path, "UNKNOWN_LABEL")
                continue
            if field in seen:
                warn(entry_path, "DUPLICATE_LABEL")
            seen.add(field)
            container = "timestamp_value" if field in TIMED_LABELS else "value"
            for key in entry:
                if key not in {"label", container}:
                    warn(child_locator(entry_path, key))
            if container in entry:
                scalar(field, entry[container], child_locator(entry_path, container))
            else:
                warn(entry_path, "LABEL_VALUE_ABSENT")

    def media(items: JSONValue, path: str) -> None:
        if not isinstance(items, list):
            warn(path)
            return
        for index, item in enumerate(items):
            item_path = child_locator(path, index)
            if not isinstance(item, dict):
                warn(item_path)
                continue
            for key, value in item.items():
                key_path = child_locator(item_path, key)
                if key in {"uri", "creation_timestamp", "title"}:
                    scalar(key, value, key_path)
                elif key == "media_metadata":
                    if not isinstance(value, dict):
                        warn(key_path)
                        continue
                    for kind, metadata in value.items():
                        kind_path = child_locator(key_path, kind)
                        if kind not in {"photo_metadata", "video_metadata"}:
                            warn(kind_path, "UNSUPPORTED_MEDIA_METADATA")
                            continue
                        if not isinstance(metadata, dict):
                            warn(kind_path)
                            continue
                        for name in metadata:
                            if name != "exif_data":
                                warn(child_locator(kind_path, name))
                        exif = metadata.get("exif_data")
                        exif_path = child_locator(kind_path, "exif_data")
                        if not isinstance(exif, list):
                            warn(kind_path)
                            continue
                        for offset, data in enumerate(exif):
                            data_path = child_locator(exif_path, offset)
                            if not isinstance(data, dict):
                                warn(data_path)
                                continue
                            for name, raw in data.items():
                                raw_path = child_locator(data_path, name)
                                if name in {
                                    "device_id",
                                    "camera_position",
                                    "software",
                                    "source_type",
                                }:
                                    scalar(name, raw, raw_path)
                                else:
                                    warn(raw_path)
                else:
                    warn(key_path, "UNSUPPORTED_MEDIA_FIELD")

    mapping = PROFILE_LABELS if profile else DELETED_LABELS
    # Only these named containers have semantics; unknown/title-only dicts stay opaque.
    for index, entry in enumerate(entries):
        path = child_locator(locator, index)
        if not isinstance(entry, dict):
            continue
        label = entry.get("label")
        container = (
            "dict"
            if (profile and label == "Detalhes") or (not profile and label == "Metadados")
            else "media"
            if not profile and isinstance(label, str) and label in {"Mídia", "M\u00c3\u00addia"}
            else None
        )
        if container is None:
            continue
        handled_containers.add(path)
        for key in entry:
            if key not in {"label", container}:
                warn(child_locator(path, key))
        nested = entry.get(container)
        nested_path = child_locator(path, container)
        if container == "media":
            media(nested, nested_path)
        elif isinstance(nested, list):
            labels(nested, nested_path, DETAIL_LABELS if profile else {"duration": "duration"})
        else:
            warn(path)
    labels(entries, locator, mapping)
    return annotations, warnings
