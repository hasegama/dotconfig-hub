"""Project configuration management for dotconfig-hub.yaml files."""

import os
from pathlib import Path
from typing import Dict, List, Any, Optional
import yaml


class ProjectConfig:
    """Manages project-specific configuration in dotconfig-hub.yaml."""
    
    CONFIG_FILENAME = "dotconfig-hub.yaml"
    
    def __init__(self, project_dir: Optional[Path] = None):
        """Initialize project configuration.
        
        Args:
            project_dir: Project directory. If None, uses current directory.
        """
        self.project_dir = project_dir or Path.cwd()
        self.config_path = self.project_dir / self.CONFIG_FILENAME
        self.config_data = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load project configuration from dotconfig-hub.yaml."""
        if not self.config_path.exists():
            return self._get_default_config()
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
                return {**self._get_default_config(), **config}
        except Exception as e:
            raise ValueError(f"Error loading project config: {e}")
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default project configuration."""
        return {
            "templates_source": None,
            "active_environment_sets": [],
            "sync_preferences": {
                "auto_sync": False,
                "create_backups": True,
                "dry_run_default": False
            }
        }
    
    def save_config(self):
        """Save current configuration to dotconfig-hub.yaml."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.config_path, 'w', encoding='utf-8') as f:
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
    
    def set_templates_source(self, templates_dir: Path):
        """Set templates source directory.
        
        Args:
            templates_dir: Path to templates directory
        """
        # Store as relative to home directory if possible for portability
        try:
            home = Path.home()
            if templates_dir.is_relative_to(home):
                relative_path = "~" / templates_dir.relative_to(home)
                self.config_data["templates_source"] = str(relative_path)
            else:
                self.config_data["templates_source"] = str(templates_dir)
        except (ValueError, OSError):
            self.config_data["templates_source"] = str(templates_dir)
    
    def get_active_environment_sets(self) -> List[str]:
        """Get list of active environment sets."""
        return self.config_data.get("active_environment_sets", [])
    
    def set_active_environment_sets(self, env_sets: List[str]):
        """Set active environment sets.
        
        Args:
            env_sets: List of environment set names
        """
        self.config_data["active_environment_sets"] = env_sets
    
    def add_environment_set(self, env_set: str):
        """Add an environment set to active list.
        
        Args:
            env_set: Environment set name to add
        """
        active_sets = set(self.get_active_environment_sets())
        active_sets.add(env_set)
        self.set_active_environment_sets(list(active_sets))
    
    def remove_environment_set(self, env_set: str):
        """Remove an environment set from active list.
        
        Args:
            env_set: Environment set name to remove
        """
        active_sets = set(self.get_active_environment_sets())
        active_sets.discard(env_set)
        self.set_active_environment_sets(list(active_sets))
    
    def get_sync_preference(self, key: str, default: Any = None) -> Any:
        """Get a sync preference value.
        
        Args:
            key: Preference key
            default: Default value if key not found
            
        Returns:
            Preference value
        """
        return self.config_data.get("sync_preferences", {}).get(key, default)
    
    def set_sync_preference(self, key: str, value: Any):
        """Set a sync preference value.
        
        Args:
            key: Preference key
            value: Preference value
        """
        if "sync_preferences" not in self.config_data:
            self.config_data["sync_preferences"] = {}
        self.config_data["sync_preferences"][key] = value
    
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
            issues.append("Templates source not configured. Run 'dotconfig-hub setup' first.")
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
                with open(templates_config, 'r', encoding='utf-8') as f:
                    templates_data = yaml.safe_load(f) or {}
                
                available_sets = set(templates_data.get("environment_sets", {}).keys())
                active_sets = set(self.get_active_environment_sets())
                invalid_sets = active_sets - available_sets
                
                if invalid_sets:
                    issues.append(f"Invalid environment sets: {', '.join(invalid_sets)}")
            except Exception as e:
                issues.append(f"Error reading templates config: {e}")
        
        return issues