"""Project mapping management for tracking which projects use which environment sets."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .utils import to_home_relative_str

logger = logging.getLogger(__name__)


class ProjectMapping:
    """Manages the reverse mapping of projects to environment sets."""

    MAPPING_FILENAME = "project_mapping.yaml"

    def __init__(self, templates_dir: Path) -> None:
        """Initialize project mapping.

        Args:
        ----
            templates_dir: Path to templates directory containing config.yaml

        """
        self.templates_dir = templates_dir
        self.mapping_path = self.templates_dir / self.MAPPING_FILENAME
        self.mapping_data = self._load_mapping()

    def _load_mapping(self) -> Dict[str, Any]:
        """Load project mapping from YAML file."""
        if not self.mapping_path.exists():
            return {"projects": {}}

        try:
            with open(self.mapping_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                # Ensure projects key exists
                if "projects" not in data:
                    data["projects"] = {}
                return data
        except yaml.YAMLError as e:
            logger.warning("Error loading project mapping: %s", e)
            return {"projects": {}}

    def save_mapping(self) -> None:
        """Save current mapping to project_mapping.yaml."""
        self.mapping_path.parent.mkdir(parents=True, exist_ok=True)

        # Sort projects by path for consistent output
        sorted_projects = dict(sorted(self.mapping_data["projects"].items()))
        self.mapping_data["projects"] = sorted_projects

        with open(self.mapping_path, "w", encoding="utf-8") as f:
            yaml.dump(self.mapping_data, f, default_flow_style=False, sort_keys=False)

    def _normalize_project_path(self, project_path: Path) -> str:
        """Normalize project path for consistent storage.

        Args:
        ----
            project_path: Project directory path

        Returns:
        -------
            Normalized path string

        """
        return to_home_relative_str(project_path)

    def add_project(self, project_path: Path, environment_sets: List[str]) -> None:
        """Add or update a project's environment set mapping.

        Args:
        ----
            project_path: Path to the project directory
            environment_sets: List of environment set names used by the project

        """
        normalized_path = self._normalize_project_path(project_path)

        self.mapping_data["projects"][normalized_path] = {
            "environment_sets": environment_sets,
            "last_synced": datetime.now().isoformat(),
        }

    def remove_project(self, project_path: Path) -> None:
        """Remove a project from the mapping.

        Args:
        ----
            project_path: Path to the project directory

        """
        normalized_path = self._normalize_project_path(project_path)

        if normalized_path in self.mapping_data["projects"]:
            del self.mapping_data["projects"][normalized_path]

    def get_project_info(self, project_path: Path) -> Optional[Dict[str, Any]]:
        """Get information about a specific project.

        Args:
        ----
            project_path: Path to the project directory

        Returns:
        -------
            Project info dict or None if not found

        """
        normalized_path = self._normalize_project_path(project_path)
        return self.mapping_data["projects"].get(normalized_path)

    def get_projects_by_environment_set(self, env_set: str) -> List[Dict[str, Any]]:
        """Get all projects using a specific environment set.

        Args:
        ----
            env_set: Environment set name

        Returns:
        -------
            List of project info dicts with 'path' key added

        """
        projects = []

        for project_path, info in self.mapping_data["projects"].items():
            if env_set in info.get("environment_sets", []):
                project_info = info.copy()
                project_info["path"] = project_path
                projects.append(project_info)

        return projects

    def get_all_projects(self) -> Dict[str, Dict[str, Any]]:
        """Get all tracked projects.

        Returns
        -------
            Dictionary mapping project paths to their info

        """
        return self.mapping_data["projects"].copy()

    def get_environment_set_usage(self) -> Dict[str, int]:
        """Get usage count for each environment set.

        Returns
        -------
            Dictionary mapping environment set names to usage counts

        """
        usage: Dict[str, int] = {}

        for info in self.mapping_data["projects"].values():
            for env_set in info.get("environment_sets", []):
                usage[env_set] = usage.get(env_set, 0) + 1

        return usage

    def update_last_synced(self, project_path: Path) -> None:
        """Update the last_synced timestamp for a project.

        Args:
        ----
            project_path: Path to the project directory

        """
        normalized_path = self._normalize_project_path(project_path)

        if normalized_path in self.mapping_data["projects"]:
            self.mapping_data["projects"][normalized_path][
                "last_synced"
            ] = datetime.now().isoformat()

    def cleanup_missing_projects(self) -> List[str]:
        """Remove projects that no longer exist from the mapping.

        Returns
        -------
            List of removed project paths

        """
        removed = []

        for project_path in list(self.mapping_data["projects"].keys()):
            # Expand ~ to home directory
            expanded_path = Path(project_path).expanduser()

            if not expanded_path.exists():
                del self.mapping_data["projects"][project_path]
                removed.append(project_path)

        return removed

    def find_projects_needing_sync(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Find projects that haven't been synced recently.

        Args:
        ----
            hours: Number of hours to consider as "recent"

        Returns:
        -------
            List of project info dicts with 'path' key added

        """
        cutoff = datetime.now().timestamp() - (hours * 3600)
        old_projects: List[Dict[str, Any]] = []

        for project_path, info in self.mapping_data["projects"].items():
            last_synced_str = info.get("last_synced")

            # Treat missing or unparseable timestamps as "needs sync"
            needs_sync = True
            if last_synced_str:
                try:
                    last_synced = datetime.fromisoformat(last_synced_str)
                    needs_sync = last_synced.timestamp() < cutoff
                except (ValueError, TypeError):
                    pass

            if needs_sync:
                project_info = info.copy()
                project_info["path"] = project_path
                old_projects.append(project_info)

        return old_projects
