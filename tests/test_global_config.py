"""Tests for global configuration functionality (Issue #2).

Covers:
- Setup with existing global config defaults
- Setup without global config (fallback to interactive)
- Global config with invalid paths (warning behavior)
- Priority testing (global vs project vs CLI)
- Interactive prompt acceptance/rejection of global defaults
"""

import tempfile
import warnings
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from dotconfig_hub.cli import global_config, setup
from dotconfig_hub.project_config import ProjectConfig


@pytest.fixture
def runner() -> CliRunner:
    """Create a Click test runner."""
    return CliRunner()


@pytest.fixture
def temp_templates_dir() -> Generator[Path, None, None]:
    """Create a temporary templates directory with valid config.yaml."""
    with tempfile.TemporaryDirectory() as temp_dir:
        templates_dir = Path(temp_dir)

        config_content = {
            "environment_sets": {
                "python_dev": {
                    "description": "Python development environment",
                    "tools": {},
                },
                "web_dev": {
                    "description": "Web development environment",
                    "tools": {},
                },
            }
        }

        config_file = templates_dir / "config.yaml"
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(config_content, f, default_flow_style=False)

        yield templates_dir


@pytest.fixture
def temp_project_dir() -> Generator[Path, None, None]:
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


class TestSetupWithGlobalConfig:
    """Test setup command when global configuration exists."""

    def test_setup_uses_global_defaults_when_accepted(
        self,
        runner: CliRunner,
        temp_templates_dir: Path,
        temp_project_dir: Path,
    ) -> None:
        """Setup should offer global defaults and apply them when user accepts."""
        mock_config = MagicMock()
        mock_config.exists.return_value = False
        mock_config.config_path = temp_project_dir / "dotconfig-hub.yaml"
        mock_config.get_global_templates_source.return_value = temp_templates_dir
        mock_config.get_global_environment_sets.return_value = ["python_dev"]

        with patch("dotconfig_hub.cli.Path.cwd", return_value=temp_project_dir):
            with patch("dotconfig_hub.cli.ProjectConfig", return_value=mock_config):
                with patch("dotconfig_hub.cli.Confirm.ask", return_value=True):
                    result = runner.invoke(setup)

        assert result.exit_code == 0
        assert "Found global default templates source" in result.output
        assert "Templates source configured" in result.output
        # Verify the global templates source was used
        call_args = mock_config.set_templates_source.call_args[0][0]
        assert call_args.resolve() == temp_templates_dir.resolve()
        mock_config.save_config.assert_called_once()


class TestSetupWithoutGlobalConfig:
    """Test setup command when no global configuration exists (fallback)."""

    @patch("dotconfig_hub.cli.Prompt.ask")
    def test_setup_falls_back_to_interactive_without_global_config(
        self,
        mock_prompt: MagicMock,
        runner: CliRunner,
        temp_templates_dir: Path,
        temp_project_dir: Path,
    ) -> None:
        """Without global config, setup should fall back to interactive prompts."""
        mock_prompt.return_value = str(temp_templates_dir)

        mock_config = MagicMock()
        mock_config.exists.return_value = False
        mock_config.config_path = temp_project_dir / "dotconfig-hub.yaml"
        mock_config.get_global_templates_source.return_value = None
        mock_config.get_global_environment_sets.return_value = []

        with patch("dotconfig_hub.cli.Path.cwd", return_value=temp_project_dir):
            with patch("dotconfig_hub.cli.ProjectConfig", return_value=mock_config):
                result = runner.invoke(setup)

        assert result.exit_code == 0
        assert "Templates source configured" in result.output
        # Should NOT show global default messages
        assert "Found global default templates source" not in result.output
        mock_prompt.assert_called_once_with("Templates directory path")


