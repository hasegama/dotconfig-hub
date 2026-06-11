"""Tests for dotfile matching via glob patterns in config.yaml.

Related: Issue #16 - glob patterns must match dotfiles such as .npmrc, .eslintrc.
Python's stdlib ``glob.glob()`` skips files whose name starts with ``.`` unless
``include_hidden=True`` (3.11+) is passed. Config._glob() handles both 3.11+
and the 3.9/3.10 fallback.
"""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
import yaml

from dotconfig_hub.config import Config


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


def _write_config(hub_dir: Path, files: list) -> Path:
    """Write a minimal config.yaml that maps a single tool to the hub root."""
    config_data = {
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
    config_path = hub_dir / "config.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config_data, f)
    return config_path


class TestGlobHelper:
    """Direct unit tests for Config._glob()."""

    def test_matches_regular_files(self, tmp_path: Path) -> None:
        """_glob() returns regular (non-dot) files for a wildcard pattern."""
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        results = Config._glob(str(tmp_path / "*.txt"))
        names = sorted(Path(p).name for p in results)
        assert names == ["a.txt", "b.txt"]

    def test_matches_dotfiles(self, tmp_path: Path) -> None:
        """_glob() matches dotfiles such as .npmrc with a ``*`` pattern."""
        (tmp_path / ".npmrc").write_text("registry=...")
        (tmp_path / ".eslintrc").write_text("{}")
        (tmp_path / "regular.txt").write_text("plain")
        results = Config._glob(str(tmp_path / "*"))
        names = sorted(Path(p).name for p in results)
        assert ".npmrc" in names
        assert ".eslintrc" in names
        assert "regular.txt" in names

    def test_no_duplicates(self, tmp_path: Path) -> None:
        """Regular files appear only once even though _glob() may run two passes."""
        (tmp_path / "a.txt").write_text("a")
        results = Config._glob(str(tmp_path / "*"))
        assert len(results) == len(set(results))

    def test_suffix_pattern_matches_dot_prefixed(self, tmp_path: Path) -> None:
        """``*.toml`` matches ``.cargo.toml`` (file whose name starts with a dot)."""
        (tmp_path / ".cargo.toml").write_text("")
        (tmp_path / "pyproject.toml").write_text("")
        results = Config._glob(str(tmp_path / "*.toml"))
        names = sorted(Path(p).name for p in results)
        assert ".cargo.toml" in names
        assert "pyproject.toml" in names


class TestDotfileGlobInConfig:
    """End-to-end tests: glob patterns in config.yaml must pick up dotfiles."""

    def test_source_glob_matches_dotfiles(
        self, temp_hub_dir: Path, temp_target_dir: Path
    ) -> None:
        """``source: "*"`` matches .npmrc, .eslintrc, .gitignore, .env on hub side."""
        for name in (".npmrc", ".eslintrc", ".gitignore", ".env", "bun.lock"):
            (temp_hub_dir / name).write_text("x")

        _write_config(temp_hub_dir, files=["*"])
        config = Config(temp_hub_dir / "config.yaml")

        sources = config.get_source_files("test_tool", env_set="default")
        names = sorted(p.name for p in sources)
        # config.yaml itself is in the directory; the * pattern picks it up too,
        # which is fine for this test - we just assert the dotfiles are included.
        for expected in (".npmrc", ".eslintrc", ".gitignore", ".env", "bun.lock"):
            assert expected in names, f"{expected} should be matched by '*'"

    def test_source_suffix_glob_matches_dot_prefixed(
        self, temp_hub_dir: Path
    ) -> None:
        """``source: "*.toml"`` matches ``.cargo.toml`` and ``pyproject.toml``."""
        (temp_hub_dir / ".cargo.toml").write_text("")
        (temp_hub_dir / "pyproject.toml").write_text("")

        _write_config(temp_hub_dir, files=["*.toml"])
        config = Config(temp_hub_dir / "config.yaml")

        sources = config.get_source_files("test_tool", env_set="default")
        names = sorted(p.name for p in sources)
        assert ".cargo.toml" in names
        assert "pyproject.toml" in names

    def test_subdir_glob_matches_dotfiles(self, temp_hub_dir: Path) -> None:
        """Glob inside a subdirectory matches dotfiles in that subdirectory."""
        subdir = temp_hub_dir / "subdir"
        subdir.mkdir()
        (subdir / ".hidden").write_text("hidden")
        (subdir / "visible.txt").write_text("visible")

        _write_config(temp_hub_dir, files=["subdir/*"])
        config = Config(temp_hub_dir / "config.yaml")

        sources = config.get_source_files("test_tool", env_set="default")
        names = sorted(p.name for p in sources)
        assert ".hidden" in names
        assert "visible.txt" in names

    def test_explicit_dotfile_still_works(self, temp_hub_dir: Path) -> None:
        """Non-glob explicit dotfile path continues to work (regression guard)."""
        (temp_hub_dir / ".npmrc").write_text("registry=...")

        _write_config(temp_hub_dir, files=[".npmrc"])
        config = Config(temp_hub_dir / "config.yaml")

        sources = config.get_source_files("test_tool", env_set="default")
        names = [p.name for p in sources]
        assert ".npmrc" in names

    def test_target_glob_matches_dotfiles(
        self, temp_hub_dir: Path, temp_target_dir: Path
    ) -> None:
        """get_target_files() picks up dotfiles in the target dir via ``*``."""
        (temp_target_dir / ".npmrc").write_text("registry=...")
        (temp_target_dir / "regular.txt").write_text("plain")

        _write_config(temp_hub_dir, files=["*"])
        config = Config(temp_hub_dir / "config.yaml")

        targets = config.get_target_files(
            "test_tool", temp_target_dir, env_set="default"
        )
        names = sorted(p.name for p in targets)
        assert ".npmrc" in names
        assert "regular.txt" in names

    def test_file_mapping_includes_dotfiles(
        self, temp_hub_dir: Path, temp_target_dir: Path
    ) -> None:
        """get_file_mapping() maps dotfiles between hub and target sides."""
        (temp_hub_dir / ".npmrc").write_text("hub-side")
        (temp_target_dir / ".npmrc").write_text("target-side")

        _write_config(temp_hub_dir, files=["*"])
        config = Config(temp_hub_dir / "config.yaml")

        mapping = config.get_file_mapping(
            "test_tool", temp_target_dir, env_set="default"
        )
        # The mapping is source-path -> target-path; check by leaf name.
        src_names = sorted(p.name for p in mapping)
        tgt_names = sorted(p.name for p in mapping.values())
        assert ".npmrc" in src_names
        assert ".npmrc" in tgt_names
