"""File comparison and difference display utilities."""

import difflib
from pathlib import Path
from typing import Optional, List, Tuple
from rich.console import Console
from rich.syntax import Syntax
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text


class DiffViewer:
    """Handles file comparison and visual difference display."""
    
    def __init__(self):
        """Initialize the diff viewer."""
        self.console = Console()
    
    def compare_files(self, source_path: Path, target_path: Path) -> bool:
        """Compare two files and return True if they are different.
        
        Args:
            source_path: Path to source file
            target_path: Path to target file
            
        Returns:
            True if files are different, False if identical
        """
        # If target doesn't exist, they're different
        if not target_path.exists():
            return True
        
        # If source doesn't exist (shouldn't happen), they're different
        if not source_path.exists():
            return True
        
        # Compare file contents
        with open(source_path, 'r', encoding='utf-8') as f:
            source_content = f.read()
        
        with open(target_path, 'r', encoding='utf-8') as f:
            target_content = f.read()
        
        return source_content != target_content
    
    def get_diff_lines(self, source_path: Path, target_path: Path) -> List[str]:
        """Get unified diff lines between two files.
        
        Args:
            source_path: Path to source file
            target_path: Path to target file
            
        Returns:
            List of diff lines
        """
        source_lines = []
        target_lines = []
        
        if source_path.exists():
            with open(source_path, 'r', encoding='utf-8') as f:
                source_lines = f.readlines()
        
        if target_path.exists():
            with open(target_path, 'r', encoding='utf-8') as f:
                target_lines = f.readlines()
        
        diff = difflib.unified_diff(
            target_lines,
            source_lines,
            fromfile=f"Project: {target_path}",
            tofile=f"Hub: {source_path}",
            lineterm=''
        )
        
        return list(diff)
    
    def display_diff(self, source_path: Path, target_path: Path, show_full: bool = False, show_context: bool = False):
        """Display visual diff between two files.
        
        Args:
            source_path: Path to source file (central repo)
            target_path: Path to target file (project)
            show_full: If True, show full file contents side by side
            show_context: If True, show changes with context (default unified diff)
        """
        self.console.print(f"\n[bold blue]Comparing files:[/bold blue]")
        self.console.print(f"Hub: [green]{source_path}[/green]")
        self.console.print(f"Project: [yellow]{target_path}[/yellow]")
        
        if not target_path.exists():
            self.console.print("\n[red]Target file does not exist[/red]")
            if source_path.exists() and show_full:
                self._display_file_content(source_path, "Source (will be created)")
            return
        
        if not source_path.exists():
            self.console.print("\n[red]Source file does not exist[/red]")
            return
        
        if show_full:
            self._display_side_by_side(source_path, target_path)
        elif show_context:
            self._display_context_diff(source_path, target_path)
        else:
            self._display_unified_diff(source_path, target_path)
    
    def _display_unified_diff(self, source_path: Path, target_path: Path):
        """Display unified diff format."""
        diff_lines = self.get_diff_lines(source_path, target_path)
        
        if not diff_lines:
            self.console.print("\n[green]Files are identical[/green]")
            return
        
        # Create syntax highlighted diff
        diff_text = '\n'.join(diff_lines)
        syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=True)
        
        self.console.print("\n[bold]Differences:[/bold]")
        self.console.print(Panel(syntax, title="Unified Diff", border_style="blue"))
    
    def _display_context_diff(self, source_path: Path, target_path: Path):
        """Display context diff showing only changed lines with minimal context."""
        source_lines = []
        target_lines = []
        
        if source_path.exists():
            with open(source_path, 'r', encoding='utf-8') as f:
                source_lines = f.readlines()
        
        if target_path.exists():
            with open(target_path, 'r', encoding='utf-8') as f:
                target_lines = f.readlines()
        
        # Get context diff with minimal context (1 line)
        diff = difflib.context_diff(
            target_lines,
            source_lines,
            fromfile=f"Project: {target_path.name}",
            tofile=f"Hub: {source_path.name}",
            n=1,  # Only 1 line of context
            lineterm=''
        )
        
        diff_lines = list(diff)
        
        if not diff_lines:
            self.console.print("\n[green]Files are identical[/green]")
            return
        
        # Filter to show only changed sections
        filtered_lines = []
        in_change_section = False
        
        for line in diff_lines:
            if line.startswith('***'):
                # Section header
                if 'Target:' in line or 'Source:' in line:
                    filtered_lines.append(line)
                elif ',' in line and ('c' in line or 'd' in line or 'a' in line):
                    # Change indicator line
                    filtered_lines.append(line)
                    in_change_section = True
            elif line.startswith('---'):
                if in_change_section:
                    filtered_lines.append(line)
            elif in_change_section:
                # Changed lines (-, +, !, or context)
                if line.startswith(('- ', '+ ', '! ', '  ')):
                    filtered_lines.append(line)
                elif line.strip() == '':
                    # Empty line - keep minimal context
                    filtered_lines.append(line)
                else:
                    in_change_section = False
        
        if filtered_lines:
            diff_text = '\n'.join(filtered_lines)
            syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=False)
            
            self.console.print("\n[bold]Changes only (with minimal context):[/bold]")
            self.console.print(Panel(syntax, title="Context Diff", border_style="yellow"))
        else:
            self.console.print("\n[green]No significant changes to display[/green]")
    
    def _display_side_by_side(self, source_path: Path, target_path: Path):
        """Display files side by side."""
        with open(source_path, 'r', encoding='utf-8') as f:
            source_content = f.read()
        
        with open(target_path, 'r', encoding='utf-8') as f:
            target_content = f.read()
        
        # Determine file extension for syntax highlighting
        file_ext = source_path.suffix.lstrip('.')
        if file_ext in ['yml', 'yaml']:
            lexer = 'yaml'
        elif file_ext == 'md':
            lexer = 'markdown'
        elif file_ext == 'py':
            lexer = 'python'
        else:
            lexer = 'text'
        
        # Create syntax highlighted panels
        source_syntax = Syntax(source_content, lexer, theme="monokai", line_numbers=True)
        target_syntax = Syntax(target_content, lexer, theme="monokai", line_numbers=True)
        
        source_panel = Panel(source_syntax, title="Hub", border_style="green")
        target_panel = Panel(target_syntax, title="Project", border_style="yellow")
        
        self.console.print("\n[bold]Side-by-side comparison:[/bold]")
        self.console.print(Columns([source_panel, target_panel], equal=True, expand=True))
    
    def _display_file_content(self, file_path: Path, title: str):
        """Display a single file's content."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Determine file extension for syntax highlighting
        file_ext = file_path.suffix.lstrip('.')
        if file_ext in ['yml', 'yaml']:
            lexer = 'yaml'
        elif file_ext == 'md':
            lexer = 'markdown'
        elif file_ext == 'py':
            lexer = 'python'
        else:
            lexer = 'text'
        
        syntax = Syntax(content, lexer, theme="monokai", line_numbers=True)
        panel = Panel(syntax, title=title, border_style="blue")
        
        self.console.print(panel)
    
    def display_summary(self, differences: List[Tuple[Path, Path, bool]]):
        """Display summary of all differences found.
        
        Args:
            differences: List of (source, target, has_diff) tuples
        """
        if not differences:
            self.console.print("\n[green]No files to sync - all files are identical[/green]")
            return
        
        self.console.print(f"\n[bold]Found {len(differences)} file(s) with differences:[/bold]")
        
        for source, target, has_diff in differences:
            if has_diff:
                status = "[red]Different[/red]" if target.exists() else "[yellow]Missing[/yellow]"
                self.console.print(f"  • {target.name}: {status}")
            else:
                self.console.print(f"  • {target.name}: [green]Identical[/green]")