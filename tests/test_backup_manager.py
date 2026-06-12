"""Tests for backup.py (BackupManager) and the clean / rollback CLI commands.

Covers:
- Backup naming helpers (make_backup_path / original_path)
- BackupManager.find_backups grouping by timestamp (= version)
- BackupManager.clean (dry-run and actual deletion)
- BackupManager.rollback (restore, displaced-file backup, deleted-file revival)
- Session-level timestamp in FileSyncer (one sync run = one version suffix)
- clean / rollback CLI commands via CliRunner
"""

import tempfile
from collections.abc import Generator
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from dotconfig_hub.backup import (
    BackupManager,
    make_backup_path,
    original_path,
)
from dotconfig_hub.cli import clean, rollback
from dotconfig_hub.sync import FileSyncer


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def runner() -> CliRunner:
    """Create a Click test runner."""
    return CliRunner()


class TestNamingHelpers:
    """Test make_backup_path / original_path round-tripping."""

    def test_make_backup_path_appends_suffix(self) -> None:
        """ci.yml -> ci.yml.bak.<timestamp>."""
        result = make_backup_path(Path("/x/ci.yml"), "20260612_153000")
        assert result == Path("/x/ci.yml.bak.20260612_153000")

    def test_make_backup_path_for_dotfile(self) -> None:
        """.gitignore -> .gitignore.bak.<timestamp>."""
        result = make_backup_path(Path("/x/.gitignore"), "20260612_153000")
        assert result == Path("/x/.gitignore.bak.20260612_153000")

    def test_original_path_round_trip(self) -> None:
        """original_path inverts make_backup_path."""
        original = Path("/x/settings.json")
        backup = make_backup_path(original, "20260612_153000")
        assert original_path(backup) == original

    def test_original_path_rejects_non_backup(self) -> None:
        """A non-backup file name raises ValueError."""
        with pytest.raises(ValueError, match="Not a dotconfig-hub backup file"):
            original_path(Path("/x/settings.json"))


class TestFindBackups:
    """Test BackupManager.find_backups grouping and filtering."""

    def test_groups_by_timestamp(self, temp_dir: Path) -> None:
        """Backups sharing a suffix form one version group."""
        (temp_dir / "a.txt.bak.20260601_120000").write_text("a1")
        (temp_dir / "b.txt.bak.20260601_120000").write_text("b1")
        (temp_dir / "a.txt.bak.20260602_120000").write_text("a2")

        backups = BackupManager(temp_dir).find_backups()

        assert set(backups) == {"20260601_120000", "20260602_120000"}
        assert len(backups["20260601_120000"]) == 2
        assert len(backups["20260602_120000"]) == 1

    def test_recurses_into_subdirectories(self, temp_dir: Path) -> None:
        """Backups in nested directories are found."""
        nested = temp_dir / ".github" / "workflows"
        nested.mkdir(parents=True)
        (nested / "ci.yml.bak.20260601_120000").write_text("ci")

        backups = BackupManager(temp_dir).find_backups()

        assert len(backups["20260601_120000"]) == 1

    def test_ignores_plain_bak_files(self, temp_dir: Path) -> None:
        """Plain .bak files (no timestamp) are not dotconfig-hub backups."""
        (temp_dir / "manual.txt.bak").write_text("manual")

        assert BackupManager(temp_dir).find_backups() == {}

    def test_skips_ignored_directories(self, temp_dir: Path) -> None:
        """Files under .git etc. are never treated as backups."""
        git_dir = temp_dir / ".git"
        git_dir.mkdir()
        (git_dir / "x.txt.bak.20260601_120000").write_text("x")

        assert BackupManager(temp_dir).find_backups() == {}

    def test_list_versions_newest_first(self, temp_dir: Path) -> None:
        """list_versions returns timestamps in descending order."""
        (temp_dir / "a.txt.bak.20260601_120000").write_text("a1")
        (temp_dir / "a.txt.bak.20260603_120000").write_text("a3")
        (temp_dir / "a.txt.bak.20260602_120000").write_text("a2")

        versions = BackupManager(temp_dir).list_versions()

        assert versions == [
            "20260603_120000",
            "20260602_120000",
            "20260601_120000",
        ]