class TestGlobalConfigWithInvalidPaths:
    """Test global configuration behavior with invalid paths."""

    def test_load_global_config_with_invalid_yaml_emits_warning(
        self, temp_project_dir: Path
    ) -> None:
        """Invalid global YAML should emit a warning and return empty config."""
        with tempfile.TemporaryDirectory() as home_dir:
            global_config_path = Path(home_dir) / "dotconfig-hub.yaml"
            global_config_path.write_text("invalid: yaml: [broken", encoding="utf-8")

            with patch.object(ProjectConfig, "GLOBAL_CONFIG_PATH", global_config_path):
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    config = ProjectConfig(project_dir=temp_project_dir)

                assert len(caught) == 1
                assert "Error loading global config" in str(caught[0].message)
                # Should still initialize with empty global config
                assert config.global_config_data == {}

    def test_global_templates_source_returns_none_for_nonexistent_path(
        self, temp_project_dir: Path
    ) -> None:
        """get_global_templates_source should return None if the path doesn't exist."""
        with tempfile.TemporaryDirectory() as home_dir:
            global_config_path = Path(home_dir) / "dotconfig-hub.yaml"
            config_content = {"templates_source": "/nonexistent/path/to/templates"}
            with open(global_config_path, "w", encoding="utf-8") as f:
                yaml.dump(config_content, f)

            with patch.object(ProjectConfig, "GLOBAL_CONFIG_PATH", global_config_path):
                config = ProjectConfig(project_dir=temp_project_dir)
                result = config.get_global_templates_source()

            assert result is None


class TestConfigPriority:
    """Test configuration priority: CLI > project > global > default."""

    def test_project_config_overrides_global_config(
        self, temp_project_dir: Path
    ) -> None:
        """Project-level config should take priority over global config."""
        with tempfile.TemporaryDirectory() as home_dir:
            # Create global config with templates_source
            global_config_path = Path(home_dir) / "dotconfig-hub.yaml"
            global_content = {
                "templates_source": "/global/templates",
                "active_environment_sets": ["global_env"],
            }
            with open(global_config_path, "w", encoding="utf-8") as f:
                yaml.dump(global_content, f)

            # Create project config with different templates_source
            project_config_path = temp_project_dir / "dotconfig-hub.yaml"
            project_content = {
                "templates_source": "/project/templates",
                "active_environment_sets": ["project_env"],
            }
            with open(project_config_path, "w", encoding="utf-8") as f:
                yaml.dump(project_content, f)

            with patch.object(ProjectConfig, "GLOBAL_CONFIG_PATH", global_config_path):
                config = ProjectConfig(project_dir=temp_project_dir)

            # Project config should win over global
            assert config.config_data["templates_source"] == "/project/templates"
            assert config.config_data["active_environment_sets"] == ["project_env"]

    def test_global_config_overrides_defaults(self, temp_project_dir: Path) -> None:
        """Global config should override default values."""
        with tempfile.TemporaryDirectory() as home_dir:
            global_config_path = Path(home_dir) / "dotconfig-hub.yaml"
            global_content = {
                "templates_source": "/global/templates",
                "active_environment_sets": ["global_env"],
            }
            with open(global_config_path, "w", encoding="utf-8") as f:
                yaml.dump(global_content, f)

            with patch.object(ProjectConfig, "GLOBAL_CONFIG_PATH", global_config_path):
                config = ProjectConfig(project_dir=temp_project_dir)

            # Global config should override defaults (None, [])
            assert config.config_data["templates_source"] == "/global/templates"
            assert config.config_data["active_environment_sets"] == ["global_env"]

    def test_cli_option_overrides_global_defaults(
        self,
        runner: CliRunner,
        temp_templates_dir: Path,
        temp_project_dir: Path,
    ) -> None:
        """CLI --templates-dir should override global configuration."""
        mock_config = MagicMock()
        mock_config.exists.return_value = False
        mock_config.config_path = temp_project_dir / "dotconfig-hub.yaml"
        mock_config.get_global_templates_source.return_value = Path("/some/global/path")
        mock_config.get_global_environment_sets.return_value = ["global_env"]

        with patch("dotconfig_hub.cli.Path.cwd", return_value=temp_project_dir):
            with patch("dotconfig_hub.cli.ProjectConfig", return_value=mock_config):
                result = runner.invoke(
                    setup, ["--templates-dir", str(temp_templates_dir)]
                )

        assert result.exit_code == 0
        assert "Templates source configured" in result.output
        # Should use CLI-provided path, not global default
        call_args = mock_config.set_templates_source.call_args[0][0]
        assert call_args.resolve() == temp_templates_dir.resolve()


