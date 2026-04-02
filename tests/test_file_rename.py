"""Tests for file rename rules (Issue #10).

Covers:
- _parse_file_entry: 3 formats + glob+rename validation
- get_file_mapping: rename-aware source→target mapping
- get_source_files_relative: target name used as key
- get_target_files: target name used for project-side path
- get_init_only_files: rename entries still recognized as init_only
- Backward compatibility: existing formats still work
"""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
import yaml

from dotconfig_hub.config import Config, FileEntry


@pytest.fixture
def temp_hub_dir() -> Generator[Path, None, None]:
    """Create a temporary hub directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def temp_target_dir() -> Generator[Path, None, None]:
    """Create a temporary target (project) directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


def _write_config(hub_dir: Path, tool_name: str, files: list) -> Config:
    """Create a Config with a given tool configuration."""
    config_data = {
        "environment_sets": {
            "test_set": {
                "description": "Test environment set",
                "tools": {
                    tool_name: {
                        "project_dir": "",
                        "files": files,
                    }
                },
            }
        }
    }
    config_path = hub_dir / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)
    return Config(config_path)


class TestParseFileEntry:
    """Test _parse_file_entry with all supported formats."""

    def test_string_format(self) -> None:
        """Plain string returns FileEntry with no rename."""
        result = Config._parse_file_entry("path/to/file")
        assert result == FileEntry(source="path/to/file", is_init_only=False)
        assert result.target is None

    def test_legacy_dict_format(self) -> None:
        """Legacy {path, init_only} dict returns FileEntry with no rename."""
        result = Config._parse_file_entry({"path": "CLAUDE.md", "init_only": True})
        assert result == FileEntry(source="CLAUDE.md", is_init_only=True, target=None)

    def test_rename_format(self) -> None:
        """New {source, target, init_only} dict returns FileEntry with rename."""
        entry = {"source": ".gitignore.hub", "target": ".gitignore", "init_only": True}
        result = Config._parse_file_entry(entry)
        assert result == FileEntry(
            source=".gitignore.hub", is_init_only=True, target=".gitignore"
        )

    def test_rename_format_without_init_only(self) -> None:
        """Rename without init_only defaults to False."""
        entry = {"source": "settings.hub.json", "target": "settings.json"}
        result = Config._parse_file_entry(entry)
        assert result == FileEntry(
            source="settings.hub.json", is_init_only=False, target="settings.json"
        )

    def test_source_without_target(self) -> None:
        """Source key without target works (no rename)."""
        entry = {"source": "README.md"}
        result = Config._parse_file_entry(entry)
        assert result == FileEntry(source="README.md", is_init_only=False, target=None)

    def test_glob_with_rename_raises_error(self) -> None:
        """Glob pattern combined with rename raises ValueError."""
        entry = {"source": "*.md", "target": "docs.md"}
        with pytest.raises(ValueError, match="Glob patterns cannot be combined"):
            Config._parse_file_entry(entry)

    def test_unexpected_type_raises_error(self) -> None:
        """Non-str/dict type raises TypeError."""
        with pytest.raises(TypeError, match="Unexpected file entry type"):
            Config._parse_file_entry(42)

    def test_dict_without_source_or_path_raises_value_error(self) -> None:
        """Dict entry missing both 'source' and 'path' raises ValueError."""
        with pytest.raises(ValueError, match="must contain 'source' or 'path' key"):
            Config._parse_file_entry({"target": ".git/info/exclude"})

    def test_dict_with_only_init_only_raises_value_error(self) -> None:
        """Dict entry with only 'init_only' key raises ValueError."""
        with pytest.raises(ValueError, match="must contain 'source' or 'path' key"):
            Config._parse_file_entry({"init_only": True})

    def test_empty_dict_raises_value_error(self) -> None:
        """Empty dict raises ValueError."""
        with pytest.raises(ValueError, match="must contain 'source' or 'path' key"):
            Config._parse_file_entry({})