class TestClean:
    """Test BackupManager.clean."""

    def test_clean_removes_all_backups(self, temp_dir: Path) -> None:
        """All timestamped backups are deleted; originals are kept."""
        (temp_dir / "a.txt").write_text("current")
        (temp_dir / "a.txt.bak.20260601_120000").write_text("old1")
        (temp_dir / "a.txt.bak.20260602_120000").write_text("old2")

        removed = BackupManager(temp_dir).clean()

        assert len(removed) == 2
        assert (temp_dir / "a.txt").exists()
        assert not (temp_dir / "a.txt.bak.20260601_120000").exists()
        assert not (temp_dir / "a.txt.bak.20260602_120000").exists()

    def test_clean_dry_run_keeps_files(self, temp_dir: Path) -> None:
        """Dry-run reports targets without deleting them."""
        bak = temp_dir / "a.txt.bak.20260601_120000"
        bak.write_text("old")

        removed = BackupManager(temp_dir).clean(dry_run=True)

        assert removed == [bak]
        assert bak.exists()

    def test_clean_keeps_plain_bak_files(self, temp_dir: Path) -> None:
        """Manual .bak files (no timestamp) survive a clean."""
        manual = temp_dir / "manual.txt.bak"
        manual.write_text("manual")
        (temp_dir / "a.txt.bak.20260601_120000").write_text("old")

        BackupManager(temp_dir).clean()

        assert manual.exists()


