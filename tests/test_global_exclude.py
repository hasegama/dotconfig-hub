"""Tests for global exclude patterns (top-level `exclude:` key in config.yaml).

OS metadata files such as .DS_Store became discoverable once glob patterns
started matching dotfiles (Issue #16). DEFAULT_EXCLUDE_PATTERNS excludes them
globally, and users can add their own patterns via the top-level `exclude:`
key. Patterns follow gitignore semantics: no `/` means basename match at any
depth; with `/` the pattern is matched against the path relative to the
tool's base directory.
"""

import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
import yaml

from dotconfig_hub.config import DEFAULT_EXCLUDE_PATTERNS, Config


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


def _write_config(
    hub_dir: Path,
    files: List,
    exclude: Optional[List[str]] = None,
) -> Path:
    """Write a minimal config.yaml, optionally with a top-level exclude key."""
    config_data: Dict[str, Any] = {
        "environment_sets": {
            "default": {
                "description": "test",
                "tools": {
                    "test_tool": {
                        "project_dir": ".",
                        "files": files,
                    }
                },
            }
        }
    }
    if exclude is not None:
        config_data["exclude"] = exclude
    config_path = hub_dir / "config.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config_data, f)
    return config_path


class TestDefaultExcludePatterns:
    """DEFAULT_EXCLUDE_PATTERNS and Config.exclude_patterns merging."""

    def test_default_contains_ds_store(self) -> None:
        """.DS_Store is excluded by default."""
        assert ".DS_Store" in DEFAULT_EXCLUDE_PATTERNS

    def test_user_patterns_merged_with_defaults(self, temp_hub_dir: Path) -> None:
        """Top-level `exclude:` adds to the defaults instead of replacing them."""
        _write_config(temp_hub_dir, files=["*"], exclude=["Thumbs.db"])
        config = Config(temp_hub_dir / "config.yaml")
        assert ".DS_Store" in config.exclude_patterns
        assert "Thumbs.db" in config.exclude_patterns

    def test_no_exclude_key_uses_defaults(self, temp_hub_dir: Path) -> None:
        """Config without an `exclude:` key falls back to the defaults."""
        _write_config(temp_hub_dir, files=["*"])
        config = Config(temp_hub_dir / "config.yaml")
        assert config.exclude_patterns == DEFAULT_EXCLUDE_PATTERNS


class TestIsExcludedPatterns:
    """Direct unit tests for the pattern check in Config._is_excluded()."""

    def test_basename_pattern_matches_any_depth(self) -> None:
        """A pattern without `/` matches the file name at any depth."""
        base = Path("/base")
        assert Config._is_excluded(base / ".DS_Store", base_dir=base) is True
        assert (
            Config._is_excluded(base / "sub" / "dir" / ".DS_Store", base_dir=base)
            is True
        )

    def test_basename_pattern_without_base_dir(self) -> None:
        """Basename patterns do not require a base_dir."""
        assert Config._is_excluded(Path(".DS_Store")) is True

    def test_wildcard_in_pattern(self) -> None:
        """Patterns support fnmatch wildcards."""
        assert (
            Config._is_excluded(Path("npm-debug.log"), exclude_patterns=("*.log",))
            is True
        )

    def test_slash_pattern_matches_relative_path(self) -> None:
        """A pattern with `/` is matched against the path relative to base_dir."""
        base = Path("/base")
        patterns = ("build/*",)
        assert (
            Config._is_excluded(
                base / "build" / "out.txt", exclude_patterns=patterns, base_dir=base
            )
            is True
        )
        assert (
            Config._is_excluded(
                base / "src" / "out.txt", exclude_patterns=patterns, base_dir=base
            )
            is False
        )

    def test_slash_pattern_skipped_without_base_dir(self) -> None:
        """Path patterns are skipped when no base_dir is available."""
        assert (
            Config._is_excluded(
                Path("/base/build/out.txt"), exclude_patterns=("build/*",)
            )
            is False
        )

    def test_suffix_check_still_works(self) -> None:
        """The existing suffix-based exclusion is unaffected (regression guard)."""
        assert Config._is_excluded(Path("ci.yml.bak")) is True
        assert Config._is_excluded(Path("ci.yml")) is False

    def test_regular_dotfiles_not_excluded(self) -> None:
        """Dotfiles like .npmrc must NOT be caught by the defaults (Issue #16)."""
        assert Config._is_excluded(Path(".npmrc")) is False
        assert Config._is_excluded(Path(".gitignore")) is False


