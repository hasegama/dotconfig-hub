"""Tests for dotconfig-hub CLI setup command."""

import os
import tempfile
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from dotconfig_hub.cli import setup


@pytest.fixture
def runner():
    """Create a Click test runner."""
    return CliRunner()


@pytest.fixture
def temp_templates_dir():
    """Create a temporary templates directory with valid config.yaml."""
    with tempfile.TemporaryDirectory() as temp_dir:
        templates_dir = Path(temp_dir)
        
        # Create valid config.yaml
        config_content = {
            "environment_sets": {
                "my_project_init_template": {
                    "description": "Complete project initialization template",
                    "tools": {
                        "claude_config": {
                            "project_dir": "my_project_init_template",
                            "files": [".claude/CLAUDE.md"]
                        }
                    }
                }
            }
        }
        
        config_file = templates_dir / "config.yaml"
        with open(config_file, 'w', encoding='utf-8') as f:
            yaml.dump(config_content, f, default_flow_style=False)
        
        yield templates_dir


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_dir = Path(temp_dir)
        yield project_dir


@pytest.fixture
def mock_project_config():
    """Create a mock ProjectConfig instance."""
    mock_config = MagicMock()
    mock_config.exists.return_value = False
    mock_config.config_path = Path("/tmp/test/dotconfig-hub.yaml")
    return mock_config


class TestSetupCommandWithOption:
    """Test setup command with --templates-dir option."""
    
    def test_setup_with_valid_templates_dir(self, runner, temp_templates_dir, temp_project_dir, mock_project_config):
        """Test setup command with valid templates directory."""
        with patch('dotconfig_hub.cli.Path.cwd', return_value=temp_project_dir):
            with patch('dotconfig_hub.cli.ProjectConfig', return_value=mock_project_config):
                result = runner.invoke(setup, ['--templates-dir', str(temp_templates_dir)])
        
        assert result.exit_code == 0
        assert "Templates source configured" in result.output
        assert "Found 1 environment sets" in result.output
        
        # Verify ProjectConfig methods were called
        mock_project_config.exists.assert_called_once()
        # Check that set_templates_source was called with the resolved path
        call_args = mock_project_config.set_templates_source.call_args[0][0]
        assert call_args.resolve() == temp_templates_dir.resolve()
        mock_project_config.save_config.assert_called_once()
    
    def test_setup_with_nonexistent_templates_dir(self, runner, temp_project_dir):
        """Test setup command with non-existent templates directory."""
        nonexistent_dir = "/path/that/does/not/exist"
        
        with patch('dotconfig_hub.cli.Path.cwd', return_value=temp_project_dir):
            result = runner.invoke(setup, ['--templates-dir', nonexistent_dir])
        
        # Should fail due to click.Path(exists=True) validation
        assert result.exit_code != 0
        assert "does not exist" in result.output
    
    def test_setup_with_quoted_path(self, runner, temp_templates_dir, temp_project_dir):
        """Test setup command with quoted path (tests the original issue)."""
        quoted_path = f'"{temp_templates_dir}"'
        
        with patch('dotconfig_hub.cli.Path.cwd', return_value=temp_project_dir):
            # This should fail with current implementation due to click validation
            result = runner.invoke(setup, ['--templates-dir', quoted_path])
            assert result.exit_code != 0
    
    def test_setup_with_tilde_path(self, runner, temp_project_dir, mock_project_config):
        """Test setup command with tilde path expansion."""
        # This test demonstrates that the current implementation fails with tilde paths
        # due to Click's path validation before expansion
        with tempfile.TemporaryDirectory() as home_dir:
            templates_dir = Path(home_dir) / "templates"
            templates_dir.mkdir()
            
            # Create valid config.yaml
            config_content = {
                "environment_sets": {
                    "test_env": {
                        "description": "Test environment",
                        "tools": {}
                    }
                }
            }
            config_file = templates_dir / "config.yaml"
            with open(config_file, 'w', encoding='utf-8') as f:
                yaml.dump(config_content, f)
            
            with patch.dict(os.environ, {'HOME': home_dir}):
                with patch('dotconfig_hub.cli.Path.cwd', return_value=temp_project_dir):
                    with patch('dotconfig_hub.cli.ProjectConfig', return_value=mock_project_config):
                        result = runner.invoke(setup, ['--templates-dir', '~/templates'])
            
            # Currently fails due to Click validation, would need CLI modification to support
            assert result.exit_code != 0
            assert "does not exist" in result.output


