"""Tests for directory filtering in file mapping and diff comparison.

Ensures that directories are excluded from sync operations to prevent
IsADirectoryError (Issue #10).
"""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
import yaml

from dotconfig_hub.config import Config
from dotconfig_hub.diff import DiffViewer


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


class TestGetFileMappingDirectoryFiltering:
    """Test that get_file_mapping() excludes directories from results."""

    def _create_config(
        self, hub_dir: Path, tool_name: str, files: list, project_subdir: str = ""
    ) -> Config:
        """Create a Config with a given tool configuration."""
        config_data = {
            "environment_sets": {
                "test_set": {
                    "description": "Test environment set",
                    "tools": {
                        tool_name: {
                            "project_dir": project_subdir,
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

    def test_glob_excludes_directories_from_source(
        self, temp_hub_dir: Path, temp_target_dir: Path
    ) -> None:
        """Directories matched by glob on the source side are excluded."""
        # Create source structure: a file and a directory at the same level
        source_dir = temp_hub_dir / "skills"
        source_dir.mkdir()
        (source_dir / "review.md").write_text("review skill")
        (source_dir / "proxy").mkdir()  # This directory should be excluded
        (source_dir / "proxy" / "config.yaml").write_text("proxy config")

        config = self._create_config(
            temp_hub_dir, "test_tool", ["skills/*"], project_subdir=""
        )

        mapping = config.get_file_mapping("test_tool", temp_target_dir, "test_set")

        # Only the file should be in the mapping, not the directory
        source_paths = list(mapping.keys())
        assert len(source_paths) == 1
        assert source_paths[0].name == "review.md"

    def test_glob_excludes_directories_from_target(
        self, temp_hub_dir: Path, temp_target_dir: Path
    ) -> None:
        """Directories matched by glob on the target side are excluded."""
        # Source side: empty (no files)
        source_dir = temp_hub_dir / "skills"
        source_dir.mkdir()

        # Target side: a file and a directory
        target_skills = temp_target_dir / "skills"
        target_skills.mkdir()
        (target_skills / "deploy.md").write_text("deploy skill")
        (target_skills / "proxy").mkdir()  # This directory should be excluded

        config = self._create_config(
            temp_hub_dir, "test_tool", ["skills/*"], project_subdir=""
        )

        mapping = config.get_file_mapping("test_tool", temp_target_dir, "test_set")

        # Only the file from target should be in the mapping
        target_paths = list(mapping.values())
        assert len(target_paths) == 1
        assert target_paths[0].name == "deploy.md"

    def test_non_glob_excludes_directory_path(
        self, temp_hub_dir: Path, temp_target_dir: Path
    ) -> None:
        """Non-glob entries that resolve to directories are excluded."""
        # Create a directory (not a file) at the specified path
        (temp_hub_dir / "proxy").mkdir()
        (temp_target_dir / "proxy").mkdir()

        config = self._create_config(
            temp_hub_dir, "test_tool", ["proxy"], project_subdir=""
        )

        mapping = config.get_file_mapping("test_tool", temp_target_dir, "test_set")

        # Directory-only entries should not appear in mapping
        assert len(mapping) == 0

    def test_non_glob_includes_file(
        self, temp_hub_dir: Path, temp_target_dir: Path
    ) -> None:
        """Non-glob entries that resolve to files are still included."""
        (temp_hub_dir / "settings.json").write_text("{}")

        config = self._create_config(
            temp_hub_dir, "test_tool", ["settings.json"], project_subdir=""
        )

        mapping = config.get_file_mapping("test_tool", temp_target_dir, "test_set")

        assert len(mapping) == 1
        source_path = list(mapping.keys())[0]
        assert source_path.name == "settings.json"


class TestDiffViewerDirectoryHandling:
    """Test that DiffViewer handles directory paths gracefully."""

    def test_compare_files_returns_false_for_source_directory(
        self, temp_hub_dir: Path, temp_target_dir: Path
    ) -> None:
        """compare_files() returns False when source is a directory."""
        source_dir = temp_hub_dir / "somedir"
        source_dir.mkdir()
        target_file = temp_target_dir / "somefile.txt"
        target_file.write_text("content")

        viewer = DiffViewer()
        result = viewer.compare_files(source_dir, target_file)

        assert result is False

    def test_compare_files_returns_false_for_target_directory(
        self, temp_hub_dir: Path, temp_target_dir: Path
    ) -> None:
        """compare_files() returns False when target is a directory."""
        source_file = temp_hub_dir / "somefile.txt"
        source_file.write_text("content")
        target_dir = temp_target_dir / "somedir"
        target_dir.mkdir()

        viewer = DiffViewer()
        result = viewer.compare_files(source_file, target_dir)

        assert result is False

    def test_get_diff_lines_returns_empty_for_directory(
        self, temp_hub_dir: Path, temp_target_dir: Path
    ) -> None:
        """get_diff_lines() returns empty list when a path is a directory."""
        source_dir = temp_hub_dir / "somedir"
        source_dir.mkdir()
        target_file = temp_target_dir / "somefile.txt"
        target_file.write_text("content")

        viewer = DiffViewer()
        result = viewer.get_diff_lines(source_dir, target_file)

        assert result == []

    def test_compare_files_still_works_for_normal_files(
        self, temp_hub_dir: Path, temp_target_dir: Path
    ) -> None:
        """compare_files() still works correctly for regular files."""
        source = temp_hub_dir / "file.txt"
        target = temp_target_dir / "file.txt"
        source.write_text("content A")
        target.write_text("content B")

        viewer = DiffViewer()

        # Different content → True
        assert viewer.compare_files(source, target) is True

        # Same content → False
        target.write_text("content A")
        assert viewer.compare_files(source, target) is False
