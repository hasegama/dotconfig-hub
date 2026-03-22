"""Command-line interface for dotconfig-hub."""

from datetime import datetime
from pathlib import Path
from typing import Optional

import click
import yaml
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from .compare import EnvSetComparer
from .config import Config
from .project_config import ProjectConfig
from .project_mapping import ProjectMapping
from .sync import FileSyncer

console = Console()


def _load_templates_config(config_file: Path) -> Optional[dict]:
    """Load and validate templates config.yaml.

    Returns config dict on success, None on failure (with error printed to console).
    Related: used by setup() and global_config() commands.
    """
    if not config_file.exists():
        console.print(
            f"[red]Error: config.yaml not found in {config_file.parent}[/red]"
        )
        console.print(
            "[yellow]The templates directory should contain a config.yaml file[/yellow]"
        )
        return None

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            templates_config = yaml.safe_load(f)

        if not templates_config or "environment_sets" not in templates_config:
            console.print("[red]Error: Invalid config.yaml format[/red]")
            console.print(
                "[yellow]The config.yaml should contain 'environment_sets'[/yellow]"
            )
            return None

        return templates_config

    except Exception as e:
        console.print(f"[red]Error reading templates config: {e}[/red]")
        return None


@click.group()
@click.version_option()
def main() -> None:
    """dotconfig-hub - Central management for favorite dotfiles and configuration templates.

    This tool helps you manage and distribute your favorite dotfiles and configuration
    templates across development projects.
    """
    pass


@main.command()
@click.option(
    "--templates-dir",
    "-t",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Path to templates directory",
)
def setup(templates_dir: Path) -> None:
    """Set up dotconfig-hub with templates directory.

    This command configures the templates source directory for the current project.
    The templates directory should contain a config.yaml file with environment sets.

    Examples
    --------
        dotconfig-hub setup --templates-dir ~/dotconfig-templates
        dotconfig-hub setup -t /path/to/templates

    """
    console.print("\n[bold blue]dotconfig-hub Setup[/bold blue]")

    # Initialize project config to check for global defaults
    project_config = ProjectConfig()

    # Prompt for templates directory if not provided
    if not templates_dir:
        # Check for global configuration defaults
        global_templates_source = project_config.get_global_templates_source()
        global_env_sets = project_config.get_global_environment_sets()

        if global_templates_source:
            console.print(
                f"[cyan]Found global default templates source: {global_templates_source}[/cyan]"
            )
            if global_env_sets:
                console.print(
                    f"[cyan]Default environment sets: {', '.join(global_env_sets)}[/cyan]"
                )

            # Ask if user wants to use global defaults
            use_defaults = Confirm.ask("Use these defaults?", default=True)
            if use_defaults:
                templates_dir = global_templates_source
            else:
                console.print("Please enter a different templates directory path.")

        # If no global defaults or user chose not to use them
        if not templates_dir:
            console.print("Please enter the path to your templates directory.")
            console.print("[dim]Example: ~/dotconfig-templates[/dim]")

            while True:
                templates_input = Prompt.ask("Templates directory path")
                if not templates_input.strip():
                    console.print("[red]Please enter a valid path[/red]")
                    continue

                templates_dir = (
                    Path(templates_input.strip("\"'").strip()).expanduser().resolve()
                )
                if templates_dir.exists() and templates_dir.is_dir():
                    break
                else:
                    console.print(f"[red]Directory not found: {templates_dir}[/red]")
                    if not Confirm.ask("Try again?", default=True):
                        console.print("[yellow]Setup cancelled[/yellow]")
                        return

    # Validate templates directory and load config
    templates_dir = templates_dir.resolve()
    templates_config = _load_templates_config(templates_dir / "config.yaml")
    if templates_config is None:
        return

    env_sets = [*templates_config["environment_sets"]]
    console.print(
        f"[green]Found {len(env_sets)} environment sets: {', '.join(env_sets)}[/green]"
    )

    # Check if already configured
    if project_config.exists():
        current_source = project_config.get_templates_source()
        if current_source and current_source != templates_dir:
            if not Confirm.ask(
                f"Templates source is already set to {current_source}. Override?"
            ):
                console.print("[yellow]Setup cancelled[/yellow]")
                return

    # Save configuration
    project_config.set_templates_source(templates_dir)
    project_config.save_config()

    console.print(f"[green]✓ Templates source configured: {templates_dir}[/green]")
    console.print(f"[dim]Configuration saved to: {project_config.config_path}[/dim]")
    console.print("\n[cyan]Next steps:[/cyan]")
    console.print("  1. Run 'dotconfig-hub init' to initialize your project")
    console.print("  2. Run 'dotconfig-hub list' to see available environment sets")