class TestInteractiveDefaultsAcceptanceRejection:
    """Test interactive prompt for accepting/rejecting global defaults."""

    def test_user_rejects_global_defaults_and_enters_custom_path(
        self,
        runner: CliRunner,
        temp_templates_dir: Path,
        temp_project_dir: Path,
    ) -> None:
        """User rejects global defaults and provides a custom path interactively."""
        mock_config = MagicMock()
        mock_config.exists.return_value = False
        mock_config.config_path = temp_project_dir / "dotconfig-hub.yaml"
        mock_config.get_global_templates_source.return_value = Path("/some/global/path")
        mock_config.get_global_environment_sets.return_value = ["global_env"]

        with patch("dotconfig_hub.cli.Path.cwd", return_value=temp_project_dir):
            with patch("dotconfig_hub.cli.ProjectConfig", return_value=mock_config):
                with patch("dotconfig_hub.cli.Confirm.ask", return_value=False):
                    with patch(
                        "dotconfig_hub.cli.Prompt.ask",
                        return_value=str(temp_templates_dir),
                    ):
                        result = runner.invoke(setup)

        assert result.exit_code == 0
        assert "Please enter a different templates directory path" in result.output
        assert "Templates source configured" in result.output
        # Should use the manually entered path
        call_args = mock_config.set_templates_source.call_args[0][0]
        assert call_args.resolve() == temp_templates_dir.resolve()

    def test_user_accepts_global_defaults_with_environment_sets_shown(
        self,
        runner: CliRunner,
        temp_templates_dir: Path,
        temp_project_dir: Path,
    ) -> None:
        """Accepting defaults should show global environment sets in output."""
        mock_config = MagicMock()
        mock_config.exists.return_value = False
        mock_config.config_path = temp_project_dir / "dotconfig-hub.yaml"
        mock_config.get_global_templates_source.return_value = temp_templates_dir
        mock_config.get_global_environment_sets.return_value = [
            "python_dev",
            "web_dev",
        ]

        with patch("dotconfig_hub.cli.Path.cwd", return_value=temp_project_dir):
            with patch("dotconfig_hub.cli.ProjectConfig", return_value=mock_config):
                with patch("dotconfig_hub.cli.Confirm.ask", return_value=True):
                    result = runner.invoke(setup)

        assert result.exit_code == 0
        assert "Default environment sets:" in result.output
        assert "python_dev" in result.output
        assert "web_dev" in result.output


