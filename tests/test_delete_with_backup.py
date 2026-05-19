"""Tests for delete-with-backup during sync (Issue #15).

Covers:
- _delete_with_backup confirmation, success, and skip behavior
- _prompt_sync_direction surfacing the delete option only when one side
  of the pair is missing
- _perform_sync dispatch for DELETE_LOCAL / DELETE_REMOTE
- _sync_file dry-run messaging for delete directions
"""

import tempfile
from collections.abc import Generator
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from dotconfig_hub.sync import FileSyncer, SyncDirection


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def syncer() -> FileSyncer:
    """Create a FileSyncer bypassing the config-dependent __init__."""
    return FileSyncer.__new__(FileSyncer)


@pytest.fixture(autouse=True)
def _setup_syncer(syncer: FileSyncer) -> None:
    """Attach a Console and DiffViewer so print/diff calls don't fail."""
    from rich.console import Console

    from dotconfig_hub.diff import DiffViewer

    syncer.console = Console()
    syncer.diff_viewer = DiffViewer()


class TestDeleteWithBackup:
    """Test FileSyncer._delete_with_backup."""

    def test_renames_existing_file_to_timestamped_bak(
        self, syncer: FileSyncer, temp_dir: Path
    ) -> None:
        """File is renamed to .bak.<timestamp> on user confirmation."""
        path = temp_dir / "ruff.toml"
        path.write_text("line-length = 88\n")

        fake_now = datetime(2026, 4, 7, 12, 34, 56)
        with patch("dotconfig_hub.sync.Confirm.ask", return_value=True), patch(
            "dotconfig_hub.sync.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.fromtimestamp = datetime.fromtimestamp
            result = syncer._delete_with_backup(path, side="Project")

        assert result is True
        assert not path.exists()
        expected = temp_dir / "ruff.toml.bak.20260407_123456"
        assert expected.exists()
        assert expected.read_text() == "line-length = 88\n"

    def test_dotfile_renamed_with_bak_suffix(
        self, syncer: FileSyncer, temp_dir: Path
    ) -> None:
        """A dotfile like .gitignore gets a .bak.<timestamp> suffix appended."""
        path = temp_dir / ".gitignore"
        path.write_text("*.pyc\n")

        fake_now = datetime(2026, 4, 7, 12, 34, 56)
        with patch("dotconfig_hub.sync.Confirm.ask", return_value=True), patch(
            "dotconfig_hub.sync.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.fromtimestamp = datetime.fromtimestamp
            assert syncer._delete_with_backup(path, side="Hub") is True

        assert (temp_dir / ".gitignore.bak.20260407_123456").exists()
        assert not path.exists()

    def test_skip_when_user_declines(
        self, syncer: FileSyncer, temp_dir: Path
    ) -> None:
        """File is left untouched when the user declines the confirmation."""
        path = temp_dir / "ruff.toml"
        path.write_text("contents")

        with patch("dotconfig_hub.sync.Confirm.ask", return_value=False):
            result = syncer._delete_with_backup(path, side="Project")

        assert result is False
        assert path.exists()
        assert path.read_text() == "contents"
        bak_files = [f for f in temp_dir.iterdir() if ".bak." in f.name]
        assert bak_files == []

    def test_skip_when_path_missing(
        self, syncer: FileSyncer, temp_dir: Path
    ) -> None:
        """Returns False when the file to delete does not exist."""
        path = temp_dir / "missing.toml"

        with patch("dotconfig_hub.sync.Confirm.ask") as mock_confirm:
            result = syncer._delete_with_backup(path, side="Hub")

        assert result is False
        # No confirmation should be asked when the path is missing.
        mock_confirm.assert_not_called()


class TestPromptOffersDeleteOption:
    """The interactive prompt should expose 'x' only when one side is missing."""

    def test_delete_option_hidden_when_both_files_exist(
        self, syncer: FileSyncer, temp_dir: Path
    ) -> None:
        """No delete option when both sides exist (regular Different case)."""
        source = temp_dir / "hub.txt"
        target = temp_dir / "proj.txt"
        source.write_text("a")
        target.write_text("b")

        with patch("dotconfig_hub.sync.Prompt.ask", return_value="s") as mock_ask:
            syncer._prompt_sync_direction(source, target)

        choices = mock_ask.call_args.kwargs["choices"]
        assert "x" not in choices

    def test_delete_option_shown_when_target_missing(
        self, syncer: FileSyncer, temp_dir: Path
    ) -> None:
        """When the Project side is missing, choosing 'x' deletes the Hub side."""
        source = temp_dir / "hub.txt"
        target = temp_dir / "proj.txt"
        source.write_text("a")  # Hub exists
        # target intentionally missing

        with patch("dotconfig_hub.sync.Prompt.ask", return_value="x") as mock_ask:
            direction = syncer._prompt_sync_direction(source, target)

        assert "x" in mock_ask.call_args.kwargs["choices"]
        assert direction == SyncDirection.DELETE_REMOTE

    def test_delete_option_shown_when_source_missing(
        self, syncer: FileSyncer, temp_dir: Path
    ) -> None:
        """When the Hub side is missing, choosing 'x' deletes the Project side."""
        source = temp_dir / "hub.txt"
        target = temp_dir / "proj.txt"
        target.write_text("b")  # Project exists
        # source intentionally missing

        with patch("dotconfig_hub.sync.Prompt.ask", return_value="x") as mock_ask:
            direction = syncer._prompt_sync_direction(source, target)

        assert "x" in mock_ask.call_args.kwargs["choices"]
        assert direction == SyncDirection.DELETE_LOCAL


class TestPerformSyncDeleteDispatch:
    """_perform_sync should route DELETE_LOCAL / DELETE_REMOTE correctly."""

    def test_delete_local_renames_target(
        self, syncer: FileSyncer, temp_dir: Path
    ) -> None:
        """DELETE_LOCAL backs up the project-side (target) file."""
        source = temp_dir / "hub.txt"  # not created — Hub side missing
        target = temp_dir / "proj.txt"
        target.write_text("project-only")

        with patch("dotconfig_hub.sync.Confirm.ask", return_value=True):
            result = syncer._perform_sync(
                source, target, SyncDirection.DELETE_LOCAL
            )

        assert result is True
        assert not target.exists()
        bak_files = [f for f in temp_dir.iterdir() if ".bak." in f.name]
        assert len(bak_files) == 1
        assert bak_files[0].name.startswith("proj.txt.bak.")
        assert bak_files[0].read_text() == "project-only"

    def test_delete_remote_renames_source(
        self, syncer: FileSyncer, temp_dir: Path
    ) -> None:
        """DELETE_REMOTE backs up the hub-side (source) file."""
        source = temp_dir / "hub.txt"
        source.write_text("hub-only")
        target = temp_dir / "proj.txt"  # not created — Project side missing

        with patch("dotconfig_hub.sync.Confirm.ask", return_value=True):
            result = syncer._perform_sync(
                source, target, SyncDirection.DELETE_REMOTE
            )

        assert result is True
        assert not source.exists()
        bak_files = [f for f in temp_dir.iterdir() if ".bak." in f.name]
        assert len(bak_files) == 1
        assert bak_files[0].name.startswith("hub.txt.bak.")
        assert bak_files[0].read_text() == "hub-only"


class TestSyncFileDryRunDelete:
    """Dry-run should not touch files for delete directions."""

    def test_dry_run_delete_local_does_not_modify(
        self, syncer: FileSyncer, temp_dir: Path
    ) -> None:
        """Dry-run for DELETE_LOCAL leaves the project file in place."""
        source = temp_dir / "hub.txt"  # Hub missing
        target = temp_dir / "proj.txt"
        target.write_text("keep me")

        with patch.object(
            syncer,
            "_prompt_sync_direction",
            return_value=SyncDirection.DELETE_LOCAL,
        ), patch.object(syncer.diff_viewer, "display_diff"):
            result = syncer._sync_file(source, target, auto_sync=None, dry_run=True)

        assert result is True
        assert target.exists()
        assert target.read_text() == "keep me"
        bak_files = [f for f in temp_dir.iterdir() if ".bak." in f.name]
        assert bak_files == []

    def test_dry_run_delete_remote_does_not_modify(
        self, syncer: FileSyncer, temp_dir: Path
    ) -> None:
        """Dry-run for DELETE_REMOTE leaves the hub file in place."""
        source = temp_dir / "hub.txt"
        source.write_text("keep me")
        target = temp_dir / "proj.txt"  # Project missing

        with patch.object(
            syncer,
            "_prompt_sync_direction",
            return_value=SyncDirection.DELETE_REMOTE,
        ), patch.object(syncer.diff_viewer, "display_diff"):
            result = syncer._sync_file(source, target, auto_sync=None, dry_run=True)

        assert result is True
        assert source.exists()
        assert source.read_text() == "keep me"
        bak_files = [f for f in temp_dir.iterdir() if ".bak." in f.name]
        assert bak_files == []