class TestSetupCommandInteractive:
    """Test setup command interactive prompts."""
    
    @patch('dotconfig_hub.cli.Prompt.ask')
    def test_setup_interactive_valid_path(self, mock_prompt, runner, temp_templates_dir, temp_project_dir, mock_project_config):
        """Test interactive setup with valid path input."""
        mock_prompt.return_value = str(temp_templates_dir)
        
        with patch('dotconfig_hub.cli.Path.cwd', return_value=temp_project_dir):
            with patch('dotconfig_hub.cli.ProjectConfig', return_value=mock_project_config):
                result = runner.invoke(setup)
        
        assert result.exit_code == 0
        assert "Templates source configured" in result.output
        mock_prompt.assert_called_once_with("Templates directory path")
    
    @patch('dotconfig_hub.cli.Prompt.ask')
    @patch('dotconfig_hub.cli.Confirm.ask')
    def test_setup_interactive_invalid_then_valid_path(self, mock_confirm, mock_prompt, runner, temp_templates_dir, temp_project_dir, mock_project_config):
        """Test interactive setup with invalid path first, then valid path."""
        mock_prompt.side_effect = ["/invalid/path", str(temp_templates_dir)]
        mock_confirm.return_value = True  # Try again
        
        with patch('dotconfig_hub.cli.Path.cwd', return_value=temp_project_dir):
            with patch('dotconfig_hub.cli.ProjectConfig', return_value=mock_project_config):
                result = runner.invoke(setup)
        
        assert result.exit_code == 0
        assert "Templates source configured" in result.output
        assert mock_prompt.call_count == 2
        mock_confirm.assert_called_once()
    
    @patch('dotconfig_hub.cli.Prompt.ask')
    @patch('dotconfig_hub.cli.Confirm.ask')
    def test_setup_interactive_cancel_after_invalid_path(self, mock_confirm, mock_prompt, runner, temp_project_dir):
        """Test interactive setup cancellation after invalid path."""
        mock_prompt.return_value = "/invalid/path"
        mock_confirm.return_value = False  # Don't try again
        
        with patch('dotconfig_hub.cli.Path.cwd', return_value=temp_project_dir):
            result = runner.invoke(setup)
        
        assert result.exit_code == 0
        assert "Setup cancelled" in result.output
        mock_confirm.assert_called_once()
    
    @patch('dotconfig_hub.cli.Prompt.ask')
    def test_setup_interactive_quoted_path(self, mock_prompt, runner, temp_templates_dir, temp_project_dir, mock_project_config):
        """Test interactive setup with quoted path input."""
        quoted_path = f'"{temp_templates_dir}"'
        mock_prompt.return_value = quoted_path
        
        with patch('dotconfig_hub.cli.Path.cwd', return_value=temp_project_dir):
            with patch('dotconfig_hub.cli.ProjectConfig', return_value=mock_project_config):
                result = runner.invoke(setup)
        
        # Should handle quoted paths correctly in prompt
        assert result.exit_code == 0
        assert "Templates source configured" in result.output
    
    @patch('dotconfig_hub.cli.Prompt.ask')
    def test_setup_interactive_empty_input(self, mock_prompt, runner, temp_project_dir):
        """Test interactive setup with empty input."""
        mock_prompt.side_effect = ["", "  ", str(temp_project_dir)]  # Empty, whitespace, then valid
        
        with patch('dotconfig_hub.cli.Path.cwd', return_value=temp_project_dir):
            result = runner.invoke(setup)
        
        # Should prompt multiple times for empty/whitespace input
        assert mock_prompt.call_count >= 2


