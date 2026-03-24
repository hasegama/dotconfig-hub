"""Configuration management for AI instructions sync tool."""

import glob
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import yaml


class Config:
    """Manages configuration for the AI instructions sync tool."""

    def __init__(self, config_path: Optional[Path] = None) -> None:
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

        with open(self.config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {"environment_sets": {}}

    def _migrate_old_config(self) -> None:
        """Migrate old config format to new environment sets format."""
        if "tools" in self.config_data and "environment_sets" not in self.config_data:
            # Migrate old format to new format
            self.config_data["environment_sets"] = {
                "default": {
                    "description": "Default environment set (migrated)",
                    "tools": self.config_data["tools"],
                }
            }
            del self.config_data["tools"]

    @staticmethod
    def _parse_file_entry(entry: Union[str, Dict[str, Any]]) -> Tuple[str, bool]:
        """Parse a file entry from the YAML config into (pattern, init_only).

        Supports two formats:
          - string: "path/to/file" -> (pattern, False)
          - dict:   {path: "path/to/file", init_only: true} -> (pattern, True)

        Related: Issue #6 - init_only delivery mode
        """
        if isinstance(entry, str):
            return entry, False
        if isinstance(entry, dict):
            return entry["path"], entry.get("init_only", False)
        msg = f"Unexpected file entry type: {type(entry)}"
        raise TypeError(msg)

    def get_init_only_files(
        self, tool_name: str, env_set: Optional[str] = None
    ) -> Set[str]:
        """Get set of file patterns marked as init_only for a tool.

        Args:
            tool_name: Name of the tool
            env_set: Environment set name

        Returns:
            Set of file pattern strings that have init_only: true

        Related: Issue #6 - init_only delivery mode

        """
        tool_config, _ = self.get_tool_config(tool_name, env_set)
        if not tool_config:
            return set()

        files = tool_config.get("files", [])
        init_only_patterns: Set[str] = set()
        for entry in files:
            pattern, is_init_only = self._parse_file_entry(entry)
            if is_init_only:
                init_only_patterns.add(pattern)
        return init_only_patterns

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

    def get_tool_config(
        self, tool_name: str, env_set: Optional[str] = None
    ) -> Tuple[Dict[str, Any], str]:
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

    def get_source_files(
        self, tool_name: str, env_set: Optional[str] = None
    ) -> List[Path]:
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
        for entry in files:
            file_pattern, _ = self._parse_file_entry(entry)
            # Handle glob patterns
            if "*" in file_pattern or "?" in file_pattern:
                pattern_path = project_dir / file_pattern
                matched_files = glob.glob(str(pattern_path), recursive=True)
                source_files.extend(Path(f) for f in matched_files)
            else:
                file_path = project_dir / file_pattern
                if file_path.exists():
                    source_files.append(file_path)

        return source_files

    def get_source_files_relative(
        self, tool_name: str, env_set: Optional[str] = None
    ) -> Dict[str, Path]:
        """Get source files mapped by their relative path from project_dir.

        This enables matching files across different environment sets by comparing
        their relative paths, regardless of the absolute project_dir location.

        Args:
            tool_name: Name of the tool
            env_set: Environment set name

        Returns:
            Dict mapping relative path strings to absolute file paths

        """
        tool_config, _ = self.get_tool_config(tool_name, env_set)
        if not tool_config:
            return {}

        project_dir = self.base_dir / tool_config.get("project_dir", "")
        source_files = self.get_source_files(tool_name, env_set)

        relative_map: Dict[str, Path] = {}
        for abs_path in source_files:
            try:
                rel_path = abs_path.relative_to(project_dir)
                relative_map[str(rel_path)] = abs_path
            except ValueError:
                continue

        return relative_map

    def get_target_files(
        self, tool_name: str, target_dir: Path, env_set: Optional[str] = None
    ) -> List[Path]:
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
        for entry in files:
            file_pattern, _ = self._parse_file_entry(entry)
            # Handle glob patterns
            if "*" in file_pattern or "?" in file_pattern:
                pattern_path = target_dir / file_pattern
                matched_files = glob.glob(str(pattern_path), recursive=True)
                target_files.extend(Path(f) for f in matched_files)
            else:
                file_path = target_dir / file_pattern
                target_files.append(file_path)  # Include even if doesn't exist

        return target_files

    def get_file_mapping(
        self, tool_name: str, target_dir: Path, env_set: Optional[str] = None
    ) -> Dict[Path, Path]:
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
        for entry in files:
            file_pattern, _ = self._parse_file_entry(entry)
            # For non-glob patterns, create direct mapping
            if "*" not in file_pattern and "?" not in file_pattern:
                source = project_dir / file_pattern
                target = target_dir / file_pattern
                # Include in mapping only if at least one side is a file
                # (skip directories to avoid IsADirectoryError during sync)
                if source.is_file() or target.is_file():
                    mapping[source] = target
            else:
                # For glob patterns, match files from both source and target
                source_pattern = project_dir / file_pattern
                target_pattern = target_dir / file_pattern

                # Get files from both sides
                source_files = glob.glob(str(source_pattern), recursive=True)
                target_files = glob.glob(str(target_pattern), recursive=True)

                # Process source files (skip directories)
                for source_file in source_files:
                    source_path = Path(source_file)
                    if not source_path.is_file():
                        continue
                    try:
                        relative_path = source_path.relative_to(project_dir)
                        target_path = target_dir / relative_path
                        mapping[source_path] = target_path
                    except ValueError:
                        continue

                # Process target files that don't have corresponding source files
                # (skip directories)
                for target_file in target_files:
                    target_path = Path(target_file)
                    if not target_path.is_file():
                        continue
                    try:
                        relative_path = target_path.relative_to(target_dir)
                        source_path = project_dir / relative_path
                        # Only add if not already in mapping
                        if source_path not in mapping:
                            mapping[source_path] = target_path
                    except ValueError:
                        continue

        return mapping