class TestGlobalExcludeInConfig:
    """End-to-end tests: globally excluded files never appear in sync results."""

    def test_source_glob_excludes_ds_store(self, temp_hub_dir: Path) -> None:
        """``source: "*"`` no longer picks up .DS_Store on the hub side."""
        (temp_hub_dir / ".DS_Store").write_bytes(b"\x00")
        (temp_hub_dir / ".npmrc").write_text("registry=...")

        _write_config(temp_hub_dir, files=["*"])
        config = Config(temp_hub_dir / "config.yaml")

        names = [p.name for p in config.get_source_files("test_tool", "default")]
        assert ".DS_Store" not in names
        assert ".npmrc" in names  # other dotfiles still match (Issue #16)

    def test_source_glob_excludes_ds_store_in_subdir(self, temp_hub_dir: Path) -> None:
        """Recursive glob excludes .DS_Store in subdirectories too."""
        subdir = temp_hub_dir / "subdir"
        subdir.mkdir()
        (subdir / ".DS_Store").write_bytes(b"\x00")
        (subdir / "visible.txt").write_text("visible")

        _write_config(temp_hub_dir, files=["**/*"])
        config = Config(temp_hub_dir / "config.yaml")

        names = [p.name for p in config.get_source_files("test_tool", "default")]
        assert ".DS_Store" not in names
        assert "visible.txt" in names

    def test_target_glob_excludes_ds_store(
        self, temp_hub_dir: Path, temp_target_dir: Path
    ) -> None:
        """get_target_files() never returns globally excluded files."""
        (temp_target_dir / ".DS_Store").write_bytes(b"\x00")
        (temp_target_dir / "regular.txt").write_text("plain")

        _write_config(temp_hub_dir, files=["*"])
        config = Config(temp_hub_dir / "config.yaml")

        targets = config.get_target_files("test_tool", temp_target_dir, "default")
        names = [p.name for p in targets]
        assert ".DS_Store" not in names
        assert "regular.txt" in names

    def test_file_mapping_excludes_ds_store_on_both_sides(
        self, temp_hub_dir: Path, temp_target_dir: Path
    ) -> None:
        """get_file_mapping() excludes .DS_Store on hub and project sides."""
        (temp_hub_dir / ".DS_Store").write_bytes(b"\x00")
        (temp_target_dir / ".DS_Store").write_bytes(b"\x00")
        (temp_hub_dir / "shared.txt").write_text("hub")

        _write_config(temp_hub_dir, files=["*"])
        config = Config(temp_hub_dir / "config.yaml")

        mapping = config.get_file_mapping("test_tool", temp_target_dir, "default")
        src_names = [p.name for p in mapping]
        tgt_names = [p.name for p in mapping.values()]
        assert ".DS_Store" not in src_names
        assert ".DS_Store" not in tgt_names
        assert "shared.txt" in src_names

    def test_user_defined_exclude_pattern(self, temp_hub_dir: Path) -> None:
        """A user pattern in the top-level `exclude:` key excludes files."""
        (temp_hub_dir / "Thumbs.db").write_bytes(b"\x00")
        (temp_hub_dir / "keep.txt").write_text("keep")

        _write_config(temp_hub_dir, files=["*"], exclude=["Thumbs.db"])
        config = Config(temp_hub_dir / "config.yaml")

        names = [p.name for p in config.get_source_files("test_tool", "default")]
        assert "Thumbs.db" not in names
        assert "keep.txt" in names

    def test_exclusion_is_order_independent(self, temp_hub_dir: Path) -> None:
        """Unlike '!' negation entries, global excludes need no ordering care."""
        (temp_hub_dir / ".DS_Store").write_bytes(b"\x00")
        (temp_hub_dir / "a.txt").write_text("a")

        # The glob appears AFTER nothing special; no trailing negation needed.
        _write_config(temp_hub_dir, files=["*"])
        config = Config(temp_hub_dir / "config.yaml")

        names = [p.name for p in config.get_source_files("test_tool", "default")]
        assert ".DS_Store" not in names