class TestSetupCommandValidation:
    """Test setup command validation logic."""
    
    def test_setup_missing_config_yaml(self, runner, temp_project_dir):
        """Test setup with directory missing config.yaml."""
        with tempfile.TemporaryDirectory() as temp_dir:
            empty_dir = Path(temp_dir)
            
            with patch('dotconfig_hub.cli.Path.cwd', return_value=temp_project_dir):
                result = runner.invoke(setup, ['--templates-dir', str(empty_dir)])
            
            assert result.exit_code == 0  # Command doesn't fail, but shows error
            assert "config.yaml not found" in result.output
    
    def test_setup_invalid_config_yaml(self, runner, temp_project_dir):
        """Test setup with invalid config.yaml format."""
        with tempfile.TemporaryDirectory() as temp_dir:
            templates_dir = Path(temp_dir)
            
            # Create invalid config.yaml (missing environment_sets)
            config_file = templates_dir / "config.yaml"
            with open(config_file, 'w', encoding='utf-8') as f:
                yaml.dump({"invalid": "config"}, f)
            
            with patch('dotconfig_hub.cli.Path.cwd', return_value=temp_project_dir):
                result = runner.invoke(setup, ['--templates-dir', str(templates_dir)])
            
            assert result.exit_code == 0  # Command doesn't fail, but shows error
            assert "Invalid config.yaml format" in result.output
    
    def test_setup_malformed_config_yaml(self, runner, temp_project_dir):
        """Test setup with malformed YAML file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            templates_dir = Path(temp_dir)
            
            # Create malformed YAML file
            config_file = templates_dir / "config.yaml"
            with open(config_file, 'w', encoding='utf-8') as f:
                f.write("invalid: yaml: content: [")
            
            with patch('dotconfig_hub.cli.Path.cwd', return_value=temp_project_dir):
                result = runner.invoke(setup, ['--templates-dir', str(templates_dir)])
            
            assert result.exit_code == 0  # Command doesn't fail, but shows error
            assert "Error reading templates config" in result.output


class TestSetupCommandOverride:
    """Test setup command override behavior."""
    
    @patch('dotconfig_hub.cli.Confirm.ask')
    def test_setup_override_existing_config(self, mock_confirm, runner, temp_templates_dir, temp_project_dir):
        """Test setup command overriding existing configuration."""
        mock_confirm.return_value = True  # Confirm override
        
        # Create mock existing config
        mock_project_config = MagicMock()
        mock_project_config.exists.return_value = True
        mock_project_config.get_templates_source.return_value = Path("/other/templates/dir")
        mock_project_config.config_path = temp_project_dir / "dotconfig-hub.yaml"
        
        with patch('dotconfig_hub.cli.Path.cwd', return_value=temp_project_dir):
            with patch('dotconfig_hub.cli.ProjectConfig', return_value=mock_project_config):
                result = runner.invoke(setup, ['--templates-dir', str(temp_templates_dir)])
        
        assert result.exit_code == 0
        assert "Templates source configured" in result.output
        mock_confirm.assert_called_once()
        # Check that set_templates_source was called with the resolved path
        call_args = mock_project_config.set_templates_source.call_args[0][0]
        assert call_args.resolve() == temp_templates_dir.resolve()
        mock_project_config.save_config.assert_called_once()
    
    @patch('dotconfig_hub.cli.Confirm.ask')
    def test_setup_cancel_override(self, mock_confirm, runner, temp_templates_dir, temp_project_dir):
        """Test setup command cancelling override of existing configuration."""
        mock_confirm.return_value = False  # Don't override
        
        # Create mock existing config
        mock_project_config = MagicMock()
        mock_project_config.exists.return_value = True
        mock_project_config.get_templates_source.return_value = Path("/other/templates/dir")
        mock_project_config.config_path = temp_project_dir / "dotconfig-hub.yaml"
        
        with patch('dotconfig_hub.cli.Path.cwd', return_value=temp_project_dir):
            with patch('dotconfig_hub.cli.ProjectConfig', return_value=mock_project_config):
                result = runner.invoke(setup, ['--templates-dir', str(temp_templates_dir)])
        
        assert result.exit_code == 0
        assert "Setup cancelled" in result.output
        mock_confirm.assert_called_once()
        # Should NOT call set_templates_source or save_config when cancelled
        mock_project_config.set_templates_source.assert_not_called()
        mock_project_config.save_config.assert_not_called()