@main.command()
@click.option(
    "--templates-dir",
    "-t",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Path to templates directory",
)
@click.option(
    "--env-sets",
    "-e",
    help="Comma-separated list of default environment sets",
)
def global_config(templates_dir: Path, env_sets: str) -> None:
    """Configure global defaults for dotconfig-hub setup.

    This command sets up global default values that will be suggested
    when running 'dotconfig-hub setup' in new projects.

    Examples
    --------
        dotconfig-hub global-config --templates-dir ~/dotconfig-templates
        dotconfig-hub global-config -t ~/templates -e "default,common"

    """
    console.print("\n[bold blue]Global Configuration Setup[/bold blue]")

    project_config = ProjectConfig()

    # Handle templates directory
    if not templates_dir:
        current_global = project_config.get_global_templates_source()
        if current_global:
            console.print(
                f"[cyan]Current global templates source: {current_global}[/cyan]"
            )
            if not Confirm.ask("Change templates directory?", default=False):
                templates_dir = current_global

        if not templates_dir:
            console.print("Please enter the path to your default templates directory.")
            console.print(
                "[dim]This will be suggested when running 'dotconfig-hub setup'[/dim]"
            )

            while True:
                templates_input = Prompt.ask("Templates directory path")
                if not templates_input.strip():
                    console.print("[red]Please enter a valid path[/red]")
                    continue

                templates_dir = (
                    Path(templates_input.strip("\"'").strip()).expanduser().resolve()
                )
                if templates_dir.exists() and templates_dir.is_dir():
                    break
                else:
                    console.print(f"[red]Directory not found: {templates_dir}[/red]")
                    if not Confirm.ask("Try again?", default=True):
                        console.print("[yellow]Global config cancelled[/yellow]")
                        return

    # Validate templates directory and load config
    templates_dir = templates_dir.resolve()
    templates_config = _load_templates_config(templates_dir / "config.yaml")
    if templates_config is None:
        return

    available_env_sets = [*templates_config["environment_sets"]]
    console.print(
        f"[green]Available environment sets: {', '.join(available_env_sets)}[/green]"
    )

    # Handle environment sets
    environment_sets = []
    if env_sets:
        environment_sets = [s.strip() for s in env_sets.split(",") if s.strip()]
        # Validate environment sets
        invalid_sets = [s for s in environment_sets if s not in available_env_sets]
        if invalid_sets:
            console.print(
                f"[red]Invalid environment sets: {', '.join(invalid_sets)}[/red]"
            )
            console.print(
                f"[yellow]Available sets: {', '.join(available_env_sets)}[/yellow]"
            )
            return
    else:
        current_global_env_sets = project_config.get_global_environment_sets()
        if current_global_env_sets:
            console.print(
                f"[cyan]Current global environment sets: {', '.join(current_global_env_sets)}[/cyan]"
            )
            if not Confirm.ask("Change environment sets?", default=False):
                environment_sets = current_global_env_sets

        if not environment_sets:
            console.print("Select default environment sets (comma-separated):")
            console.print(f"[dim]Available: {', '.join(available_env_sets)}[/dim]")

            env_input = Prompt.ask("Environment sets (optional)", default="")
            if env_input.strip():
                environment_sets = [
                    s.strip() for s in env_input.split(",") if s.strip()
                ]
                invalid_sets = [
                    s for s in environment_sets if s not in available_env_sets
                ]
                if invalid_sets:
                    console.print(
                        f"[red]Invalid environment sets: {', '.join(invalid_sets)}[/red]"
                    )
                    return

    # Save global configuration
    project_config.save_global_config(templates_dir, environment_sets)

    console.print(f"[green]✓ Global templates source: {templates_dir}[/green]")
    if environment_sets:
        console.print(
            f"[green]✓ Global environment sets: {', '.join(environment_sets)}[/green]"
        )
    console.print(
        f"[dim]Global configuration saved to: {project_config.GLOBAL_CONFIG_PATH}[/dim]"
    )
    console.print(
        "\n[cyan]These defaults will be suggested when running 'dotconfig-hub setup'[/cyan]"
    )


