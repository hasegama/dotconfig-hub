"""Shared utility functions for dotconfig-hub."""

from pathlib import Path


def to_home_relative_str(path: Path) -> str:
    """Convert an absolute path to a ~/relative string when possible.

    If the given path lives under the user's home directory, returns a
    tilde-prefixed string (e.g. "~/projects/foo").  Otherwise returns
    the path as-is in string form.

    Used by ProjectConfig and ProjectMapping to store portable paths.
    """
    abs_path = path.resolve()
    try:
        home = Path.home()
        if abs_path.is_relative_to(home):
            return "~/" + str(abs_path.relative_to(home))
    except (ValueError, OSError):
        pass
    return str(abs_path)
