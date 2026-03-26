"""Project configuration management for dotconfig-hub.yaml files."""

import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .utils import to_home_relative_str


class ProjectConfig:
    """Manages project-specific configuration in dotconfig-hub.yaml."""

    CONFIG_FILENAME = "dotconfig-hub.yaml"
    GLOBAL_CONFIG_PATH = Path.home() / CONFIG_FILENAME

    def __init__(self, project_dir: Optional[Path] = None) -> None:
        """Initialize project configuration.

        Args:
            project_dir: Project directory. If None, uses current directory.

        """
        self.project_dir = project_dir or Path.cwd()
        self.config_path = self.project_dir / self.CONFIG_FILENAME
        self.global_config_data = self._load_global_config()
        self.config_data = self._load_config()

    def _load_global_config(self) -> Dict[str, Any]:
        """Load global configuration from ~/dotconfig-hub.yaml."""
        if not self.GLOBAL_CONFIG_PATH.exists():
            return {}

        try:
            with open(self.GLOBAL_CONFIG_PATH, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            # Don't raise error for global config issues, just log and continue
            warnings.warn(f"Error loading global config: {e}", stacklevel=2)
            return {}

    def _load_config(self) -> Dict[str, Any]:
        """Load project configuration from dotconfig-hub.yaml."""
        # Start with default config
        config = self._get_default_config()

        # Apply global config if available
        if self.global_config_data:
            config.update(self.global_config_data)

        # Apply project-specific config (highest priority)
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    project_config = yaml.safe_load(f) or {}
                    config.update(project_config)
            except Exception as e:
                msg = f"Error loading project config: {e}"
                raise ValueError(msg) from e

        return config

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default project configuration."""
        return {
            "templates_source": None,
            "active_environment_sets": [],
        }

    def save_config(self) -> None:
        """Save current configuration to dotconfig-hub.yaml."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(self.config_data, f, default_flow_style=False, sort_keys=False)

    def exists(self) -> bool:
        """Check if project config file exists."""
        return self.config_path.exists()

    def get_templates_source(self) -> Optional[Path]:
        """Get templates source directory."""
        source = self.config_data.get("templates_source")
        if source:
            # Expand user home directory
            expanded = Path(source).expanduser().resolve()
            return expanded if expanded.exists() else None
        return None

    @staticmethod
    def _to_home_relative_str(path: Path) -> str:
        """Convert path to home-relative string if possible (e.g. ~/projects/foo)."""
        return to_home_relative_str(path)

    def set_templates_source(self, templates_dir: Path) -> None:
        """Set templates source directory.

        Args:
            templates_dir: Path to templates directory

        """
        self.config_data["templates_source"] = self._to_home_relative_str(templates_dir)

    def get_active_environment_sets(self) -> List[str]:
        """Get list of active environment sets."""
        return self.config_data.get("active_environment_sets", [])

    def set_active_environment_sets(self, env_sets: List[str]) -> None:
        """Set active environment sets.

        Args:
            env_sets: List of environment set names

        """
        self.config_data["active_environment_sets"] = env_sets

    def add_environment_set(self, env_set: str) -> None:
        """Add an environment set to active list.

        Args:
            env_set: Environment set name to add

        """
        active_sets = set(self.get_active_environment_sets())
        active_sets.add(env_set)
        self.set_active_environment_sets(list(active_sets))

    def get_templates_config_path(self) -> Optional[Path]:
        """Get path to templates config.yaml file.

        Returns:
            Path to templates config.yaml or None if not configured/found

        """
        templates_source = self.get_templates_source()
        if not templates_source:
            return None

        config_path = templates_source / "config.yaml"
        return config_path if config_path.exists() else None

    def validate_setup(self) -> List[str]:
        """Validate project setup and return list of issues.

        Returns:
            List of validation error messages

        """
        issues = []

        # Check if templates source is configured
        if not self.config_data.get("templates_source"):
            issues.append(
                "Templates source not configured. Run 'dotconfig-hub setup' first."
            )
            return issues

        # Check if templates source exists
        templates_source = self.get_templates_source()
        if not templates_source:
            source = self.config_data.get("templates_source")
            issues.append(f"Templates source directory not found: {source}")
            return issues

        # Check if templates config exists
        templates_config = self.get_templates_config_path()
        if not templates_config:
            issues.append(f"Templates config.yaml not found in: {templates_source}")

        # Check if active environment sets are valid (requires templates config)
        if templates_config:
            try:
                with open(templates_config, "r", encoding="utf-8") as f:
                    templates_data = yaml.safe_load(f) or {}

                available_sets = set(templates_data.get("environment_sets", {}).keys())
                active_sets = set(self.get_active_environment_sets())
                invalid_sets = active_sets - available_sets

                if invalid_sets:
                    issues.append(
                        f"Invalid environment sets: {', '.join(invalid_sets)}"
                    )
            except Exception as e:
                issues.append(f"Error reading templates config: {e}")

        return issues

    def get_global_templates_source(self) -> Optional[Path]:
        """Get templates source from global configuration.

        Returns:
            Path to global templates source or None

        """
        source = self.global_config_data.get("templates_source")
        if source:
            expanded = Path(source).expanduser().resolve()
            return expanded if expanded.exists() else None
        return None

    def get_global_environment_sets(self) -> List[str]:
        """Get active environment sets from global configuration.

        Returns:
            List of global environment set names

        """
        return self.global_config_data.get("active_environment_sets") or []

    def save_global_config(
        self,
        templates_source: Optional[Path] = None,
        environment_sets: Optional[List[str]] = None,
    ) -> None:
        """Save global configuration to ~/dotconfig-hub.yaml.

        Args:
            templates_source: Global templates source directory
            environment_sets: Global environment sets

        """
        global_config = self.global_config_data.copy()

        if templates_source is not None:
            global_config["templates_source"] = self._to_home_relative_str(
                templates_source
            )

        if environment_sets is not None:
            global_config["active_environment_sets"] = environment_sets

        # Create directory if it doesn't exist
        self.GLOBAL_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

        with open(self.GLOBAL_CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.dump(global_config, f, default_flow_style=False, sort_keys=False)

        # Reload global config data
        self.global_config_data = self._load_global_config()