@main.command()
@click.option("--env-set", "-e", help="Environment set to initialize")
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Force initialization even if already configured",
)
def init(env_set: str, force: bool) -> None:
    """Initialize current project with configuration templates.

    This command sets up the current project to use specific environment sets
    from the configured templates source.

    Examples
    --------
        dotconfig-hub init --env-set my_project_init_template
        dotconfig-hub init -e my_project_init_template

    """
    console.print("\n[bold blue]dotconfig-hub Project Initialization[/bold blue]")

    # Load project config
    project_config = ProjectConfig()

    # Validate setup
    issues = project_config.validate_setup()
    if issues:
        console.print("[red]Setup issues found:[/red]")
        for issue in issues:
            console.print(f"  • {issue}")
        console.print("\n[yellow]Run 'dotconfig-hub setup' first[/yellow]")
        return

    # Get available environment sets
    templates_config_path = project_config.get_templates_config_path()
    with open(templates_config_path, "r", encoding="utf-8") as f:
        templates_config = yaml.safe_load(f)

    available_sets = [*templates_config["environment_sets"]]

    # Prompt for environment set if not provided
    if not env_set:
        console.print("Available environment sets:")
        for i, set_name in enumerate(available_sets, 1):
            set_config = templates_config["environment_sets"][set_name]
            description = set_config.get("description", "No description")
            console.print(f"  {i}. [cyan]{set_name}[/cyan]: {description}")

        while True:
            choice = Prompt.ask(
                "\nSelect environment set (number or name)",
                choices=[str(i) for i in range(1, len(available_sets) + 1)]
                + available_sets,
                show_choices=False,
            )

            # Handle numeric choice
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(available_sets):
                    env_set = available_sets[idx]
                    break
            # Handle name choice
            elif choice in available_sets:
                env_set = choice
                break

            console.print("[red]Invalid choice[/red]")

    # Validate environment set
    if env_set not in available_sets:
        console.print(f"[red]Unknown environment set: {env_set}[/red]")
        console.print(f"[yellow]Available sets: {', '.join(available_sets)}[/yellow]")
        return

    # Check if already configured
    current_sets = project_config.get_active_environment_sets()
    if env_set in current_sets and not force:
        console.print(f"[yellow]Environment set '{env_set}' is already active[/yellow]")
        console.print("Use --force to reconfigure")
        return

    # Add environment set
    project_config.add_environment_set(env_set)
    project_config.save_config()

    # Update project mapping
    templates_source = project_config.get_templates_source()
    project_mapping = ProjectMapping(templates_source)
    project_mapping.add_project(
        Path.cwd(), project_config.get_active_environment_sets()
    )
    project_mapping.save_mapping()

    set_config = templates_config["environment_sets"][env_set]
    tools = [*set_config.get("tools", {})]

    console.print(f"[green]✓ Environment set '{env_set}' activated[/green]")
    console.print(f"[dim]Tools available: {', '.join(tools)}[/dim]")
    console.print("\n[cyan]Next steps:[/cyan]")
    console.print("  • Run 'dotconfig-hub sync' to synchronize files")
    console.print("  • Run 'dotconfig-hub list' to see configured tools")


