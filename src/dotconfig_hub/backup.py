"""Backup file management for dotconfig-hub.

Centralizes the naming convention of timestamped backup files
(``<name>.bak.<YYYYMMDD_HHMMSS>``) and the operations on them.

Design notes:
- FileSyncer (sync.py) creates backups via :func:`make_backup_path` using a
  single per-session timestamp, so every backup produced by one sync run
  shares the same suffix. This makes a timestamp act as a "version" that
  the ``rollback`` command can restore atomically.
- The ``clean`` and ``rollback`` CLI commands (cli.py) operate through
  :class:`BackupManager`, scoped to a single root directory (Hub or
  Project) so each side can be managed independently.
"""

import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

# Timestamp format shared by all backup suffixes (e.g. 20260612_153000)
BACKUP_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"

# Matches "<original>.bak.<YYYYMMDD_HHMMSS>". Plain "*.bak" files are
# intentionally NOT matched: they may be manual backups made by the user,
# while the timestamped form is only ever produced by dotconfig-hub.
BACKUP_NAME_PATTERN = re.compile(r"^(?P<original>.+)\.bak\.(?P<timestamp>\d{8}_\d{6})$")

# Directories that are never scanned for backup files
SKIP_DIR_NAMES = frozenset({".git", ".venv", "node_modules", "__pycache__"})


def make_backup_path(path: Path, timestamp: str) -> Path:
    """Return the backup path for ``path`` with the given timestamp.

    Example: ``ci.yml`` + ``20260612_153000`` -> ``ci.yml.bak.20260612_153000``
    """
    return path.with_suffix(f"{path.suffix}.bak.{timestamp}")


def original_path(backup: Path) -> Path:
    """Return the original file path that ``backup`` was created from.

    Raises
    ------
        ValueError: If ``backup`` does not follow the backup naming
            convention.

    """
    match = BACKUP_NAME_PATTERN.match(backup.name)
    if match is None:
        message = f"Not a dotconfig-hub backup file: {backup}"
        raise ValueError(message)
    return backup.with_name(match.group("original"))


class BackupManager:
    """Discover, clean and roll back timestamped backup files under a root.

    The root is either the Hub (templates source) or a Project directory,
    so each side can be cleaned / rolled back independently.
    """

    def __init__(self, root: Path) -> None:
        """Initialize the manager.

        Args:
        ----
            root: Directory to scan recursively for backup files.

        """
        self.root = root

    def find_backups(self) -> Dict[str, List[Path]]:
        """Find all backup files under the root, grouped by timestamp.

        Returns
        -------
            Mapping of timestamp (version) to the backup file paths that
            share it, each list sorted for stable display.

        """
        grouped: Dict[str, List[Path]] = {}
        for dirpath, dirnames, filenames in os.walk(self.root):
            # Prune ignored directories in-place so os.walk skips them
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES]
            for name in filenames:
                match = BACKUP_NAME_PATTERN.match(name)
                if match:
                    grouped.setdefault(match.group("timestamp"), []).append(
                        Path(dirpath) / name
                    )
        for paths in grouped.values():
            paths.sort()
        return grouped

    def list_versions(self) -> List[str]:
        """Return available backup timestamps, newest first."""
        return sorted(self.find_backups(), reverse=True)

    def clean(self, dry_run: bool = False) -> List[Path]:
        """Delete every backup file under the root.

        Args:
        ----
            dry_run: If True, only report what would be deleted.

        Returns:
        -------
            The backup file paths that were (or would be) deleted.

        """
        removed: List[Path] = []
        for _timestamp, paths in sorted(self.find_backups().items()):
            for path in paths:
                if not dry_run:
                    path.unlink()
                removed.append(path)
        return removed

    def rollback(self, timestamp: str) -> List[Tuple[Path, Path]]:
        """Restore all files backed up with ``timestamp`` under the root.

        For each backup of the selected version:
        1. The current file (if it exists) is preserved as a new backup
           stamped with the rollback execution time, so the pre-rollback
           state itself becomes a selectable version.
        2. The selected backup content is copied back to the original
           path. The backup file is kept so the same version remains
           selectable later.

        Args:
        ----
            timestamp: Version suffix to restore (``YYYYMMDD_HHMMSS``).

        Returns:
        -------
            List of ``(backup, original)`` pairs that were restored.

        Raises:
        ------
            KeyError: If no backup files carry ``timestamp``.

        """
        backups = self.find_backups()[timestamp]
        # Single timestamp for the whole rollback so the displaced files
        # also form one consistent version (same rule as sync sessions).
        displaced_ts = datetime.now().strftime(BACKUP_TIMESTAMP_FORMAT)
        restored: List[Tuple[Path, Path]] = []
        for backup in backups:
            original = original_path(backup)
            if original.exists():
                shutil.copy2(original, make_backup_path(original, displaced_ts))
            shutil.copy2(backup, original)
            restored.append((backup, original))
        return restored
