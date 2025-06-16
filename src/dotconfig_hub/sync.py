"""Synchronization logic for AI instruction files."""

import shutil
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from datetime import datetime
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn

from .config import Config
from .diff import DiffViewer


class SyncDirection:
    """Sync direction constants."""
    TO_LOCAL = "local"      # Update local files from central
    TO_REMOTE = "remote"    # Update central files from local
    SKIP = "skip"           # Skip this file


class FileSyncer:
    """Handles file synchronization between central repo and projects."""
    
    def __init__(self, config: Config):
        """Initialize the file syncer.
        
        Args:
            config: Configuration instance
        """
        self.config = config
        self.console = Console()
        self.diff_viewer = DiffViewer()
    
    def sync_tool(self, tool_name: str, target_dir: Path, 
                  auto_sync: Optional[str] = None, dry_run: bool = False,
                  env_set: Optional[str] = None) -> int:
        """Sync files for a specific tool.
        
        Args:
            tool_name: Name of the tool to sync
            target_dir: Target directory (project directory)
            auto_sync: Automatic sync direction ('local' or 'remote')
            dry_run: If True, don't actually sync files
            env_set: Environment set name
            
        Returns:
            Number of files synced
        """
        # Get file mappings
        file_mapping = self.config.get_file_mapping(tool_name, target_dir, env_set)
        
        if not file_mapping:
            self.console.print(f"[yellow]No files configured for tool: {tool_name}[/yellow]")
            if env_set:
                self.console.print(f"[dim]Environment set: {env_set}[/dim]")
            return 0
        
        # Find differences
        differences = self._find_differences(file_mapping)
        
        if not differences:
            self.console.print(f"[green]All files for {tool_name} are in sync[/green]")
            return 0
        
        # Display summary
        self.diff_viewer.display_summary(differences)
        
        # Sync files
        synced_count = 0
        for source, target, has_diff in differences:
            if has_diff:
                if self._sync_file(source, target, auto_sync, dry_run):
                    synced_count += 1
        
        return synced_count
    
    def sync_file(self, file_name: str, target_dir: Path, 
                  auto_sync: Optional[str] = None, dry_run: bool = False,
                  env_set: Optional[str] = None) -> int:
        """Sync a specific file by name.
        
        Args:
            file_name: Name of the file to sync (e.g., '.gitignore')
            target_dir: Target directory (project directory)
            auto_sync: Automatic sync direction ('local' or 'remote')
            dry_run: If True, don't actually sync files
            env_set: Environment set name
            
        Returns:
            Number of files synced (0 or 1)
        """
        # Get all file mappings across all tools
        all_mappings = {}
        
        if env_set:
            env_sets = [env_set]
        else:
            env_sets = self.config.get_environment_sets()
        
        for set_name in env_sets:
            tools = self.config.get_tools(set_name)
            for tool_name in tools:
                tool_mapping = self.config.get_file_mapping(tool_name, target_dir, set_name)
                all_mappings.update(tool_mapping)
        
        # Find the specific file
        matching_files = {}
        for source, target in all_mappings.items():
            if target.name == file_name or str(target).endswith(file_name):
                matching_files[source] = target
        
        if not matching_files:
            self.console.print(f"[yellow]File '{file_name}' not found in any configured tools[/yellow]")
            return 0
        
        if len(matching_files) > 1:
            self.console.print(f"[yellow]Multiple matches found for '{file_name}':[/yellow]")
            for source, target in matching_files.items():
                self.console.print(f"  • {target}")
            self.console.print("[yellow]Please be more specific or use --tool option[/yellow]")
            return 0
        
        # Sync the single matching file
        source, target = next(iter(matching_files.items()))
        
        # Check if there are differences
        has_diff = self.diff_viewer.compare_files(source, target)
        if not has_diff:
            self.console.print(f"[green]File '{file_name}' is already in sync[/green]")
            return 0
        
        self.console.print(f"[bold]Syncing file: {file_name}[/bold]")
        
        if self._sync_file(source, target, auto_sync, dry_run):
            return 1
        
        return 0
    
    def sync_all_tools(self, target_dir: Path, 
                       auto_sync: Optional[str] = None, dry_run: bool = False,
                       env_set: Optional[str] = None) -> Dict[str, int]:
        """Sync files for all configured tools.
        
        Args:
            target_dir: Target directory
            auto_sync: Automatic sync direction
            dry_run: If True, don't actually sync files
            env_set: Environment set name. If None, syncs all sets.
            
        Returns:
            Dictionary mapping tool names to number of files synced
        """
        results = {}
        
        if env_set:
            # Sync specific environment set
            env_config = self.config.get_environment_set(env_set)
            if not env_config:
                self.console.print(f"[yellow]Environment set '{env_set}' not found[/yellow]")
                return results
            
            self.console.print(f"\n[bold magenta]Environment Set: {env_set}[/bold magenta]")
            if desc := env_config.get("description"):
                self.console.print(f"[dim]{desc}[/dim]")
            
            tools = self.config.get_tools(env_set)
            for tool in tools:
                self.console.print(f"\n[bold blue]Syncing {tool}...[/bold blue]")
                results[f"{env_set}/{tool}"] = self.sync_tool(tool, target_dir, auto_sync, dry_run, env_set)
        else:
            # Sync all environment sets
            env_sets = self.config.get_environment_sets()
            if not env_sets:
                self.console.print("[yellow]No environment sets configured in config.yaml[/yellow]")
                return results
            
            for set_name in env_sets:
                env_config = self.config.get_environment_set(set_name)
                self.console.print(f"\n[bold magenta]Environment Set: {set_name}[/bold magenta]")
                if desc := env_config.get("description"):
                    self.console.print(f"[dim]{desc}[/dim]")
                
                tools = self.config.get_tools(set_name)
                for tool in tools:
                    self.console.print(f"\n[bold blue]Syncing {tool}...[/bold blue]")
                    results[f"{set_name}/{tool}"] = self.sync_tool(tool, target_dir, auto_sync, dry_run, set_name)
        
        return results
    
    def _find_differences(self, file_mapping: Dict[Path, Path]) -> List[Tuple[Path, Path, bool]]:
        """Find files that have differences.
        
        Args:
            file_mapping: Dictionary mapping source to target paths
            
        Returns:
            List of (source, target, has_diff) tuples
        """
        differences = []
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console
        ) as progress:
            task = progress.add_task("Checking files...", total=len(file_mapping))
            
            for source, target in file_mapping.items():
                has_diff = self.diff_viewer.compare_files(source, target)
                if has_diff:
                    differences.append((source, target, has_diff))
                progress.advance(task)
        
        return differences
    
    def _sync_file(self, source: Path, target: Path, 
                   auto_sync: Optional[str], dry_run: bool) -> bool:
        """Sync a single file.
        
        Args:
            source: Source file path (central repo)
            target: Target file path (project)
            auto_sync: Automatic sync direction
            dry_run: If True, don't actually sync
            
        Returns:
            True if file was synced, False if skipped
        """
        # Display diff
        self.console.print(f"\n[bold]File: {target.name}[/bold]")
        self.diff_viewer.display_diff(source, target)
        
        # Determine sync direction
        if auto_sync:
            direction = auto_sync
        else:
            direction = self._prompt_sync_direction(source, target)
        
        if direction == SyncDirection.SKIP:
            self.console.print("[yellow]Skipping file[/yellow]")
            return False
        
        # Perform sync
        if not dry_run:
            self._perform_sync(source, target, direction)
            self.console.print(f"[green]✓ Synced {target.name}[/green]")
        else:
            action = "Would sync" if not dry_run else "Would sync (dry run)"
            if direction == SyncDirection.TO_LOCAL:
                self.console.print(f"[cyan]{action}: Hub → Project[/cyan]")
            else:
                self.console.print(f"[cyan]{action}: Project → Hub[/cyan]")
        
        return True
    
    def _prompt_sync_direction(self, source: Path, target: Path) -> str:
        """Prompt user for sync direction.
        
        Args:
            source: Source file path
            target: Target file path
            
        Returns:
            Sync direction (TO_LOCAL, TO_REMOTE, or SKIP)
        """
        choices = {
            "p": ("Update [P]roject (Hub → Project)", SyncDirection.TO_LOCAL),
            "h": ("Update [H]ub (Project → Hub)", SyncDirection.TO_REMOTE),
            "s": ("[S]kip this file", SyncDirection.SKIP),
            "d": ("[D]isplay full diff", None),
            "c": ("[C]hanges only (context diff)", None),
        }
        
        while True:
            # Display action choices
            self.console.print("\n[bold cyan]Choose action:[/bold cyan]")
            for key, (desc, _) in choices.items():
                self.console.print(f"  {desc}")
            
            choice = Prompt.ask(
                "Select [p/h/s/d/c]",
                choices=[key for key in choices.keys()],
                default="s"
            ).lower()
            
            _, action = choices[choice]
            
            if choice == "d":
                # Show full diff and ask again
                self.diff_viewer.display_diff(source, target, show_full=True)
                continue
            elif choice == "c":
                # Show context diff (changes only) and ask again
                self.diff_viewer.display_diff(source, target, show_context=True)
                continue
            
            return action
    
    def _perform_sync(self, source: Path, target: Path, direction: str):
        """Perform the actual file sync.
        
        Args:
            source: Source file path
            target: Target file path
            direction: Sync direction
        """
        if direction == SyncDirection.TO_LOCAL:
            # Hub → Project
            self._copy_file(source, target, create_backup=True)
        elif direction == SyncDirection.TO_REMOTE:
            # Project → Hub
            self._copy_file(target, source, create_backup=True)
    
    def _copy_file(self, src: Path, dst: Path, create_backup: bool = True):
        """Copy file with optional backup.
        
        Args:
            src: Source file
            dst: Destination file
            create_backup: If True, create backup of destination
        """
        # Create backup if destination exists
        if create_backup and dst.exists():
            backup_path = dst.with_suffix(dst.suffix + '.bak')
            # Add timestamp if backup already exists
            if backup_path.exists():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = dst.with_suffix(f"{dst.suffix}.bak.{timestamp}")
            shutil.copy2(dst, backup_path)
            self.console.print(f"[dim]Created backup: {backup_path}[/dim]")
        
        # Ensure destination directory exists
        dst.parent.mkdir(parents=True, exist_ok=True)
        
        # Copy file
        shutil.copy2(src, dst)