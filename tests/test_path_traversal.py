"""Tests for path confinement of config.yaml entries (path traversal fix).

config.yaml lives in the hub repository, which may be shared. Paths in it
must not reach outside the hub (project_dir, source) or outside the project
(target), whether via ``..``, absolute paths, or symlinks.
"""

import os
import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from dotconfig_hub.config import Config, UnsafePathError, is_within, safe_join
from dotconfig_hub.sync import FileSyncer

TOOL = "vscode"
ENV_SET = "test_set"


@pytest.fixture
def workspace() -> Generator[Path, None, None]:
    """Create a workspace with hub/, home/project/ and a fake secret."""
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / "hub" / "set" / ".vscode").mkdir(parents=True)
        (root / "home" / "project").mkdir(parents=True)
        (root / "home" / ".ssh").mkdir()
        (root / "home" / ".bashrc").write_text("original\n")
        (root / "home" / ".ssh" / "id_ed25519").write_text("SECRET\n")
        (root / "hub" / "set" / ".vscode" / "payload.sh").write_text("evil\n")
        yield root


def _config(root: Path, files: list, project_dir: str = "set") -> Config:
    """Write config.yaml with one tool and return a Config for it."""
    data = {
        "environment_sets": {
            ENV_SET: {"tools": {TOOL: {"project_dir": project_dir, "files": files}}}
        }
    }
    config_path = root / "hub" / "config.yaml"
    config_path.write_text(yaml.dump(data))
    return Config(config_path)


def _project(root: Path) -> Path:
    """Return the project directory inside the workspace."""
    return root / "home" / "project"


class TestSafeJoin:
    """Test safe join."""

    def test_plain_relative_path_is_allowed(self, workspace: Path) -> None:
        """Plain relative path is allowed."""
        base = workspace / "hub"
        assert safe_join(base, "set/.vscode/a.json", "source") == (
            base / "set/.vscode/a.json"
        )

    def test_empty_path_is_base(self, workspace: Path) -> None:
        """Empty path is base."""
        base = workspace / "hub"
        assert safe_join(base, "", "project_dir") == base

    def test_inner_dotdot_that_stays_inside_is_allowed(self, workspace: Path) -> None:
        """Inner dotdot that stays inside is allowed."""
        base = workspace / "hub"
        assert is_within(safe_join(base, "set/../set/x", "source"), base)

    @pytest.mark.parametrize("bad", ["../x", "a/../../x", "../../.bashrc"])
    def test_dotdot_escape_is_rejected(self, workspace: Path, bad: str) -> None:
        """Dotdot escape is rejected."""
        with pytest.raises(UnsafePathError):
            safe_join(workspace / "hub", bad, "target")

    def test_absolute_path_is_rejected(self, workspace: Path) -> None:
        """Absolute path is rejected."""
        with pytest.raises(UnsafePathError):
            safe_join(workspace / "hub", str(workspace / "home" / ".bashrc"), "target")

    def test_unsafe_path_error_is_value_error(self) -> None:
        """Unsafe path error is value error."""
        assert issubclass(UnsafePathError, ValueError)