class TestGetFileMappingWithRename:
    """Test that get_file_mapping uses rename rules correctly."""

    def test_rename_maps_source_to_target(
        self, temp_hub_dir: Path, temp_target_dir: Path
    ) -> None:
        """Hub's .gitignore.hub maps to project's .gitignore."""
        # Create hub file with hub-side name
        (temp_hub_dir / ".gitignore.hub").write_text("*.pyc\n")

        config = _write_config(
            temp_hub_dir,
            "git_config",
            [{"source": ".gitignore.hub", "target": ".gitignore", "init_only": True}],
        )

        mapping = config.get_file_mapping("git_config", temp_target_dir, "test_set")

        assert len(mapping) == 1
        source = list(mapping.keys())[0]
        target = list(mapping.values())[0]
        assert source.name == ".gitignore.hub"
        assert target.name == ".gitignore"

    def test_rename_reverse_direction(
        self, temp_hub_dir: Path, temp_target_dir: Path
    ) -> None:
        """Project's .gitignore maps back to hub's .gitignore.hub."""
        # Only project-side file exists
        (temp_target_dir / ".gitignore").write_text("*.pyc\n")

        config = _write_config(
            temp_hub_dir,
            "git_config",
            [{"source": ".gitignore.hub", "target": ".gitignore"}],
        )

        mapping = config.get_file_mapping("git_config", temp_target_dir, "test_set")

        assert len(mapping) == 1
        source = list(mapping.keys())[0]
        target = list(mapping.values())[0]
        # Source is hub-side name, target is project-side name
        assert source.name == ".gitignore.hub"
        assert target.name == ".gitignore"

    def test_no_rename_backward_compat(
        self, temp_hub_dir: Path, temp_target_dir: Path
    ) -> None:
        """Legacy format still works: same name on both sides."""
        (temp_hub_dir / "CLAUDE.md").write_text("# Claude")

        config = _write_config(
            temp_hub_dir,
            "claude_config",
            [{"path": "CLAUDE.md", "init_only": True}],
        )

        mapping = config.get_file_mapping("claude_config", temp_target_dir, "test_set")

        assert len(mapping) == 1
        source = list(mapping.keys())[0]
        target = list(mapping.values())[0]
        assert source.name == "CLAUDE.md"
        assert target.name == "CLAUDE.md"


class TestGetSourceFilesRelativeWithRename:
    """Test that get_source_files_relative uses target name as key."""

    def test_rename_entry_keyed_by_target(self, temp_hub_dir: Path) -> None:
        """Rename entries use target (project-side) name as the key."""
        (temp_hub_dir / ".gitignore.hub").write_text("*.pyc\n")

        config = _write_config(
            temp_hub_dir,
            "git_config",
            [{"source": ".gitignore.hub", "target": ".gitignore"}],
        )

        relative_map = config.get_source_files_relative("git_config", "test_set")

        # Key should be the target name, not the source name
        assert ".gitignore" in relative_map
        assert ".gitignore.hub" not in relative_map
        assert relative_map[".gitignore"].name == ".gitignore.hub"


class TestGetTargetFilesWithRename:
    """Test that get_target_files uses target name for project-side path."""

    def test_rename_uses_target_name(
        self, temp_hub_dir: Path, temp_target_dir: Path
    ) -> None:
        """Target files use project-side name from rename config."""
        config = _write_config(
            temp_hub_dir,
            "git_config",
            [{"source": ".gitignore.hub", "target": ".gitignore"}],
        )

        targets = config.get_target_files("git_config", temp_target_dir, "test_set")

        assert len(targets) == 1
        assert targets[0].name == ".gitignore"


class TestGetInitOnlyFilesWithRename:
    """Test that init_only detection works with rename entries."""

    def test_rename_entry_detected_as_init_only(self, temp_hub_dir: Path) -> None:
        """Rename entries with init_only=true are detected."""
        config = _write_config(
            temp_hub_dir,
            "git_config",
            [{"source": ".gitignore.hub", "target": ".gitignore", "init_only": True}],
        )

        init_only = config.get_init_only_files("git_config", "test_set")

        # init_only uses the hub-side source name
        assert ".gitignore.hub" in init_only

    def test_rename_entry_without_init_only_not_included(
        self, temp_hub_dir: Path
    ) -> None:
        """Rename entries without init_only are not in init_only set."""
        config = _write_config(
            temp_hub_dir,
            "git_config",
            [{"source": ".gitignore.hub", "target": ".gitignore"}],
        )

        init_only = config.get_init_only_files("git_config", "test_set")

        assert len(init_only) == 0
