"""Command-line interface for dotconfig-hub."""

import click
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm, Prompt

from .config import Config
from .sync import FileSyncer
from .project_config import ProjectConfig


console = Console()


@click.group()
@click.version_option()
def main():
    """dotconfig-hub - Central management for favorite dotfiles and configuration templates.
    
    This tool helps you manage and distribute your favorite dotfiles and configuration
    templates across development projects.
    """
    pass


@main.command()
@click.option('--templates-dir', '-t', 
              type=click.Path(exists=True, file_okay=False, path_type=Path),
              help='Path to templates directory')
def setup(templates_dir: Path):
    """Set up dotconfig-hub with templates directory.
    
    This command configures the templates source directory for the current project.
    The templates directory should contain a config.yaml file with environment sets.
    
    Examples:
        dotconfig-hub setup --templates-dir ~/dotconfig-templates
        dotconfig-hub setup -t /path/to/templates
    """
    console.print("\n[bold blue]dotconfig-hub Setup[/bold blue]")
    
    # Prompt for templates directory if not provided
    if not templates_dir:
        console.print("Please enter the path to your templates directory.")
        console.print("[dim]Example: ~/dotconfig-templates[/dim]")
        
        while True:
            templates_input = Prompt.ask("Templates directory path")
            if not templates_input.strip():
                console.print("[red]Please enter a valid path[/red]")
                continue
            
            templates_dir = Path(templates_input.strip('"\'').strip()).expanduser().resolve()
            if templates_dir.exists() and templates_dir.is_dir():
                break
            else:
                console.print(f"[red]Directory not found: {templates_dir}[/red]")
                if not Confirm.ask("Try again?", default=True):
                    console.print("[yellow]Setup cancelled[/yellow]")
                    return
    
    # Validate templates directory
    templates_dir = templates_dir.resolve()
    config_file = templates_dir / "config.yaml"
    
    if not config_file.exists():
        console.print(f"[red]Error: config.yaml not found in {templates_dir}[/red]")
        console.print("[yellow]The templates directory should contain a config.yaml file[/yellow]")
        return
    
    # Load and validate templates config
    try:
        import yaml
        with open(config_file, 'r', encoding='utf-8') as f:
            templates_config = yaml.safe_load(f)
        
        if not templates_config or "environment_sets" not in templates_config:
            console.print(f"[red]Error: Invalid config.yaml format[/red]")
            console.print("[yellow]The config.yaml should contain 'environment_sets'[/yellow]")
            return
        
        env_sets = [key for key in templates_config["environment_sets"].keys()]
        console.print(f"[green]Found {len(env_sets)} environment sets: {', '.join(env_sets)}[/green]")
        
    except Exception as e:
        console.print(f"[red]Error reading templates config: {e}[/red]")
        return
    
    # Initialize project config
    project_config = ProjectConfig()
    
    # Check if already configured
    if project_config.exists():
        current_source = project_config.get_templates_source()
        if current_source and current_source != templates_dir:
            if not Confirm.ask(f"Templates source is already set to {current_source}. Override?"):
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
@click.option('--env-set', '-e', help='Environment set to initialize')
@click.option('--force', '-f', is_flag=True, help='Force initialization even if already configured')
def init(env_set: str, force: bool):
    """Initialize current project with configuration templates.
    
    This command sets up the current project to use specific environment sets
    from the configured templates source.
    
    Examples:
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
    with open(templates_config_path, 'r', encoding='utf-8') as f:
        import yaml
        templates_config = yaml.safe_load(f)
    
    available_sets = [key for key in templates_config["environment_sets"].keys()]
    
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
                choices=[str(i) for i in range(1, len(available_sets) + 1)] + available_sets,
                show_choices=False
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
    
    set_config = templates_config["environment_sets"][env_set]
    tools = [key for key in set_config.get("tools", {}).keys()]
    
    console.print(f"[green]✓ Environment set '{env_set}' activated[/green]")
    console.print(f"[dim]Tools available: {', '.join(tools)}[/dim]")
    console.print("\n[cyan]Next steps:[/cyan]")
    console.print("  • Run 'dotconfig-hub sync' to synchronize files")
    console.print("  • Run 'dotconfig-hub list' to see configured tools")


@main.command()
@click.option('--tool', '-t', help='Sync only specific tool')
@click.option('--env-set', '-e', help='Sync only specific environment set')
@click.option('--file', '-f', help='Sync only specific file by name (e.g., .gitignore)')
@click.option('--dry-run', '-n', is_flag=True, help='Show what would be synced without making changes')
@click.option('--auto-sync', type=click.Choice(['local', 'remote']), 
              help='Automatically sync in specified direction without prompting')
def sync(tool: str, env_set: str, file: str, dry_run: bool, auto_sync: str):
    """Synchronize configuration files between templates and project.
    
    This command syncs files from the configured templates to the current project
    (or vice versa) based on the active environment sets.
    
    Examples:
        dotconfig-hub sync                    # Sync all active environment sets
        dotconfig-hub sync --dry-run          # Preview changes
        dotconfig-hub sync --tool vscode      # Sync only VS Code settings
        dotconfig-hub sync --file .gitignore  # Sync only .gitignore file
        dotconfig-hub sync --auto-sync local  # Auto-sync to local
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
        console.print("\n[yellow]Run 'dotconfig-hub setup' and 'dotconfig-hub init' first[/yellow]")
        return
    
    # Load templates config
    templates_config_path = project_config.get_templates_config_path()
    
    # Initialize config with templates source
    cfg = Config(config_path=templates_config_path)
    
    # Set target directory
    target_directory = Path.cwd()
    
    # Initialize syncer
    syncer = FileSyncer(cfg)
    
    # Get active environment sets
    active_env_sets = project_config.get_active_environment_sets()
    if env_set:
        if env_set not in active_env_sets:
            console.print(f"[yellow]Environment set '{env_set}' is not active for this project[/yellow]")
            if not Confirm.ask("Continue anyway?"):
                return
        active_env_sets = [env_set]
    
    if not active_env_sets:
        console.print("[yellow]No active environment sets. Run 'dotconfig-hub init' first[/yellow]")
        return
    
    # Perform sync
    if dry_run:
        console.print("[yellow]DRY RUN MODE - No files will be modified[/yellow]\n")
    
    try:
        all_results = {}
        
        if file:
            # Sync specific file
            console.print(f"[bold]Syncing specific file: {file}[/bold]")
            synced = syncer.sync_file(file, target_directory, auto_sync, dry_run, env_set)
            all_results[f"file/{file}"] = synced
        else:
            # Sync by tool or all tools
            for env_set_name in active_env_sets:
                console.print(f"\n[bold magenta]Environment Set: {env_set_name}[/bold magenta]")
                
                if tool:
                    # Sync specific tool
                    available_tools = cfg.get_tools(env_set_name)
                    if tool not in available_tools:
                        console.print(f"[red]Tool '{tool}' not found in environment set '{env_set_name}'[/red]")
                        console.print(f"[yellow]Available tools: {', '.join(available_tools)}[/yellow]")
                        continue
                    
                    synced = syncer.sync_tool(tool, target_directory, auto_sync, dry_run, env_set_name)
                    all_results[f"{env_set_name}/{tool}"] = synced
                else:
                    # Sync all tools in environment set
                    results = syncer.sync_all_tools(target_directory, auto_sync, dry_run, env_set_name)
                    all_results.update(results)
        
        _display_results(all_results, dry_run)
    
    except KeyboardInterrupt:
        console.print("\n[yellow]Sync cancelled by user[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error during sync: {e}[/red]")
        raise