class TestFileMappingConfinement:
    """Test file mapping confinement."""

    def test_target_with_dotdot_is_rejected(self, workspace: Path) -> None:
        """Target with dotdot is rejected."""
        config = _config(
            workspace, [{"source": ".vscode/payload.sh", "target": "../.bashrc"}]
        )
        with pytest.raises(UnsafePathError):
            config.get_file_mapping(TOOL, _project(workspace), ENV_SET)

    def test_absolute_target_is_rejected(self, workspace: Path) -> None:
        """Absolute target is rejected."""
        abs_target = str(workspace / "home" / ".bashrc")
        config = _config(
            workspace, [{"source": ".vscode/payload.sh", "target": abs_target}]
        )
        with pytest.raises(UnsafePathError):
            config.get_file_mapping(TOOL, _project(workspace), ENV_SET)

    def test_source_with_dotdot_is_rejected(self, workspace: Path) -> None:
        """Source with dotdot is rejected."""
        config = _config(workspace, ["../../home/.ssh/id_ed25519"])
        with pytest.raises(UnsafePathError):
            config.get_file_mapping(TOOL, _project(workspace), ENV_SET)

    def test_legacy_path_entry_with_dotdot_is_rejected(self, workspace: Path) -> None:
        """Legacy path entry with dotdot is rejected."""
        config = _config(workspace, [{"path": "../../home/.bashrc"}])
        with pytest.raises(UnsafePathError):
            config.get_file_mapping(TOOL, _project(workspace), ENV_SET)

    def test_project_dir_outside_hub_is_rejected(self, workspace: Path) -> None:
        """Project dir outside hub is rejected."""
        config = _config(workspace, [".ssh/id_ed25519"], project_dir="../home")
        with pytest.raises(UnsafePathError):
            config.get_file_mapping(TOOL, _project(workspace), ENV_SET)
        with pytest.raises(UnsafePathError):
            config.get_source_files(TOOL, ENV_SET)

    def test_glob_with_dotdot_is_rejected(self, workspace: Path) -> None:
        """Glob with dotdot is rejected."""
        config = _config(workspace, ["../../home/*"])
        with pytest.raises(UnsafePathError):
            config.get_file_mapping(TOOL, _project(workspace), ENV_SET)

    def test_get_target_files_rejects_escape(self, workspace: Path) -> None:
        """Get target files rejects escape."""
        config = _config(
            workspace, [{"source": ".vscode/payload.sh", "target": "../.bashrc"}]
        )
        with pytest.raises(UnsafePathError):
            config.get_target_files(TOOL, _project(workspace), ENV_SET)

    def test_normal_entries_still_work(self, workspace: Path) -> None:
        """Normal entries still work."""
        config = _config(
            workspace,
            [{"source": ".vscode/payload.sh", "target": ".vscode/run.sh"}],
        )
        mapping = config.get_file_mapping(TOOL, _project(workspace), ENV_SET)
        assert mapping == {
            workspace / "hub" / "set" / ".vscode" / "payload.sh": _project(workspace)
            / ".vscode"
            / "run.sh"
        }


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unsupported")
class TestSymlinkConfinement:
    """Test symlink confinement."""

    def test_symlinked_target_dir_is_rejected(self, workspace: Path) -> None:
        """Symlinked target dir is rejected."""
        # Project contains .vscode -> ~ ; writing .vscode/.bashrc would hit ~/.bashrc
        (_project(workspace) / ".vscode").symlink_to(workspace / "home")
        config = _config(
            workspace, [{"source": ".vscode/payload.sh", "target": ".vscode/.bashrc"}]
        )
        with pytest.raises(UnsafePathError):
            config.get_file_mapping(TOOL, _project(workspace), ENV_SET)

    def test_symlinked_project_file_is_rejected(self, workspace: Path) -> None:
        """Symlinked project file is rejected."""
        # Project file symlinked to a secret must not be copied into the hub
        (_project(workspace) / ".vscode").mkdir()
        (_project(workspace) / ".vscode" / "payload.sh").symlink_to(
            workspace / "home" / ".ssh" / "id_ed25519"
        )
        config = _config(workspace, [".vscode/payload.sh"])
        with pytest.raises(UnsafePathError):
            config.get_file_mapping(TOOL, _project(workspace), ENV_SET)

    def test_symlinked_hub_file_is_rejected(self, workspace: Path) -> None:
        """Symlinked hub file is rejected."""
        (workspace / "hub" / "set" / ".vscode" / "leak").symlink_to(
            workspace / "home" / ".ssh" / "id_ed25519"
        )
        config = _config(workspace, [".vscode/leak"])
        with pytest.raises(UnsafePathError):
            config.get_file_mapping(TOOL, _project(workspace), ENV_SET)

    def test_glob_skips_symlinks_pointing_outside(self, workspace: Path) -> None:
        """Glob skips symlinks pointing outside."""
        (workspace / "hub" / "set" / ".vscode" / "leak.txt").symlink_to(
            workspace / "home" / ".ssh" / "id_ed25519"
        )
        (workspace / "hub" / "set" / ".vscode" / "ok.txt").write_text("ok\n")
        config = _config(workspace, [".vscode/*.txt"])
        mapping = config.get_file_mapping(TOOL, _project(workspace), ENV_SET)
        names = sorted(p.name for p in mapping)
        assert names == ["ok.txt"]


