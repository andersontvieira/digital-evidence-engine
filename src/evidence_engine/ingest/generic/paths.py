"""Conservative local path policy; no links or special files are accepted."""

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from evidence_engine.errors import EvidenceError


def sync_directory(path: Path) -> None:
    """Persist directory entries on the canonical POSIX runtime before DB commit."""
    if os.name != "posix":
        return
    check_path(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def check_path(path: Path) -> None:
    """Check every existing component, including Windows directory junctions."""
    for component in (path, *path.parents):
        if component.is_symlink() or component.is_junction():
            raise EvidenceError("Links and junctions are not allowed in case paths")
        if component.exists():
            info = component.stat()
            if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                raise EvidenceError("Special files are not allowed in case paths")
            if stat.S_ISREG(info.st_mode) and info.st_nlink > 1:
                raise EvidenceError("Hard-linked case files are not allowed")


@dataclass(frozen=True)
class CasePaths:
    root: Path
    originals: Path
    working: Path
    database: Path
    output: Path

    @property
    def db_file(self) -> Path:
        return self.database / "evidence.db"

    @classmethod
    def load(cls, root: Path, *, create: bool = False) -> "CasePaths":
        root = root.absolute()
        check_path(root)
        root = root.resolve(strict=True)
        if not root.is_dir():
            raise EvidenceError("Case root must be an existing directory")
        if any((parent / ".git").exists() for parent in (root, *root.parents)):
            raise EvidenceError("Case data must be outside Git repositories")
        # Also protect installed editable source trees without visible .git metadata.
        source_root = Path(__file__).resolve().parents[4]
        if (source_root / "pyproject.toml").exists() and root.is_relative_to(source_root):
            raise EvidenceError("Case data must be outside the project")
        areas = [root / name for name in ("originals", "working", "database", "output")]
        for area in areas:
            check_path(area)
            if area.exists() and not area.is_dir():
                raise EvidenceError("Case areas must be directories")
        if not areas[0].is_dir():
            raise EvidenceError("The originals directory must already exist")
        resolved = [area.resolve() for area in areas]
        for i, left in enumerate(resolved):
            for right in resolved[i + 1 :]:
                if left.is_relative_to(right) or right.is_relative_to(left):
                    raise EvidenceError("Case areas must not overlap")
                if left.exists() and right.exists() and left.samefile(right):
                    raise EvidenceError("Case areas must not alias each other")
        for area in areas[1:]:
            if create:
                area.mkdir(exist_ok=True)
            elif not area.is_dir():
                raise EvidenceError("Case is not initialized; run evidence ingest first")
        result = cls(root, *areas)
        for name in ("evidence.db", "evidence.db-journal", "evidence.db-wal", "evidence.db-shm"):
            check_path(result.database / name)
        return result


def discover(originals: Path) -> list[Path]:
    """Sorted inventory; reject links instead of silently omitting them."""
    files: list[Path] = []

    def visit(directory: Path) -> None:
        check_path(directory)
        for path in sorted(directory.iterdir()):
            check_path(path)
            mode = path.lstat().st_mode
            if stat.S_ISDIR(mode):
                visit(path)
            elif stat.S_ISREG(mode):
                files.append(path)
            else:
                raise EvidenceError("Special files are not accepted in originals")

    visit(originals)
    return sorted(files, key=lambda path: path.relative_to(originals).as_posix())