@main.command()
def list():
    """List available environment sets and tools.
    
    Shows the currently configured templates and active environment sets
    for this project.
    """
    console.print("\n[bold blue]dotconfig-hub Configuration[/bold blue]")
    
    # Load project config
    project_config = ProjectConfig()
    
    # Check if configured
    if not project_config.exists():
        console.print("[yellow]Project not configured. Run 'dotconfig-hub setup' first.[/yellow]")
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
    with open(templates_config_path, 'r', encoding='utf-8') as f:
        import yaml
        templates_config = yaml.safe_load(f)
    
    # Display available environment sets
    console.print("\n[bold]Available Environment Sets:[/bold]")
    active_sets = set(project_config.get_active_environment_sets())
    
    for set_name, set_config in templates_config["environment_sets"].items():
        status = "[green]●[/green]" if set_name in active_sets else "[dim]○[/dim]"
        description = set_config.get("description", "No description")
        console.print(f"  {status} [cyan]{set_name}[/cyan]: {description}")
        
        if set_name in active_sets:
            tools = [key for key in set_config.get("tools", {}).keys()]
            if tools:
                console.print(f"    [dim]Tools: {', '.join(tools)}[/dim]")
    
    console.print(f"\n[dim]Legend: [green]●[/green] Active  [dim]○[/dim] Available[/dim]")


def _display_results(results: dict, dry_run: bool):
    """Display sync results in a table.
    
    Args:
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