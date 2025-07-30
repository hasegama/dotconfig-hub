"""Tests for project mapping functionality."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from dotconfig_hub.project_mapping import ProjectMapping


@pytest.fixture()
def temp_templates_dir():
    """Create a temporary templates directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


def test_project_mapping_initialization(temp_templates_dir):
    """Test ProjectMapping initialization."""
    mapping = ProjectMapping(temp_templates_dir)

    assert mapping.templates_dir == temp_templates_dir
    assert mapping.mapping_path == temp_templates_dir / "project_mapping.yaml"
    assert mapping.mapping_data == {"projects": {}}


def test_add_and_get_project(temp_templates_dir):
    """Test adding and retrieving projects."""
    mapping = ProjectMapping(temp_templates_dir)

    # Add a project
    project_path = Path("/home/user/my-project")
    env_sets = ["my_project_init_template", "python_dev"]
    mapping.add_project(project_path, env_sets)

    # Get project info
    info = mapping.get_project_info(project_path)
    assert info is not None
    assert info["environment_sets"] == env_sets
    assert "last_synced" in info

    # Test normalization - should find the same project
    absolute_path = project_path.resolve()
    info2 = mapping.get_project_info(absolute_path)
    assert info2 == info


def test_remove_project(temp_templates_dir):
    """Test removing a project."""
    mapping = ProjectMapping(temp_templates_dir)

    # Add and then remove a project
    project_path = Path("/home/user/my-project")
    mapping.add_project(project_path, ["test_env"])

    assert mapping.get_project_info(project_path) is not None

    mapping.remove_project(project_path)
    assert mapping.get_project_info(project_path) is None


def test_get_projects_by_environment_set(temp_templates_dir):
    """Test getting projects by environment set."""
    mapping = ProjectMapping(temp_templates_dir)

    # Add multiple projects
    mapping.add_project(Path("/project1"), ["env_a", "env_b"])
    mapping.add_project(Path("/project2"), ["env_b", "env_c"])
    mapping.add_project(Path("/project3"), ["env_a"])

    # Get projects using env_b
    projects = mapping.get_projects_by_environment_set("env_b")
    assert len(projects) == 2

    paths = [p["path"] for p in projects]
    assert "/project1" in paths
    assert "/project2" in paths

    # Get projects using env_c
    projects = mapping.get_projects_by_environment_set("env_c")
    assert len(projects) == 1
    assert projects[0]["path"] == "/project2"

    # Get projects using non-existent env
    projects = mapping.get_projects_by_environment_set("env_d")
    assert len(projects) == 0


def test_get_environment_set_usage(temp_templates_dir):
    """Test getting environment set usage statistics."""
    mapping = ProjectMapping(temp_templates_dir)

    # Add projects
    mapping.add_project(Path("/project1"), ["env_a", "env_b"])
    mapping.add_project(Path("/project2"), ["env_b", "env_c"])
    mapping.add_project(Path("/project3"), ["env_a"])

    usage = mapping.get_environment_set_usage()

    assert usage["env_a"] == 2
    assert usage["env_b"] == 2
    assert usage["env_c"] == 1


def test_update_last_synced(temp_templates_dir):
    """Test updating last_synced timestamp."""
    mapping = ProjectMapping(temp_templates_dir)

    project_path = Path("/my-project")
    mapping.add_project(project_path, ["test_env"])

    # Get initial timestamp
    info1 = mapping.get_project_info(project_path)
    timestamp1 = info1["last_synced"]

    # Update timestamp
    import time

    time.sleep(0.1)  # Small delay to ensure different timestamp
    mapping.update_last_synced(project_path)

    # Check updated timestamp
    info2 = mapping.get_project_info(project_path)
    timestamp2 = info2["last_synced"]

    assert timestamp2 > timestamp1


def test_save_and_load_mapping(temp_templates_dir):
    """Test saving and loading project mapping."""
    mapping1 = ProjectMapping(temp_templates_dir)

    # Add some projects
    mapping1.add_project(Path("/project1"), ["env_a"])
    mapping1.add_project(Path("/project2"), ["env_b", "env_c"])

    # Save mapping
    mapping1.save_mapping()

    # Load in new instance
    mapping2 = ProjectMapping(temp_templates_dir)

    # Verify data is loaded correctly
    assert len(mapping2.get_all_projects()) == 2
    assert mapping2.get_project_info(Path("/project1")) is not None
    assert mapping2.get_project_info(Path("/project2")) is not None


def test_cleanup_missing_projects(temp_templates_dir):
    """Test cleaning up projects that no longer exist."""
    mapping = ProjectMapping(temp_templates_dir)

    # Add mix of existing and non-existing projects
    with tempfile.TemporaryDirectory() as existing_dir:
        existing_path = Path(existing_dir)
        mapping.add_project(existing_path, ["env_a"])
        mapping.add_project(Path("/non/existing/path1"), ["env_b"])
        mapping.add_project(Path("/non/existing/path2"), ["env_c"])

    # Cleanup
    removed = mapping.cleanup_missing_projects()

    # Should remove non-existing paths
    assert len(removed) >= 2  # At least the two non-existing paths
    assert "/non/existing/path1" in str(removed)
    assert "/non/existing/path2" in str(removed)


def test_find_projects_needing_sync(temp_templates_dir):
    """Test finding projects that need synchronization."""
    mapping = ProjectMapping(temp_templates_dir)

    # Add projects with different timestamps
    now = datetime.now()
    old_time = (now - timedelta(hours=48)).isoformat()
    recent_time = (now - timedelta(hours=12)).isoformat()

    # Manually set timestamps
    mapping.mapping_data["projects"] = {
        "/old-project": {"environment_sets": ["env_a"], "last_synced": old_time},
        "/recent-project": {"environment_sets": ["env_b"], "last_synced": recent_time},
        "/no-timestamp-project": {
            "environment_sets": ["env_c"]
            # No last_synced field
        },
    }

    # Find projects older than 24 hours
    old_projects = mapping.find_projects_needing_sync(hours=24)

    paths = [p["path"] for p in old_projects]
    assert "/old-project" in paths
    assert "/no-timestamp-project" in paths
    assert "/recent-project" not in paths


def test_path_normalization_with_home_directory(temp_templates_dir):
    """Test that paths are normalized correctly with home directory."""
    mapping = ProjectMapping(temp_templates_dir)

    # Add project with absolute path in home directory
    home = Path.home()
    project_path = home / "test-project"
    mapping.add_project(project_path, ["test_env"])

    # Check that path is stored with ~ notation
    all_projects = mapping.get_all_projects()
    stored_paths = list(all_projects.keys())

    assert len(stored_paths) == 1
    assert stored_paths[0].startswith("~/")
