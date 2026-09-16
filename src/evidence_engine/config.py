"""Explicit limits; case paths are validated separately before any write."""

from pydantic import BaseModel, ConfigDict, Field


class ZipLimits(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_file_bytes: int = Field(default=512 * 1024 * 1024, gt=0)
    max_total_bytes: int = Field(default=2 * 1024 * 1024 * 1024, gt=0)
    max_members: int = Field(default=10_000, gt=0)
    max_ratio: float = Field(default=200.0, ge=1, allow_inf_nan=False)