@main.command()
@click.option("--tool", "-t", help="Sync only specific tool")
@click.option("--env-set", "-e", help="Sync only specific environment set")
@click.option("--file", "-f", help="Sync only specific file by name (e.g., .gitignore)")
@click.option(
    "--dry-run",
    "-n",
    is_flag=True,
    help="Show what would be synced without making changes",
)
@click.option(
    "--auto-sync",
    type=click.Choice(["local", "remote"]),
    help="Automatically sync in specified direction without prompting",
)
@click.option(
    "--include-init-only",
    is_flag=True,
    help="Include init_only files even if they already exist at the target",
)
def sync(
    tool: str,
    env_set: str,
    file: str,
    dry_run: bool,
    auto_sync: str,
    include_init_only: bool,
) -> None:
    """Synchronize configuration files between templates and project.

    This command syncs files from the configured templates to the current project
    (or vice versa) based on the active environment sets.

    Examples
    --------
        dotconfig-hub sync                    # Sync all active environment sets
        dotconfig-hub sync --dry-run          # Preview changes
        dotconfig-hub sync --tool vscode      # Sync only VS Code settings
        dotconfig-hub sync --file .gitignore  # Sync only .gitignore file
        dotconfig-hub sync --auto-sync local  # Auto-sync to local
        dotconfig-hub sync --include-init-only  # Force sync init_only files too

    """
    console.print("\n[bold blue]dotconfig-hub Sync[/bold blue]")

    # Load project config
    project_config = ProjectConfig()

    # Validate setup
    issues = project_config.validate_setup()
    if issues:
        console.print("[red]Setup issues found:[/red]")
        for issue in issues:
            console.print(f"  • {issue}")
        console.print(
            "\n[yellow]Run 'dotconfig-hub setup' and 'dotconfig-hub init' first[/yellow]"
        )
        return

    # Load templates config
    templates_config_path = project_config.get_templates_config_path()

    # Initialize config with templates source
    cfg = Config(config_path=templates_config_path)

    # Set target directory
    target_directory = Path.cwd()

    # Initialize project mapping
    project_mapping = ProjectMapping(project_config.get_templates_source())

    # Initialize syncer with project mapping (include_init_only: Issue #6)
    syncer = FileSyncer(cfg, project_mapping, include_init_only=include_init_only)

    # Get active environment sets
    active_env_sets = project_config.get_active_environment_sets()
    if env_set:
        if env_set not in active_env_sets:
            console.print(
                f"[yellow]Environment set '{env_set}' is not active for this project[/yellow]"
            )
            if not Confirm.ask("Continue anyway?"):
                return
        active_env_sets = [env_set]

    if not active_env_sets:
        console.print(
            "[yellow]No active environment sets. Run 'dotconfig-hub init' first[/yellow]"
        )
        return

    # Perform sync
    if dry_run:
        console.print("[yellow]DRY RUN MODE - No files will be modified[/yellow]\n")

    try:
        all_results = {}

        if file:
            # Sync specific file
            console.print(f"[bold]Syncing specific file: {file}[/bold]")
            synced = syncer.sync_file(
                file, target_directory, auto_sync, dry_run, env_set
            )
            all_results[f"file/{file}"] = synced
        else:
            # Sync by tool or all tools
            for env_set_name in active_env_sets:
                console.print(
                    f"\n[bold magenta]Environment Set: {env_set_name}[/bold magenta]"
                )

                if tool:
                    # Sync specific tool
                    available_tools = cfg.get_tools(env_set_name)
                    if tool not in available_tools:
                        console.print(
                            f"[red]Tool '{tool}' not found in environment set '{env_set_name}'[/red]"
                        )
                        console.print(
                            f"[yellow]Available tools: {', '.join(available_tools)}[/yellow]"
                        )
                        continue

                    synced = syncer.sync_tool(
                        tool, target_directory, auto_sync, dry_run, env_set_name
                    )
                    all_results[f"{env_set_name}/{tool}"] = synced
                else:
                    # Sync all tools in environment set
                    results = syncer.sync_all_tools(
                        target_directory, auto_sync, dry_run, env_set_name
                    )
                    all_results.update(results)

        _display_results(all_results, dry_run)

        # Update project mapping after successful sync
        if not dry_run and any(count > 0 for count in all_results.values()):
            project_mapping.add_project(target_directory, active_env_sets)
            project_mapping.update_last_synced(target_directory)
            project_mapping.save_mapping()
            console.print("\n[dim]Updated project mapping[/dim]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Sync cancelled by user[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error during sync: {e}[/red]")
        raise


