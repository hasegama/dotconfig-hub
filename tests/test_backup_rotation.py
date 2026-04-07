"""Tests for timestamped backup in FileSyncer._copy_file().

Ensures that each sync creates a .bak.<timestamp> backup file
with the current time, preserving a full history of backups.
"""

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
    """Test _copy_file timestamped backup creation."""

    def test_backup_creates_timestamped_file(
        self, syncer: FileSyncer, temp_dir: Path
    ) -> None:
        """Sync creates a .bak.<timestamp> backup of the destination."""
        src = temp_dir / "src.txt"
        dst = temp_dir / "dst.txt"
        src.write_text("new content")
        dst.write_text("old content")

        syncer._copy_file(src, dst)

        bak_files = [f for f in temp_dir.iterdir() if ".bak." in f.name]
        assert len(bak_files) == 1
        assert bak_files[0].read_text() == "old content"
        assert dst.read_text() == "new content"

    def test_no_plain_bak_created(self, syncer: FileSyncer, temp_dir: Path) -> None:
        """No plain .bak file (without timestamp) should be created."""
        src = temp_dir / "src.txt"
        dst = temp_dir / "dst.txt"
        src.write_text("new")
        dst.write_text("old")

        syncer._copy_file(src, dst)

        plain_bak = temp_dir / "dst.txt.bak"
        assert not plain_bak.exists()

    def test_backup_filename_contains_timestamp(
        self, syncer: FileSyncer, temp_dir: Path
    ) -> None:
        """Backup filename includes a timestamp matching the current time."""
        src = temp_dir / "src.txt"
        dst = temp_dir / "dst.txt"
        src.write_text("new")
        dst.write_text("old")

        fake_now = datetime(2026, 4, 7, 15, 30, 0)
        with patch("dotconfig_hub.sync.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.fromtimestamp = datetime.fromtimestamp
            syncer._copy_file(src, dst)

        expected = temp_dir / "dst.txt.bak.20260407_153000"
        assert expected.exists()
        assert expected.read_text() == "old"

    def test_multiple_syncs_create_separate_backups(
        self, syncer: FileSyncer, temp_dir: Path
    ) -> None:
        """Each sync creates a distinct timestamped backup."""
        src = temp_dir / "src.txt"
        dst = temp_dir / "dst.txt"

        times = [
            datetime(2026, 3, 1, 12, 0, 0),
            datetime(2026, 3, 2, 12, 0, 0),
            datetime(2026, 3, 3, 12, 0, 0),
        ]

        for i, fake_now in enumerate(times):
            dst.write_text(f"v{i + 1}")
            src.write_text(f"v{i + 2}")
            with patch("dotconfig_hub.sync.datetime") as mock_dt:
                mock_dt.now.return_value = fake_now
                mock_dt.fromtimestamp = datetime.fromtimestamp
                syncer._copy_file(src, dst)

        bak_files = sorted(f for f in temp_dir.iterdir() if ".bak." in f.name)
        assert len(bak_files) == 3
        assert bak_files[0].read_text() == "v1"
        assert bak_files[1].read_text() == "v2"
        assert bak_files[2].read_text() == "v3"

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