class TestSyncDoesNotEscape:
    """Test sync does not escape."""

    def test_auto_sync_local_does_not_overwrite_outside_file(
        self, workspace: Path
    ) -> None:
        """Auto sync local does not overwrite outside file."""
        config = _config(
            workspace, [{"source": ".vscode/payload.sh", "target": "../.bashrc"}]
        )
        with pytest.raises(UnsafePathError):
            FileSyncer(config).sync_tool(
                TOOL, _project(workspace), "local", False, ENV_SET
            )
        assert (workspace / "home" / ".bashrc").read_text() == "original\n"

    def test_auto_sync_remote_does_not_copy_secret_into_hub(
        self, workspace: Path
    ) -> None:
        """Auto sync remote does not copy secret into hub."""
        config = _config(
            workspace,
            [{"source": ".vscode/leak.txt", "target": "../.ssh/id_ed25519"}],
        )
        with pytest.raises(UnsafePathError):
            FileSyncer(config).sync_tool(
                TOOL, _project(workspace), "remote", False, ENV_SET
            )
        assert not (workspace / "hub" / "set" / ".vscode" / "leak.txt").exists()

    @pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unsupported")
    def test_glob_sync_local_does_not_write_through_project_symlink(
        self, workspace: Path
    ) -> None:
        """Glob sync local does not write through a symlinked project directory."""
        (workspace / "hub" / "set" / "conf").mkdir()
        (workspace / "hub" / "set" / "conf" / "run.sh").write_text("evil\n")
        (workspace / "home" / "outside").mkdir()
        (workspace / "home" / "outside" / "run.sh").write_text("original\n")
        (_project(workspace) / "conf").symlink_to(workspace / "home" / "outside")
        config = _config(workspace, ["**/*"])
        FileSyncer(config).sync_tool(TOOL, _project(workspace), "local", False, ENV_SET)
        assert (workspace / "home" / "outside" / "run.sh").read_text() == "original\n"

    @pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unsupported")
    def test_glob_sync_remote_does_not_write_through_hub_symlink(
        self, workspace: Path
    ) -> None:
        """Glob sync remote does not write through a symlinked hub file."""
        (workspace / "hub" / "set" / ".vscode" / "x.txt").symlink_to(
            workspace / "home" / ".bashrc"
        )
        (_project(workspace) / ".vscode").mkdir()
        (_project(workspace) / ".vscode" / "x.txt").write_text("evil\n")
        config = _config(workspace, [".vscode/*.txt"])
        FileSyncer(config).sync_tool(
            TOOL, _project(workspace), "remote", False, ENV_SET
        )
        assert (workspace / "home" / ".bashrc").read_text() == "original\n"


def _sync_answering(config: Config, root: Path, key: str) -> None:
    """対話式の同期を、操作選択に ``key`` と答え、確認にはすべて yes で実行する。"""
    with (
        patch("dotconfig_hub.sync.Prompt.ask", return_value=key),
        patch("dotconfig_hub.sync.Confirm.ask", return_value=True),
    ):
        FileSyncer(config).sync_tool(TOOL, _project(root), None, False, ENV_SET)


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unsupported")
class TestDeleteWithBackupDoesNotEscape:
    """片側だけ残ったファイルの削除は Hub と Project の外に及ばない。"""

    def test_project_side_delete_does_not_reach_through_symlinked_dir(
        self, workspace: Path
    ) -> None:
        """Project 側の削除は、シンボリックリンクのディレクトリ先のドットファイルを消さない。"""
        outside = workspace / "home" / "outside"
        outside.mkdir()
        (outside / ".profile").write_text("original\n")
        (_project(workspace) / ".vscode").symlink_to(outside)
        config = _config(workspace, ["**/*"])
        _sync_answering(config, workspace, "p")
        assert (outside / ".profile").read_text() == "original\n"
        assert not (outside / "payload.sh").exists()

    def test_hub_side_delete_does_not_reach_through_symlinked_dir(
        self, workspace: Path
    ) -> None:
        """Hub 側の削除は、シンボリックリンクのディレクトリ先のドットファイルを消さない。"""
        outside = workspace / "home" / "outside"
        outside.mkdir()
        (outside / ".env").write_text("keep\n")
        (workspace / "hub" / "set" / "conf").symlink_to(outside)
        config = _config(workspace, ["**/*"])
        _sync_answering(config, workspace, "h")
        assert (outside / ".env").read_text() == "keep\n"