@main.command()
def list() -> None:
    """List available environment sets and tools.

    Shows the currently configured templates and active environment sets
    for this project.
    """
    console.print("\n[bold blue]dotconfig-hub Configuration[/bold blue]")

    # Load project config
    project_config = ProjectConfig()

    # Check if configured
    if not project_config.exists():
        console.print(
            "[yellow]Project not configured. Run 'dotconfig-hub setup' first.[/yellow]"
        )
        return

    # Display templates source
    templates_source = project_config.get_templates_source()
    if templates_source:
        console.print(f"[bold]Templates Source:[/bold] {templates_source}")
    else:
        console.print("[red]Templates source not configured[/red]")
        return

    # Validate setup
    issues = project_config.validate_setup()
    if issues:
        console.print("\n[red]Setup issues:[/red]")
        for issue in issues:
            console.print(f"  • {issue}")
        return

    # Load templates config
    templates_config_path = project_config.get_templates_config_path()
    with open(templates_config_path, "r", encoding="utf-8") as f:
        templates_config = yaml.safe_load(f)

    # Display available environment sets
    console.print("\n[bold]Available Environment Sets:[/bold]")
    active_sets = set(project_config.get_active_environment_sets())

    for set_name, set_config in templates_config["environment_sets"].items():
        status = "[green]●[/green]" if set_name in active_sets else "[dim]○[/dim]"
        description = set_config.get("description", "No description")
        console.print(f"  {status} [cyan]{set_name}[/cyan]: {description}")

        if set_name in active_sets:
            tools = [*set_config.get("tools", {})]
            if tools:
                console.print(f"    [dim]Tools: {', '.join(tools)}[/dim]")

    console.print(
        "\n[dim]Legend: [green]●[/green] Active  [dim]○[/dim] Available[/dim]"
    )


@main.command()
@click.option("--env-set", "-e", help="Show projects using specific environment set")
@click.option("--cleanup", is_flag=True, help="Remove missing projects from mapping")
def projects(env_set: str, cleanup: bool) -> None:
    """List projects tracked by dotconfig-hub.

    Shows all projects using the templates and their associated environment sets.

    Examples
    --------
        dotconfig-hub projects                    # List all tracked projects
        dotconfig-hub projects --env-set python_dev  # List projects using python_dev
        dotconfig-hub projects --cleanup          # Clean up missing projects

    """
    console.print("\n[bold blue]dotconfig-hub Tracked Projects[/bold blue]")

    # Load project config
    project_config = ProjectConfig()

    # Validate setup
    issues = project_config.validate_setup()
    if issues:
        console.print("[red]Setup issues found:[/red]")
        for issue in issues:
            console.print(f"  • {issue}")
        return

    # Load project mapping
    templates_source = project_config.get_templates_source()
    if not templates_source:
        console.print("[red]Templates source not configured[/red]")
        return

    project_mapping = ProjectMapping(templates_source)

    # Cleanup if requested
    if cleanup:
        removed = project_mapping.cleanup_missing_projects()
        if removed:
            project_mapping.save_mapping()
            console.print(f"[yellow]Removed {len(removed)} missing projects:[/yellow]")
            for path in removed:
                console.print(f"  • {path}")
        else:
            console.print("[green]No missing projects found[/green]")
        return

    # Get projects
    if env_set:
        projects = project_mapping.get_projects_by_environment_set(env_set)
        if not projects:
            console.print(
                f"[yellow]No projects found using environment set '{env_set}'[/yellow]"
            )
            return
        console.print(f"\n[bold]Projects using '{env_set}':[/bold]")
    else:
        all_projects = project_mapping.get_all_projects()
        if not all_projects:
            console.print("[yellow]No tracked projects found[/yellow]")
            console.print(
                "[dim]Projects are tracked when you run 'dotconfig-hub init' or 'sync'[/dim]"
            )
            return

        # Convert to list format for consistent display
        projects = []
        for path, info in all_projects.items():
            project_info = info.copy()
            project_info["path"] = path
            projects.append(project_info)

    # Display projects
    table = Table(title="\nTracked Projects")
    table.add_column("Project Path", style="cyan")
    table.add_column("Environment Sets", style="green")
    table.add_column("Last Synced", style="dim")

    for project in projects:
        path = project["path"]
        env_sets = ", ".join(project.get("environment_sets", []))
        last_synced = project.get("last_synced", "Never")

        # Format timestamp
        if last_synced != "Never":
            try:
                dt = datetime.fromisoformat(last_synced)
                last_synced = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                pass

        table.add_row(path, env_sets, last_synced)

    console.print(table)

    # Show usage statistics
    if not env_set:
        usage = project_mapping.get_environment_set_usage()
        if usage:
            console.print("\n[bold]Environment Set Usage:[/bold]")
            for set_name, count in sorted(
                usage.items(), key=lambda x: x[1], reverse=True
            ):
                console.print(
                    f"  • [cyan]{set_name}[/cyan]: {count} project{'s' if count > 1 else ''}"
                )