class TestGlobalConfigCommand:
    """Test global-config CLI command (Issue #2)."""

    def test_global_config_with_all_options(
        self,
        runner: CliRunner,
        temp_templates_dir: Path,
    ) -> None:
        """Providing --templates-dir and --env-sets should save global config."""
        mock_config = MagicMock()
        mock_config.GLOBAL_CONFIG_PATH = Path("/mock/global/config")

        with patch("dotconfig_hub.cli.ProjectConfig", return_value=mock_config):
            result = runner.invoke(
                global_config,
                [
                    "--templates-dir",
                    str(temp_templates_dir),
                    "--env-sets",
                    "python_dev,web_dev",
                ],
            )

        assert result.exit_code == 0
        assert "Global templates source" in result.output
        assert "Global environment sets" in result.output
        mock_config.save_global_config.assert_called_once()
        call_args = mock_config.save_global_config.call_args
        assert call_args[0][0].resolve() == temp_templates_dir.resolve()
        assert call_args[0][1] == ["python_dev", "web_dev"]

    def test_global_config_with_templates_dir_only(
        self,
        runner: CliRunner,
        temp_templates_dir: Path,
    ) -> None:
        """Providing only --templates-dir should prompt for env-sets interactively."""
        mock_config = MagicMock()
        mock_config.GLOBAL_CONFIG_PATH = Path("/mock/global/config")
        mock_config.get_global_environment_sets.return_value = []

        with patch("dotconfig_hub.cli.ProjectConfig", return_value=mock_config):
            with patch("dotconfig_hub.cli.Prompt.ask", return_value="python_dev"):
                result = runner.invoke(
                    global_config,
                    ["--templates-dir", str(temp_templates_dir)],
                )

        assert result.exit_code == 0
        assert "Global templates source" in result.output
        mock_config.save_global_config.assert_called_once()

    def test_global_config_interactive_new(
        self,
        runner: CliRunner,
        temp_templates_dir: Path,
    ) -> None:
        """Without any options, should prompt for all inputs interactively."""
        mock_config = MagicMock()
        mock_config.GLOBAL_CONFIG_PATH = Path("/mock/global/config")
        mock_config.get_global_templates_source.return_value = None
        mock_config.get_global_environment_sets.return_value = []

        with patch("dotconfig_hub.cli.ProjectConfig", return_value=mock_config):
            with patch(
                "dotconfig_hub.cli.Prompt.ask",
                side_effect=[str(temp_templates_dir), "python_dev"],
            ):
                result = runner.invoke(global_config)

        assert result.exit_code == 0
        assert "Global templates source" in result.output
        mock_config.save_global_config.assert_called_once()

    def test_global_config_keeps_existing_templates_dir(
        self,
        runner: CliRunner,
        temp_templates_dir: Path,
    ) -> None:
        """When user declines to change existing templates dir, keep the current one."""
        mock_config = MagicMock()
        mock_config.GLOBAL_CONFIG_PATH = Path("/mock/global/config")
        mock_config.get_global_templates_source.return_value = temp_templates_dir
        mock_config.get_global_environment_sets.return_value = ["python_dev"]

        with patch("dotconfig_hub.cli.ProjectConfig", return_value=mock_config):
            with patch("dotconfig_hub.cli.Confirm.ask", return_value=False):
                result = runner.invoke(global_config)

        assert result.exit_code == 0
        mock_config.save_global_config.assert_called_once()
        call_args = mock_config.save_global_config.call_args
        assert call_args[0][0].resolve() == temp_templates_dir.resolve()
        assert call_args[0][1] == ["python_dev"]

    def test_global_config_rejects_invalid_env_sets(
        self,
        runner: CliRunner,
        temp_templates_dir: Path,
    ) -> None:
        """Invalid environment set names should be rejected."""
        mock_config = MagicMock()

        with patch("dotconfig_hub.cli.ProjectConfig", return_value=mock_config):
            result = runner.invoke(
                global_config,
                [
                    "--templates-dir",
                    str(temp_templates_dir),
                    "--env-sets",
                    "nonexistent_env",
                ],
            )

        assert result.exit_code == 0
        assert "Invalid environment sets" in result.output
        mock_config.save_global_config.assert_not_called()

    def test_global_config_missing_config_yaml(
        self,
        runner: CliRunner,
    ) -> None:
        """Templates dir without config.yaml should show error."""
        mock_config = MagicMock()

        with tempfile.TemporaryDirectory() as empty_dir:
            with patch("dotconfig_hub.cli.ProjectConfig", return_value=mock_config):
                result = runner.invoke(
                    global_config,
                    ["--templates-dir", empty_dir],
                )

        assert result.exit_code == 0
        assert "config.yaml not found" in result.output
        mock_config.save_global_config.assert_not_called()

    def test_global_config_cancel_during_path_input(
        self,
        runner: CliRunner,
    ) -> None:
        """Cancelling during path input should abort gracefully."""
        mock_config = MagicMock()
        mock_config.get_global_templates_source.return_value = None

        with patch("dotconfig_hub.cli.ProjectConfig", return_value=mock_config):
            with patch(
                "dotconfig_hub.cli.Prompt.ask", return_value="/nonexistent/path"
            ):
                with patch("dotconfig_hub.cli.Confirm.ask", return_value=False):
                    result = runner.invoke(global_config)

        assert result.exit_code == 0
        assert "cancelled" in result.output.lower()
        mock_config.save_global_config.assert_not_called()
