"""Configuration management for AI instructions sync tool."""

import os
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import yaml
import glob


class Config:
    """Manages configuration for the AI instructions sync tool."""
    
    def __init__(self, config_path: Optional[Path] = None):
        """Initialize configuration.
        
        Args:
            config_path: Path to config.yaml file. If None, searches for it.
        """
        self.config_path = config_path or self._find_config_file()
        self.config_data = self._load_config()
        self.base_dir = self.config_path.parent if self.config_path else Path.cwd()
        self._migrate_old_config()
    
    def _find_config_file(self) -> Optional[Path]:
        """Search for config.yaml in current and parent directories."""
        current = Path.cwd()
        
        # Search up to 5 levels up
        for _ in range(5):
            config_file = current / "config.yaml"
            if config_file.exists():
                return config_file
            
            # Check if we've reached the root
            if current.parent == current:
                break
            current = current.parent
        
        return None
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        if not self.config_path or not self.config_path.exists():
            return {"environment_sets": {}}
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {"environment_sets": {}}
    
    def _migrate_old_config(self):
        """Migrate old config format to new environment sets format."""
        if "tools" in self.config_data and "environment_sets" not in self.config_data:
            # Migrate old format to new format
            self.config_data["environment_sets"] = {
                "default": {
                    "description": "Default environment set (migrated)",
                    "tools": self.config_data["tools"]
                }
            }
            del self.config_data["tools"]
    
    def get_environment_sets(self) -> List[str]:
        """Get list of configured environment sets."""
        return list(self.config_data.get("environment_sets", {}).keys())
    
    def get_environment_set(self, set_name: str) -> Dict[str, Any]:
        """Get configuration for a specific environment set."""
        return self.config_data.get("environment_sets", {}).get(set_name, {})
    
    def get_tools(self, env_set: Optional[str] = None) -> List[str]:
        """Get list of configured tools.
        
        Args:
            env_set: Environment set name. If None, returns tools from all sets.
            
        Returns:
            List of tool names
        """
        if env_set:
            env_config = self.get_environment_set(env_set)
            return list(env_config.get("tools", {}).keys())
        else:
            # Return all tools from all environment sets
            all_tools = []
            for set_name in self.get_environment_sets():
                env_config = self.get_environment_set(set_name)
                all_tools.extend(env_config.get("tools", {}).keys())
            return list(set(all_tools))  # Remove duplicates
    
    def get_tool_config(self, tool_name: str, env_set: Optional[str] = None) -> Tuple[Dict[str, Any], str]:
        """Get configuration for a specific tool.
        
        Args:
            tool_name: Name of the tool (e.g., 'claude', 'github_copilot')
            env_set: Environment set name. If None, searches all sets.
            
        Returns:
            Tuple of (tool config dict, environment set name)
        """
        if env_set:
            env_config = self.get_environment_set(env_set)
            tool_config = env_config.get("tools", {}).get(tool_name, {})
            if tool_config:
                return tool_config, env_set
        else:
            # Search all environment sets for the tool
            for set_name in self.get_environment_sets():
                env_config = self.get_environment_set(set_name)
                tool_config = env_config.get("tools", {}).get(tool_name, {})
                if tool_config:
                    return tool_config, set_name
        
        return {}, ""
    
    def get_source_files(self, tool_name: str, env_set: Optional[str] = None) -> List[Path]:
        """Get list of source files for a tool from the central repository.
        
        Args:
            tool_name: Name of the tool
            env_set: Environment set name
            
        Returns:
            List of absolute paths to source files
        """
        tool_config, _ = self.get_tool_config(tool_name, env_set)
        if not tool_config:
            return []
        
        project_dir = self.base_dir / tool_config.get("project_dir", "")
        files = tool_config.get("files", [])
        
        source_files = []
        for file_pattern in files:
            # Handle glob patterns
            if '*' in file_pattern or '?' in file_pattern:
                pattern_path = project_dir / file_pattern
                matched_files = glob.glob(str(pattern_path), recursive=True)
                source_files.extend(Path(f) for f in matched_files)
            else:
                file_path = project_dir / file_pattern
                if file_path.exists():
                    source_files.append(file_path)
        
        return source_files
    
    def get_target_files(self, tool_name: str, target_dir: Path, env_set: Optional[str] = None) -> List[Path]:
        """Get list of target files for a tool in the target directory.
        
        Args:
            tool_name: Name of the tool
            target_dir: Target directory (project directory)
            env_set: Environment set name
            
        Returns:
            List of absolute paths to target files
        """
        tool_config, _ = self.get_tool_config(tool_name, env_set)
        if not tool_config:
            return []
        
        files = tool_config.get("files", [])
        
        target_files = []
        for file_pattern in files:
            # Handle glob patterns
            if '*' in file_pattern or '?' in file_pattern:
                pattern_path = target_dir / file_pattern
                matched_files = glob.glob(str(pattern_path), recursive=True)
                target_files.extend(Path(f) for f in matched_files)
            else:
                file_path = target_dir / file_pattern
                target_files.append(file_path)  # Include even if doesn't exist
        
        return target_files
    
    def get_file_mapping(self, tool_name: str, target_dir: Path, env_set: Optional[str] = None) -> Dict[Path, Path]:
        """Get mapping of source files to target files.
        
        Args:
            tool_name: Name of the tool
            target_dir: Target directory
            env_set: Environment set name
            
        Returns:
            Dictionary mapping source paths to target paths
        """
        tool_config, _ = self.get_tool_config(tool_name, env_set)
        if not tool_config:
            return {}
        
        project_dir = self.base_dir / tool_config.get("project_dir", "")
        files = tool_config.get("files", [])
        
        mapping = {}
        for file_pattern in files:
            # For non-glob patterns, create direct mapping
            if '*' not in file_pattern and '?' not in file_pattern:
                source = project_dir / file_pattern
                target = target_dir / file_pattern
                # Include in mapping if file exists in either location
                if source.exists() or target.exists():
                    mapping[source] = target
            else:
                # For glob patterns, match files and create relative mappings
                source_pattern = project_dir / file_pattern
                source_files = glob.glob(str(source_pattern), recursive=True)
                
                for source_file in source_files:
                    source_path = Path(source_file)
                    # Calculate relative path from project_dir
                    try:
                        relative_path = source_path.relative_to(project_dir)
                        target_path = target_dir / relative_path
                        mapping[source_path] = target_path
                    except ValueError:
                        # Skip if not relative to project_dir
                        continue
        
        return mapping