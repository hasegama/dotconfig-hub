"""Tests for gitignore-style negation patterns ('!' prefix) in config.yaml.

Ensures that negation entries exclude files from sync operations,
following gitignore semantics where patterns are evaluated top-to-bottom.

Related: Issue #14
"""

from pathlib import Path

import pytest
import yaml

from dotconfig_hub.config import Config, FileEntry

# -- Fixtures ----------------------------------------------------------------


@pytest.fixture
def temp_hub_dir(tmp_path: Path) -> Path:
    """Create a temporary hub directory."""
    hub = tmp_path / "hub"
    hub.mkdir()
    return hub


@pytest.fixture
def temp_target_dir(tmp_path: Path) -> Path:
    """Create a temporary target (project) directory."""
    target = tmp_path / "project"
    target.mkdir()
    return target


def _create_config(
    hub_dir: Path,
    tool_name: str,
    files: list,
    project_subdir: str = "",
) -> Config:
    """Create a Config with a given tool configuration."""
    config_data = {
        "environment_sets": {
            "test_set": {
                "description": "Test environment set",
                "tools": {tool_name: {"project_dir": project_subdir, "files": files}},
            }
        }
    }
    config_path = hub_dir / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)
    return Config(config_path)


# -- _parse_file_entry tests ------------------------------------------------


class TestParseNegationEntry:
    """Test _parse_file_entry with negation patterns."""

    def test_string_negation(self) -> None:
        """String entry with '!' prefix produces a negation FileEntry."""
        result = Config._parse_file_entry("!configs/local.toml")
        assert result == FileEntry(
            source="configs/local.toml",
            is_init_only=False,
            target=None,
            is_negation=True,
        )

    def test_dict_source_negation(self) -> None:
        """Dict entry with source starting with '!' produces a negation FileEntry."""
        result = Config._parse_file_entry({"source": "!configs/local.toml"})
        assert result == FileEntry(
            source="configs/local.toml",
            is_init_only=False,
            target=None,
            is_negation=True,
        )

    def test_negation_ignores_init_only(self) -> None:
        """Negation entry always has is_init_only=False even if init_only is set."""
        result = Config._parse_file_entry({"source": "!some_file", "init_only": True})
        assert result.is_negation is True
        assert result.is_init_only is False

    def test_negation_with_target_raises(self) -> None:
        """Negation pattern combined with rename target raises ValueError."""
        with pytest.raises(ValueError, match="Negation patterns cannot be combined"):
            Config._parse_file_entry({"source": "!file.toml", "target": "other.toml"})

    def test_negation_with_glob(self) -> None:
        """Negation pattern with glob wildcard is valid."""
        result = Config._parse_file_entry("!configs/*.local.toml")
        assert result.is_negation is True
        assert result.source == "configs/*.local.toml"

    def test_non_negation_string_unchanged(self) -> None:
        """Normal string entry is not treated as negation."""
        result = Config._parse_file_entry("configs/local.toml")
        assert result.is_negation is False
        assert result.source == "configs/local.toml"


# -- _apply_negation tests --------------------------------------------------


class TestApplyNegation:
    """Test Config._apply_negation static method."""

    def test_removes_matching_file(self, tmp_path: Path) -> None:
        """Exact filename match is removed."""
        base = tmp_path
        files = [base / "a.toml", base / "b.toml", base / "c.toml"]
        result = Config._apply_negation(files, "b.toml", base)
        assert result == [base / "a.toml", base / "c.toml"]

    def test_removes_glob_match(self, tmp_path: Path) -> None:
        """Glob pattern removes matching files."""
        base = tmp_path
        files = [base / "a.toml", base / "b.txt", base / "c.toml"]
        result = Config._apply_negation(files, "*.txt", base)
        assert result == [base / "a.toml", base / "c.toml"]

    def test_no_match_keeps_all(self, tmp_path: Path) -> None:
        """When nothing matches, list is unchanged."""
        base = tmp_path
        files = [base / "a.toml", base / "b.toml"]
        result = Config._apply_negation(files, "*.txt", base)
        assert result == files

    def test_path_outside_base_kept(self, tmp_path: Path) -> None:
        """Files outside base_dir are kept (cannot compute relative path)."""
        base = tmp_path / "sub"
        base.mkdir()
        outside = tmp_path / "other" / "file.toml"
        files = [outside]
        result = Config._apply_negation(files, "*.toml", base)
        assert result == [outside]

    def test_subdirectory_pattern(self, tmp_path: Path) -> None:
        """Pattern with subdirectory matches correctly."""
        base = tmp_path
        files = [
            base / "configs" / "a.toml",
            base / "configs" / "local.toml",
            base / "other" / "b.toml",
        ]
        result = Config._apply_negation(files, "configs/local.toml", base)
        assert result == [base / "configs" / "a.toml", base / "other" / "b.toml"]


# -- _resolve_source_files integration tests --------------------------------


