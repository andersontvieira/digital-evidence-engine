"""Errors safe to present without dumping source contents or absolute paths."""


class EvidenceError(Exception):
    """An explicit preservation, validation or integrity failure."""
