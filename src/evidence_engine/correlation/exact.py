"""One static correlator, two exact rules, explicitly selected observer versions."""

import hashlib
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from evidence_engine.ingest.parsing.framework import json_text
from evidence_engine.models.entities import DeviceObservation, NetworkObservation

CORRELATOR_ID = "exact_match.correlator"
CORRELATOR_VERSION = "1.0.0"
RULE_VERSION = "1.0.0"
DEVICE_RULE = "device.exact_namespace_value"
NETWORK_RULE = "network.exact_canonical_ip"
type Observation = DeviceObservation | NetworkObservation


@dataclass(frozen=True)
class CandidateGroup:
    candidate_kind: str
    rule_id: str
    rule_version: str
    key_digest: str
    observations: tuple[Observation, ...]


def observation_key(observation: Observation) -> tuple[str, str, str] | None:
    """Return kind, rule and versioned key JSON; never decode/normalize device raw."""
    if isinstance(observation, DeviceObservation):
        if (observation.observer_id, observation.observer_version) != ("device.observer", "1.0.0"):
            return None
        kind, rule = "device", DEVICE_RULE
        fields: list[object] = [observation.fact_kind, observation.namespace, observation.value_raw]
    else:
        if (observation.observer_id, observation.observer_version) != ("network.observer", "1.0.0"):
            return None
        if observation.ip_canonical is None or observation.ip_version not in (4, 6):
            return None
        kind, rule = "network", NETWORK_RULE
        fields = [observation.ip_version, observation.ip_canonical]
    return kind, rule, json_text(["exact-match-key", 1, rule, RULE_VERSION, *fields])


def exact_groups(observations: Iterable[Observation]) -> tuple[CandidateGroup, ...]:
    buckets: dict[tuple[str, str, str], list[Observation]] = defaultdict(list)
    for observation in observations:
        key = observation_key(observation)
        if key is not None:
            buckets[key].append(observation)
    groups = []
    digests: set[str] = set()
    for (kind, rule, key_json), members in sorted(buckets.items()):
        if len(members) < 2:
            continue
        digest = hashlib.sha256(key_json.encode("utf-8")).hexdigest()
        if digest in digests:
            raise ValueError("KEY_DIGEST_COLLISION")
        digests.add(digest)
        ordered = tuple(
            sorted(members, key=lambda o: (o.parsed_record_id, o.observation_ordinal, o.id))
        )
        groups.append(CandidateGroup(kind, rule, RULE_VERSION, digest, ordered))
    return tuple(groups)