class TestResolveSourceFilesNegation:
    """Test negation patterns in _resolve_source_files."""

    def test_glob_with_negation(self, temp_hub_dir: Path) -> None:
        """Glob pattern followed by negation excludes specific files."""
        configs = temp_hub_dir / "configs"
        configs.mkdir()
        (configs / "base.toml").write_text("base")
        (configs / "local.toml").write_text("local")
        (configs / "dev.toml").write_text("dev")

        config = _create_config(
            temp_hub_dir,
            "ruff",
            ["configs/*.toml", "!configs/local.toml"],
            project_subdir="",
        )
        result = config.get_source_files("ruff", "test_set")
        names = {p.name for p in result}
        assert "base.toml" in names
        assert "dev.toml" in names
        assert "local.toml" not in names

    def test_multiple_negations(self, temp_hub_dir: Path) -> None:
        """Multiple negation entries all take effect."""
        configs = temp_hub_dir / "configs"
        configs.mkdir()
        (configs / "a.toml").write_text("a")
        (configs / "b.toml").write_text("b")
        (configs / "c.toml").write_text("c")

        config = _create_config(
            temp_hub_dir,
            "tool",
            ["configs/*.toml", "!configs/a.toml", "!configs/b.toml"],
        )
        result = config.get_source_files("tool", "test_set")
        names = {p.name for p in result}
        assert names == {"c.toml"}

    def test_negation_only_has_no_effect(self, temp_hub_dir: Path) -> None:
        """Negation without prior positive pattern produces empty result."""
        (temp_hub_dir / "file.toml").write_text("x")
        config = _create_config(temp_hub_dir, "tool", ["!file.toml"])
        result = config.get_source_files("tool", "test_set")
        assert result == []

    def test_re_include_after_negation(self, temp_hub_dir: Path) -> None:
        """A file negated then re-added by a later entry is included."""
        configs = temp_hub_dir / "configs"
        configs.mkdir()
        (configs / "a.toml").write_text("a")
        (configs / "b.toml").write_text("b")

        config = _create_config(
            temp_hub_dir,
            "tool",
            [
                "configs/*.toml",
                "!configs/a.toml",
                "configs/a.toml",  # re-include
            ],
        )
        result = config.get_source_files("tool", "test_set")
        names = {p.name for p in result}
        assert "a.toml" in names
        assert "b.toml" in names


# -- get_target_files integration tests --------------------------------------


class TestGetTargetFilesNegation:
    """Test negation patterns in get_target_files."""

    def test_negation_excludes_target(
        self, temp_hub_dir: Path, temp_target_dir: Path
    ) -> None:
        """Negation removes matching files from target list."""
        configs = temp_target_dir / "configs"
        configs.mkdir()
        (configs / "base.toml").write_text("base")
        (configs / "local.toml").write_text("local")

        config = _create_config(
            temp_hub_dir,
            "tool",
            ["configs/*.toml", "!configs/local.toml"],
        )
        result = config.get_target_files("tool", temp_target_dir, "test_set")
        names = {p.name for p in result}
        assert "base.toml" in names
        assert "local.toml" not in names


# -- get_file_mapping integration tests --------------------------------------


class TestGetFileMappingNegation:
    """Test negation patterns in get_file_mapping."""

    def test_negation_removes_from_mapping(
        self, temp_hub_dir: Path, temp_target_dir: Path
    ) -> None:
        """Negation pattern removes entries from the file mapping dict."""
        configs_hub = temp_hub_dir / "configs"
        configs_hub.mkdir()
        (configs_hub / "base.toml").write_text("base")
        (configs_hub / "local.toml").write_text("local")
        (configs_hub / "dev.toml").write_text("dev")

        configs_target = temp_target_dir / "configs"
        configs_target.mkdir()
        (configs_target / "base.toml").write_text("base")
        (configs_target / "local.toml").write_text("local")
        (configs_target / "dev.toml").write_text("dev")

        config = _create_config(
            temp_hub_dir,
            "tool",
            ["configs/*.toml", "!configs/local.toml"],
        )
        mapping = config.get_file_mapping("tool", temp_target_dir, "test_set")
        source_names = {s.name for s in mapping}
        assert "base.toml" in source_names
        assert "dev.toml" in source_names
        assert "local.toml" not in source_names

    def test_negation_with_dict_format(
        self, temp_hub_dir: Path, temp_target_dir: Path
    ) -> None:
        """Dict-format negation entry works in file mapping."""
        configs_hub = temp_hub_dir / "configs"
        configs_hub.mkdir()
        (configs_hub / "a.toml").write_text("a")
        (configs_hub / "b.toml").write_text("b")

        configs_target = temp_target_dir / "configs"
        configs_target.mkdir()
        (configs_target / "a.toml").write_text("a")
        (configs_target / "b.toml").write_text("b")

        config = _create_config(
            temp_hub_dir,
            "tool",
            [
                "configs/*.toml",
                {"source": "!configs/b.toml"},
            ],
        )
        mapping = config.get_file_mapping("tool", temp_target_dir, "test_set")
        source_names = {s.name for s in mapping}
        assert "a.toml" in source_names
        assert "b.toml" not in source_names