@main.command()
@click.argument("set_a")
@click.argument("set_b")
@click.option("--tool", "-t", help="Filter comparison to a specific tool")
@click.option(
    "--file",
    "-f",
    "file_pattern",
    help="Filter to specific file pattern (supports wildcards like *.toml, configs/*)",
)
@click.option(
    "--merge",
    "-m",
    is_flag=True,
    help="Enable interactive merge mode (default is compare-only)",
)
@click.option(
    "--dry-run",
    "-n",
    is_flag=True,
    help="Preview merge without writing files (requires --merge)",
)
def compare(
    set_a: str,
    set_b: str,
    tool: str,
    file_pattern: str,
    merge: bool,
    dry_run: bool,
) -> None:
    """Compare files across two environment sets.

    Finds common files between SET_A and SET_B by matching relative paths
    within shared tools, then displays their differences. Use --merge to
    interactively copy selected files between sets.

    This command operates entirely within the hub (template repository)
    and does not require a project to be set up.

    Examples
    --------
        dotconfig-hub compare my_project_init_template minimal_template
        dotconfig-hub compare set_a set_b --tool vscode
        dotconfig-hub compare set_a set_b --file "*.json"
        dotconfig-hub compare set_a set_b --merge
        dotconfig-hub compare set_a set_b --merge --dry-run

    """
    console.print("\n[bold blue]dotconfig-hub Compare[/bold blue]")

    # Load hub config directly (no project setup required)
    cfg = Config()

    # Validate environment sets exist
    available_sets = cfg.get_environment_sets()
    for name in (set_a, set_b):
        if name not in available_sets:
            console.print(f"[red]Environment set '{name}' not found[/red]")
            console.print(
                f"[yellow]Available sets: {', '.join(available_sets)}[/yellow]"
            )
            return

    if set_a == set_b:
        console.print("[yellow]Cannot compare an environment set with itself[/yellow]")
        return

    comparer = EnvSetComparer(cfg, console)

    try:
        if merge:
            if dry_run:
                console.print(
                    "[yellow]DRY RUN MODE - No files will be modified[/yellow]\n"
                )
            comparer.merge(set_a, set_b, tool, file_pattern, dry_run)
        else:
            if dry_run:
                console.print(
                    "[yellow]--dry-run has no effect without --merge[/yellow]\n"
                )
            diff_count = comparer.compare(set_a, set_b, tool, file_pattern)
            if diff_count > 0:
                console.print(
                    f"\n[dim]Found {diff_count} difference(s). "
                    f"Use --merge to interactively merge.[/dim]"
                )
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
    except KeyboardInterrupt:
        console.print("\n[yellow]Compare cancelled by user[/yellow]")



def _display_results(results: dict, dry_run: bool) -> None:
    """Display sync results in a table.

    Args:
    ----
        results: Dictionary mapping tool names to sync counts
        dry_run: Whether this was a dry run

    """
    if not results:
        console.print("\n[green]No files needed synchronization[/green]")
        return

    # Create results table
    table = Table(title="\nSync Results" + (" (Dry Run)" if dry_run else ""))
    table.add_column("Environment/Tool", style="cyan")
    table.add_column("Files Synced", style="green")

    total = 0
    for tool, count in results.items():
        table.add_row(tool, str(count))
        total += count

    if len(results) > 1:
        table.add_row("[bold]Total[/bold]", f"[bold]{total}[/bold]")

    console.print(table)

    if dry_run:
        console.print("\n[yellow]This was a dry run. No files were modified.[/yellow]")
        console.print("[dim]Run without --dry-run to apply changes.[/dim]")


if __name__ == "__main__":
    main()
