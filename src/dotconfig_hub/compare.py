"""Environment set comparison and merge functionality.

Provides the ability to compare files across different environment sets
and selectively merge changes bidirectionally. This operates entirely
within the hub (template repository), without requiring a project setup.

Related: GitHub Issue #7
"""

import shutil
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from .config import Config
from .diff import DiffViewer


@dataclass
class FilePair:
    """Represents a pair of files from two environment sets for comparison.

    Attributes:
        relative_path: The common relative path shared by both files
        path_a: Absolute path in environment set A (None if only in B)
        path_b: Absolute path in environment set B (None if only in A)

    """

    relative_path: str
    path_a: Optional[Path]
    path_b: Optional[Path]


class EnvSetComparer:
    """Handles comparison and merge of files across environment sets.

    Parallel to FileSyncer in sync.py, but operates on two environment sets
    within the hub rather than between hub and project.
    """

    def __init__(self, config: Config, console: Console) -> None:
        """Initialize the comparer.

        Args:
            config: Hub configuration instance
            console: Rich console for output

        """
        self.config = config
        self.console = console
        self.diff_viewer = DiffViewer()

    def find_file_pairs(
        self,
        set_a: str,
        set_b: str,
        tool: Optional[str] = None,
        file_pattern: Optional[str] = None,
    ) -> List[FilePair]:
        """Find file pairs across two environment sets by matching relative paths.

        For each common tool between the two sets, collects files from both sides
        as relative paths. Files with the same relative path are paired for comparison.
        Files existing in only one set are also included.

        Args:
            set_a: Name of the first environment set
            set_b: Name of the second environment set
            tool: Optional tool name filter
            file_pattern: Optional file pattern filter (supports wildcards via fnmatch)

        Returns:
            List of FilePair objects representing matched files

        """
        tools_a = set(self.config.get_tools(set_a))
        tools_b = set(self.config.get_tools(set_b))

        # Find common tools, or filter to specific tool
        if tool:
            if tool not in tools_a:
                msg = f"Tool '{tool}' not found in environment set '{set_a}'"
                raise ValueError(msg)
            if tool not in tools_b:
                msg = f"Tool '{tool}' not found in environment set '{set_b}'"
                raise ValueError(msg)
            common_tools = [tool]
        else:
            common_tools = sorted(tools_a & tools_b)

        pairs: List[FilePair] = []

        for tool_name in common_tools:
            files_a = self.config.get_source_files_relative(tool_name, set_a)
            files_b = self.config.get_source_files_relative(tool_name, set_b)

            all_rel_paths = sorted(set(files_a.keys()) | set(files_b.keys()))

            for rel_path in all_rel_paths:
                # Apply file pattern filter if specified
                if file_pattern and not fnmatch(rel_path, file_pattern):
                    continue

                pairs.append(
                    FilePair(
                        relative_path=rel_path,
                        path_a=files_a.get(rel_path),
                        path_b=files_b.get(rel_path),
                    )
                )

        return pairs

    def compare(
        self,
        set_a: str,
        set_b: str,
        tool: Optional[str] = None,
        file_pattern: Optional[str] = None,
    ) -> int:
        """Compare files between two environment sets and display diffs.

        Args:
            set_a: Name of the first environment set
            set_b: Name of the second environment set
            tool: Optional tool name filter
            file_pattern: Optional file pattern filter (supports wildcards)

        Returns:
            Number of files with differences

        """
        pairs = self.find_file_pairs(set_a, set_b, tool, file_pattern)

        if not pairs:
            self.console.print("[yellow]No common files found to compare[/yellow]")
            return 0

        diff_count = 0
        summary_rows: List[tuple] = []

        for pair in pairs:
            if pair.path_a is None:
                summary_rows.append((pair.relative_path, f"Only in {set_b}"))
                diff_count += 1
            elif pair.path_b is None:
                summary_rows.append((pair.relative_path, f"Only in {set_a}"))
                diff_count += 1
            elif self.diff_viewer.compare_files(pair.path_a, pair.path_b):
                summary_rows.append((pair.relative_path, "Different"))
                diff_count += 1
                self._display_pair_diff(pair, set_a, set_b)
            else:
                summary_rows.append((pair.relative_path, "Identical"))

        # Display summary table
        self._display_summary(set_a, set_b, summary_rows)

        return diff_count

    def merge(
        self,
        set_a: str,
        set_b: str,
        tool: Optional[str] = None,
        file_pattern: Optional[str] = None,
        dry_run: bool = False,
    ) -> int:
        """Interactively merge files between two environment sets.

        For each differing file, prompts the user to choose a merge direction:
        A -> B, B -> A, or Skip.

        Args:
            set_a: Name of the first environment set
            set_b: Name of the second environment set
            tool: Optional tool name filter
            file_pattern: Optional file pattern filter (supports wildcards)
            dry_run: If True, preview merge without writing files

        Returns:
            Number of files merged

        """
        pairs = self.find_file_pairs(set_a, set_b, tool, file_pattern)

        if not pairs:
            self.console.print("[yellow]No common files found to merge[/yellow]")
            return 0

        merged_count = 0

        for pair in pairs:
            has_diff = False

            if pair.path_a is None:
                self.console.print(
                    f"\n[bold]{pair.relative_path}[/bold]: Only in [cyan]{set_b}[/cyan]"
                )
                has_diff = True
            elif pair.path_b is None:
                self.console.print(
                    f"\n[bold]{pair.relative_path}[/bold]: Only in [cyan]{set_a}[/cyan]"
                )
                has_diff = True
            elif self.diff_viewer.compare_files(pair.path_a, pair.path_b):
                has_diff = True
                self._display_pair_diff(pair, set_a, set_b)

            if not has_diff:
                continue

            # Prompt user for merge direction
            merged = self._prompt_merge_direction(pair, set_a, set_b, dry_run)
            if merged:
                merged_count += 1

        if dry_run and merged_count > 0:
            self.console.print(
                f"\n[yellow]DRY RUN: {merged_count} file(s) would be merged[/yellow]"
            )
        elif merged_count > 0:
            self.console.print(f"\n[green]Merged {merged_count} file(s)[/green]")
        else:
            self.console.print("\n[dim]No files were merged[/dim]")

        return merged_count

    def _display_pair_diff(self, pair: FilePair, set_a: str, set_b: str) -> None:
        """Display diff between a file pair with environment set labels.

        Args:
            pair: The file pair to display
            set_a: Name of environment set A (used as label)
            set_b: Name of environment set B (used as label)

        """
        self.console.print(f"\n[bold blue]--- {pair.relative_path} ---[/bold blue]")
        self.console.print(f"  [green]{set_a}[/green]: {pair.path_a}")
        self.console.print(f"  [yellow]{set_b}[/yellow]: {pair.path_b}")

        if pair.path_a and pair.path_b:
            # Reuse DiffViewer's unified diff display
            diff_lines = self.diff_viewer.get_diff_lines(pair.path_a, pair.path_b)
            if diff_lines:
                from rich.panel import Panel
                from rich.syntax import Syntax

                diff_text = "\n".join(diff_lines)
                syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=True)
                self.console.print(
                    Panel(syntax, title="Differences", border_style="blue")
                )

    def _prompt_merge_direction(
        self,
        pair: FilePair,
        set_a: str,
        set_b: str,
        dry_run: bool,
    ) -> bool:
        """Prompt user for merge direction and execute the copy.

        Args:
            pair: The file pair to merge
            set_a: Name of environment set A
            set_b: Name of environment set B
            dry_run: If True, only preview without writing

        Returns:
            True if a merge action was selected (not skipped)

        """
        # Build available choices based on which files exist
        choices = []
        choice_labels = []

        if pair.path_a is not None:
            choices.append("a2b")
            choice_labels.append(f"[green]{set_a}[/green] -> [yellow]{set_b}[/yellow]")

        if pair.path_b is not None:
            choices.append("b2a")
            choice_labels.append(f"[yellow]{set_b}[/yellow] -> [green]{set_a}[/green]")

        choices.append("skip")
        choice_labels.append("Skip")

        # Display choices
        self.console.print("\n  Merge options:")
        for i, label in enumerate(choice_labels):
            self.console.print(f"    {i + 1}. {label}")

        choice = Prompt.ask(
            "  Select",
            choices=[str(i + 1) for i in range(len(choices))],
            default=str(len(choices)),
        )

        selected = choices[int(choice) - 1]

        if selected == "skip":
            return False

        if selected == "a2b":
            self._copy_file(pair.path_a, pair.path_b, pair, set_a, set_b, dry_run)
        elif selected == "b2a":
            self._copy_file(pair.path_b, pair.path_a, pair, set_b, set_a, dry_run)

        return True

    def _copy_file(
        self,
        source: Path,
        target: Optional[Path],
        pair: FilePair,
        source_set: str,
        target_set: str,
        dry_run: bool,
    ) -> None:
        """Copy a file from one environment set to another.

        If the target path is None (file only exists in one set), determines the
        target path from the target set's tool config.

        Args:
            source: Source file path
            target: Target file path (may be None for files only in one set)
            pair: The file pair being merged
            source_set: Name of the source environment set
            target_set: Name of the target environment set
            dry_run: If True, only preview without writing

        """
        if target is None:
            # Determine target path from the target set's project_dir
            target = self._resolve_target_path(pair.relative_path, target_set)

        if dry_run:
            self.console.print(f"  [yellow]Would copy:[/yellow] {source} -> {target}")
            return

        # Ensure target directory exists
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        self.console.print(
            f"  [green]Copied:[/green] {source.name} ({source_set} -> {target_set})"
        )

    def _resolve_target_path(self, relative_path: str, target_set: str) -> Path:
        """Resolve an absolute target path for a file in a given environment set.

        Finds the first tool in the target set whose files could contain the
        given relative path and constructs the absolute path from its project_dir.

        Args:
            relative_path: Relative file path to resolve
            target_set: Environment set to resolve the path in

        Returns:
            Absolute path in the target set's project_dir

        """
        for tool_name in self.config.get_tools(target_set):
            tool_config, _ = self.config.get_tool_config(tool_name, target_set)
            if tool_config:
                project_dir = self.config.base_dir / tool_config.get("project_dir", "")
                return project_dir / relative_path

        # Fallback: should not normally reach here
        msg = (
            f"Could not resolve target path for '{relative_path}' "
            f"in environment set '{target_set}'"
        )
        raise ValueError(msg)

    def _display_summary(
        self,
        set_a: str,
        set_b: str,
        rows: List[tuple],
    ) -> None:
        """Display a summary table of comparison results.

        Args:
            set_a: Name of environment set A
            set_b: Name of environment set B
            rows: List of (relative_path, status) tuples

        """
        table = Table(title=f"\nComparison: {set_a} vs {set_b}")
        table.add_column("File", style="cyan")
        table.add_column("Status")

        for file_path, status in rows:
            if status == "Identical":
                styled_status = "[green]Identical[/green]"
            elif status == "Different":
                styled_status = "[red]Different[/red]"
            else:
                styled_status = f"[yellow]{status}[/yellow]"
            table.add_row(file_path, styled_status)

        self.console.print(table)
