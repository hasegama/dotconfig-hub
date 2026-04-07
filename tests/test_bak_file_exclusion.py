"""Tests for .bak file exclusion from sync operations.

Ensures that .bak backup files (auto-created by dotconfig-hub during sync)
are excluded from file discovery by default, and can be included via override.
"""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
import yaml

from dotconfig_hub.config import DEFAULT_EXCLUDE_SUFFIXES, Config


@pytest.fixture
def temp_hub_dir() -> Generator[Path, None, None]:
    """Create a temporary hub directory with config and template files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def temp_target_dir() -> Generator[Path, None, None]:
    """Create a temporary target (project) directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


class TestIsExcluded:
    """Test Config._is_excluded() static method."""

    def test_bak_suffix_excluded(self) -> None:
        """A file with .bak suffix is excluded by default."""
        assert Config._is_excluded(Path("ci.yml.bak")) is True

    def test_bak_with_timestamp_excluded(self) -> None:
        """A timestamped backup like ci.yml.bak.20260325_202320 is excluded."""
        assert Config._is_excluded(Path("ci.yml.bak.20260325_202320")) is True

    def test_normal_file_not_excluded(self) -> None:
        """A normal file is not excluded."""
        assert Config._is_excluded(Path("ci.yml")) is False

    def test_dotfile_not_excluded(self) -> None:
        """A dotfile like .gitignore is not excluded."""
        assert Config._is_excluded(Path(".gitignore")) is False

    def test_empty_exclude_list_excludes_nothing(self) -> None:
        """Passing empty exclude_suffixes disables all exclusion."""
        assert Config._is_excluded(Path("ci.yml.bak"), exclude_suffixes=()) is False

    def test_custom_exclude_suffix(self) -> None:
        """Custom suffixes can be used for exclusion."""
        assert (
            Config._is_excluded(Path("file.orig"), exclude_suffixes=(".orig",)) is True
        )
        assert (
            Config._is_excluded(Path("file.bak"), exclude_suffixes=(".orig",)) is False
        )

    def test_default_constant_contains_bak(self) -> None:
        """DEFAULT_EXCLUDE_SUFFIXES contains .bak."""
        assert ".bak" in DEFAULT_EXCLUDE_SUFFIXES


def _create_config(
    hub_dir: Path,
    tool_name: str,
    files: list,
    project_subdir: str = "",
    include_backup_files: bool = False,
) -> Config:
    """Create a Config with a given tool configuration."""
    tool_cfg: dict = {
        "project_dir": project_subdir,
        "files": files,
    }
    if include_backup_files:
        tool_cfg["include_backup_files"] = True

    config_data = {
        "environment_sets": {
            "test_set": {
                "description": "Test environment set",
                "tools": {tool_name: tool_cfg},
            }
        }
    }
    config_path = hub_dir / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)

    return Config(config_path)