class TestRollback:
    """Test BackupManager.rollback."""

    def test_restores_selected_version(self, temp_dir: Path) -> None:
        """The original file is overwritten with the backup content."""
        original = temp_dir / "a.txt"
        original.write_text("current")
        (temp_dir / "a.txt.bak.20260601_120000").write_text("old")

        restored = BackupManager(temp_dir).rollback("20260601_120000")

        assert len(restored) == 1
        assert original.read_text() == "old"

    def test_displaced_file_becomes_new_version(self, temp_dir: Path) -> None:
        """The pre-rollback content is saved as a rollback-time backup."""
        original = temp_dir / "a.txt"
        original.write_text("current")
        (temp_dir / "a.txt.bak.20260601_120000").write_text("old")

        fake_now = datetime(2026, 6, 12, 9, 0, 0)
        with patch("dotconfig_hub.backup.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            BackupManager(temp_dir).rollback("20260601_120000")

        displaced = temp_dir / "a.txt.bak.20260612_090000"
        assert displaced.exists()
        assert displaced.read_text() == "current"

    def test_backup_file_is_kept_after_rollback(self, temp_dir: Path) -> None:
        """The selected version stays selectable after a rollback."""
        (temp_dir / "a.txt").write_text("current")
        bak = temp_dir / "a.txt.bak.20260601_120000"
        bak.write_text("old")

        BackupManager(temp_dir).rollback("20260601_120000")

        assert bak.exists()

    def test_revives_deleted_original(self, temp_dir: Path) -> None:
        """A file deleted via delete-with-backup is restored from its backup."""
        bak = temp_dir / "a.txt.bak.20260601_120000"
        bak.write_text("deleted content")

        BackupManager(temp_dir).rollback("20260601_120000")

        assert (temp_dir / "a.txt").read_text() == "deleted content"

    def test_unknown_version_raises(self, temp_dir: Path) -> None:
        """Requesting a nonexistent version raises KeyError."""
        with pytest.raises(KeyError):
            BackupManager(temp_dir).rollback("19990101_000000")

    def test_rollback_restores_all_files_of_version(self, temp_dir: Path) -> None:
        """Every file sharing the version suffix is restored together."""
        (temp_dir / "a.txt").write_text("a-current")
        (temp_dir / "b.txt").write_text("b-current")
        (temp_dir / "a.txt.bak.20260601_120000").write_text("a-old")
        (temp_dir / "b.txt.bak.20260601_120000").write_text("b-old")

        restored = BackupManager(temp_dir).rollback("20260601_120000")

        assert len(restored) == 2
        assert (temp_dir / "a.txt").read_text() == "a-old"
        assert (temp_dir / "b.txt").read_text() == "b-old"


class TestSessionTimestamp:
    """Backups within one sync session share a single version suffix."""

    def test_copy_file_shares_suffix_within_session(self, temp_dir: Path) -> None:
        """Two backups created in one session get the same timestamp."""
        syncer = FileSyncer.__new__(FileSyncer)
        from rich.console import Console

        syncer.console = Console()
        syncer._session_timestamp = None

        for name in ("a.txt", "b.txt"):
            (temp_dir / f"src_{name}").write_text("new")
            (temp_dir / name).write_text("old")

        syncer._copy_file(temp_dir / "src_a.txt", temp_dir / "a.txt")
        syncer._copy_file(temp_dir / "src_b.txt", temp_dir / "b.txt")

        backups = BackupManager(temp_dir).find_backups()
        assert len(backups) == 1
        (paths,) = backups.values()
        assert len(paths) == 2


class TestCleanCommand:
    """Test the clean CLI command."""

    def test_clean_project_with_yes(self, runner: CliRunner, temp_dir: Path) -> None:
        """Clean project --yes deletes backups under the cwd."""
        (temp_dir / "a.txt.bak.20260601_120000").write_text("old")

        with patch("dotconfig_hub.cli.Path.cwd", return_value=temp_dir):
            result = runner.invoke(clean, ["project", "--yes"])

        assert result.exit_code == 0
        assert not (temp_dir / "a.txt.bak.20260601_120000").exists()

    def test_clean_dry_run_keeps_files(self, runner: CliRunner, temp_dir: Path) -> None:
        """Clean project --dry-run leaves backups in place."""
        bak = temp_dir / "a.txt.bak.20260601_120000"
        bak.write_text("old")

        with patch("dotconfig_hub.cli.Path.cwd", return_value=temp_dir):
            result = runner.invoke(clean, ["project", "--dry-run"])

        assert result.exit_code == 0
        assert bak.exists()

    def test_clean_hub_uses_templates_source(
        self, runner: CliRunner, temp_dir: Path
    ) -> None:
        """Clean hub resolves the root from ProjectConfig."""
        (temp_dir / "a.txt.bak.20260601_120000").write_text("old")

        with patch("dotconfig_hub.cli.ProjectConfig") as mock_pc:
            mock_pc.return_value.get_templates_source.return_value = temp_dir
            result = runner.invoke(clean, ["hub", "--yes"])

        assert result.exit_code == 0
        assert not (temp_dir / "a.txt.bak.20260601_120000").exists()

    def test_clean_hub_without_setup_prints_error(self, runner: CliRunner) -> None:
        """Clean hub fails gracefully when templates source is missing."""
        with patch("dotconfig_hub.cli.ProjectConfig") as mock_pc:
            mock_pc.return_value.get_templates_source.return_value = None
            result = runner.invoke(clean, ["hub", "--yes"])

        assert result.exit_code == 0
        assert "not configured" in result.output


class TestRollbackCommand:
    """Test the rollback CLI command."""

    def test_rollback_with_explicit_version(
        self, runner: CliRunner, temp_dir: Path
    ) -> None:
        """Rollback project --version restores the selected version."""
        (temp_dir / "a.txt").write_text("current")
        (temp_dir / "a.txt.bak.20260601_120000").write_text("old")

        with patch("dotconfig_hub.cli.Path.cwd", return_value=temp_dir):
            result = runner.invoke(
                rollback,
                ["project", "--version", "20260601_120000", "--yes"],
            )

        assert result.exit_code == 0
        assert (temp_dir / "a.txt").read_text() == "old"

    def test_rollback_unknown_version_lists_available(
        self, runner: CliRunner, temp_dir: Path
    ) -> None:
        """An unknown version aborts and shows the available ones."""
        (temp_dir / "a.txt").write_text("current")
        (temp_dir / "a.txt.bak.20260601_120000").write_text("old")

        with patch("dotconfig_hub.cli.Path.cwd", return_value=temp_dir):
            result = runner.invoke(
                rollback,
                ["project", "--version", "19990101_000000", "--yes"],
            )

        assert result.exit_code == 0
        assert "not found" in result.output
        assert (temp_dir / "a.txt").read_text() == "current"

    def test_rollback_interactive_selection(
        self, runner: CliRunner, temp_dir: Path
    ) -> None:
        """Without --version, the version is chosen interactively."""
        (temp_dir / "a.txt").write_text("current")
        (temp_dir / "a.txt.bak.20260601_120000").write_text("old")

        with (
            patch("dotconfig_hub.cli.Path.cwd", return_value=temp_dir),
            patch(
                "dotconfig_hub.cli.Prompt.ask",
                return_value="20260601_120000",
            ),
        ):
            result = runner.invoke(rollback, ["project", "--yes"])

        assert result.exit_code == 0
        assert (temp_dir / "a.txt").read_text() == "old"
