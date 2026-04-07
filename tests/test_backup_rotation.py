"""Tests for backup rotation in FileSyncer._copy_file().

Ensures that .bak always holds the most recent backup, and older backups
are rotated to .bak.<timestamp> using the .bak file's mtime.
"""

import os
import tempfile
from collections.abc import Generator
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from dotconfig_hub.sync import FileSyncer


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def syncer() -> FileSyncer:
    """Create a FileSyncer with a dummy config (config is unused by _copy_file)."""
    with patch("dotconfig_hub.sync.Config"):
        return FileSyncer.__new__(FileSyncer)


@pytest.fixture(autouse=True)
def _setup_syncer(syncer: FileSyncer) -> None:
    """Attach a Console to the syncer so print calls don't fail."""
    from rich.console import Console

    syncer.console = Console()


class TestCopyFileBackup:
    """Test _copy_file backup creation and rotation."""

    def test_first_backup_creates_bak(self, syncer: FileSyncer, temp_dir: Path) -> None:
        """First sync creates .bak when no backup exists yet."""
        src = temp_dir / "src.txt"
        dst = temp_dir / "dst.txt"
        src.write_text("new content")
        dst.write_text("old content")

        syncer._copy_file(src, dst)

        bak = temp_dir / "dst.txt.bak"
        assert bak.exists()
        assert bak.read_text() == "old content"
        assert dst.read_text() == "new content"

    def test_no_timestamped_bak_on_first_backup(
        self, syncer: FileSyncer, temp_dir: Path
    ) -> None:
        """First sync should not create any timestamped .bak file."""
        src = temp_dir / "src.txt"
        dst = temp_dir / "dst.txt"
        src.write_text("new")
        dst.write_text("old")

        syncer._copy_file(src, dst)

        timestamped = [f for f in temp_dir.iterdir() if ".bak." in f.name]
        assert timestamped == []

    def test_rotation_moves_old_bak_to_timestamped(
        self, syncer: FileSyncer, temp_dir: Path
    ) -> None:
        """Second sync rotates existing .bak to .bak.<timestamp>."""
        src = temp_dir / "src.txt"
        dst = temp_dir / "dst.txt"
        bak = temp_dir / "dst.txt.bak"

        # Simulate state after first sync
        src.write_text("v3")
        dst.write_text("v2")
        bak.write_text("v1")

        syncer._copy_file(src, dst)

        # .bak should now hold v2 (the previous dst content)
        assert bak.read_text() == "v2"
        # dst should hold v3
        assert dst.read_text() == "v3"
        # A timestamped file should exist with v1
        timestamped = [f for f in temp_dir.iterdir() if ".bak." in f.name]
        assert len(timestamped) == 1
        assert timestamped[0].read_text() == "v1"

    def test_rotated_filename_uses_bak_mtime(
        self, syncer: FileSyncer, temp_dir: Path
    ) -> None:
        """Rotated .bak filename timestamp matches the .bak file's mtime."""
        src = temp_dir / "src.txt"
        dst = temp_dir / "dst.txt"
        bak = temp_dir / "dst.txt.bak"

        src.write_text("new")
        dst.write_text("current")
        bak.write_text("old")

        # Set a known mtime on the .bak file
        known_mtime = datetime(2026, 1, 15, 10, 30, 0).timestamp()
        os.utime(bak, (known_mtime, known_mtime))

        syncer._copy_file(src, dst)

        expected_name = "dst.txt.bak.20260115_103000"
        rotated = [f for f in temp_dir.iterdir() if ".bak." in f.name]
        assert len(rotated) == 1
        assert rotated[0].name == expected_name

    def test_bak_always_holds_latest_backup(
        self, syncer: FileSyncer, temp_dir: Path
    ) -> None:
        """After multiple syncs, .bak always contains the previous dst content."""
        src = temp_dir / "src.txt"
        dst = temp_dir / "dst.txt"
        bak = temp_dir / "dst.txt.bak"

        # First sync: v1 -> v2
        dst.write_text("v1")
        src.write_text("v2")
        syncer._copy_file(src, dst)
        assert bak.read_text() == "v1"

        # Set distinct mtime so rotation produces a unique timestamp
        mtime_1 = datetime(2026, 3, 1, 12, 0, 0).timestamp()
        os.utime(bak, (mtime_1, mtime_1))

        # Second sync: v2 -> v3
        src.write_text("v3")
        syncer._copy_file(src, dst)
        assert bak.read_text() == "v2"

        mtime_2 = datetime(2026, 3, 2, 12, 0, 0).timestamp()
        os.utime(bak, (mtime_2, mtime_2))

        # Third sync: v3 -> v4
        src.write_text("v4")
        syncer._copy_file(src, dst)
        assert bak.read_text() == "v3"

        # Should have 2 timestamped backups (v1 and v2)
        timestamped = sorted(f for f in temp_dir.iterdir() if ".bak." in f.name)
        assert len(timestamped) == 2
        assert timestamped[0].read_text() == "v1"
        assert timestamped[1].read_text() == "v2"

    def test_no_backup_when_dst_missing(
        self, syncer: FileSyncer, temp_dir: Path
    ) -> None:
        """No backup is created when destination does not exist."""
        src = temp_dir / "src.txt"
        dst = temp_dir / "dst.txt"
        src.write_text("content")

        syncer._copy_file(src, dst)

        assert dst.read_text() == "content"
        bak_files = [f for f in temp_dir.iterdir() if ".bak" in f.name]
        assert bak_files == []

    def test_no_backup_when_disabled(self, syncer: FileSyncer, temp_dir: Path) -> None:
        """No backup is created when create_backup=False."""
        src = temp_dir / "src.txt"
        dst = temp_dir / "dst.txt"
        src.write_text("new")
        dst.write_text("old")

        syncer._copy_file(src, dst, create_backup=False)

        assert dst.read_text() == "new"
        bak_files = [f for f in temp_dir.iterdir() if ".bak" in f.name]
        assert bak_files == []

    def test_skip_when_source_missing(self, syncer: FileSyncer, temp_dir: Path) -> None:
        """Returns False and does not modify dst when source is missing."""
        src = temp_dir / "nonexistent.txt"
        dst = temp_dir / "dst.txt"
        dst.write_text("original")

        result = syncer._copy_file(src, dst)

        assert result is False
        assert dst.read_text() == "original"