class TestGetFileMappingBakExclusion:
    """Test that get_file_mapping() excludes .bak files by default."""

    def test_glob_excludes_bak_from_source(
        self, temp_hub_dir: Path, temp_target_dir: Path
    ) -> None:
        """Glob patterns on source side skip .bak files."""
        source_dir = temp_hub_dir / "configs"
        source_dir.mkdir()
        (source_dir / "settings.json").write_text("{}")
        (source_dir / "settings.json.bak").write_text("{old}")

        config = _create_config(temp_hub_dir, "tool", ["configs/*"])
        mapping = config.get_file_mapping("tool", temp_target_dir, "test_set")

        source_names = [p.name for p in mapping.keys()]
        assert "settings.json" in source_names
        assert "settings.json.bak" not in source_names

    def test_glob_excludes_bak_from_target(
        self, temp_hub_dir: Path, temp_target_dir: Path
    ) -> None:
        """Glob patterns on target side skip .bak files."""
        # Source side: empty dir (so target-only files are picked up)
        source_dir = temp_hub_dir / "configs"
        source_dir.mkdir()

        # Target side: normal file + .bak file
        target_dir = temp_target_dir / "configs"
        target_dir.mkdir()
        (target_dir / "settings.json").write_text("{}")
        (target_dir / "settings.json.bak").write_text("{old}")

        config = _create_config(temp_hub_dir, "tool", ["configs/*"])
        mapping = config.get_file_mapping("tool", temp_target_dir, "test_set")

        target_names = [p.name for p in mapping.values()]
        assert "settings.json" in target_names
        assert "settings.json.bak" not in target_names

    def test_glob_excludes_timestamped_bak(
        self, temp_hub_dir: Path, temp_target_dir: Path
    ) -> None:
        """Timestamped .bak files (e.g. .bak.20260325) are also excluded."""
        source_dir = temp_hub_dir / "configs"
        source_dir.mkdir()
        (source_dir / "app.toml").write_text("key = 1")
        (source_dir / "app.toml.bak.20260325_202320").write_text("key = 0")

        config = _create_config(temp_hub_dir, "tool", ["configs/*"])
        mapping = config.get_file_mapping("tool", temp_target_dir, "test_set")

        source_names = [p.name for p in mapping.keys()]
        assert "app.toml" in source_names
        assert "app.toml.bak.20260325_202320" not in source_names

    def test_include_backup_files_config_allows_bak(
        self, temp_hub_dir: Path, temp_target_dir: Path
    ) -> None:
        """Setting include_backup_files: true in config.yaml includes .bak files."""
        source_dir = temp_hub_dir / "configs"
        source_dir.mkdir()
        (source_dir / "settings.json").write_text("{}")
        (source_dir / "settings.json.bak").write_text("{old}")

        config = _create_config(
            temp_hub_dir, "tool", ["configs/*"], include_backup_files=True
        )
        mapping = config.get_file_mapping("tool", temp_target_dir, "test_set")

        source_names = [p.name for p in mapping.keys()]
        assert "settings.json" in source_names
        assert "settings.json.bak" in source_names

    def test_non_glob_explicit_bak_excluded(
        self, temp_hub_dir: Path, temp_target_dir: Path
    ) -> None:
        """Explicit .bak file entry is excluded by default."""
        (temp_hub_dir / "settings.json.bak").write_text("{old}")

        config = _create_config(temp_hub_dir, "tool", ["settings.json.bak"])
        mapping = config.get_file_mapping("tool", temp_target_dir, "test_set")

        assert len(mapping) == 0

    def test_normal_files_unaffected(
        self, temp_hub_dir: Path, temp_target_dir: Path
    ) -> None:
        """Normal files are not affected by the exclusion."""
        (temp_hub_dir / "readme.md").write_text("# Hello")
        (temp_hub_dir / "config.toml").write_text("[section]")

        config = _create_config(temp_hub_dir, "tool", ["readme.md", "config.toml"])
        mapping = config.get_file_mapping("tool", temp_target_dir, "test_set")

        source_names = [p.name for p in mapping.keys()]
        assert "readme.md" in source_names
        assert "config.toml" in source_names


class TestGetSourceFilesBakExclusion:
    """Test that get_source_files() excludes .bak files by default."""

    def test_bak_excluded_from_source_files(self, temp_hub_dir: Path) -> None:
        """get_source_files() omits .bak files."""
        source_dir = temp_hub_dir / "configs"
        source_dir.mkdir()
        (source_dir / "app.yml").write_text("key: 1")
        (source_dir / "app.yml.bak").write_text("key: 0")

        config = _create_config(temp_hub_dir, "tool", ["configs/*"])
        files = config.get_source_files("tool", "test_set")

        names = [p.name for p in files]
        assert "app.yml" in names
        assert "app.yml.bak" not in names

    def test_bak_excluded_from_relative_map(self, temp_hub_dir: Path) -> None:
        """get_source_files_relative() omits .bak files."""
        source_dir = temp_hub_dir / "configs"
        source_dir.mkdir()
        (source_dir / "app.yml").write_text("key: 1")
        (source_dir / "app.yml.bak").write_text("key: 0")

        config = _create_config(temp_hub_dir, "tool", ["configs/*"])
        rel_map = config.get_source_files_relative("tool", "test_set")

        keys = list(rel_map.keys())
        assert any("app.yml" in k and ".bak" not in k for k in keys)
        assert not any(".bak" in k for k in keys)
