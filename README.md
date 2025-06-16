# 🛠️ dotconfig-hub

Your favorite dotfiles and configuration templates, centrally managed and easily distributed across projects.

## 🤔 What is dotconfig-hub?

dotconfig-hub is a tool that helps you manage and sync your favorite development configurations across multiple projects. Whether it's VS Code settings, GitHub workflows, linting configs, or AI assistant instructions (Claude, Copilot, Cursor), keep them all in one place and distribute them effortlessly.

## ✨ Key Features

- **🏠 Central Hub**: One repository for all your configuration templates
- **📦 Separated Architecture**: Templates live outside site-packages
- **🎯 Environment Sets**: Group related configs (Python env, TypeScript env, AI assistants)
- **🔄 Two-way Sync**: Update templates from projects or projects from templates
- **💬 Interactive Mode**: Friendly prompts when arguments are omitted
- **📋 Smart Diff Display**: Content-based change detection with multiple viewing options (full, unified, context-only)
- **🔒 Safe Operations**: Automatic backups and dry-run mode

## 🚀 Quick Start

### Set up templates repository (once per machine)

```bash
# Clone templates to a shared location
git clone https://github.com/hasegama/dotconfig-hub.git ~/dotconfig-templates
```

### Use in any project

```bash
# Install dotconfig-hub
cd /path/to/your-project
uv add dotconfig-hub

# Configure (interactive prompts)
dotconfig-hub setup
dotconfig-hub init

# Sync your configurations
dotconfig-hub sync
```

That's it! Your project now has your favorite configurations.

## 📦 Installation

### From PyPI (recommended)

```bash
pip install dotconfig-hub
# or
uv add dotconfig-hub
```

### From source

```bash
git clone https://github.com/hasegama/dotconfig-hub.git
cd dotconfig-hub
pip install -e .
# or
uv add -e .
```

## 🏗️ How It Works

### Architecture

```
~/dotconfig-templates/          # Your central configuration hub
├── config.yaml                 # Defines environment sets and tools
├── my_project_init_template/    # Example environment set
│   ├── .claude/                 # Claude configurations
│   ├── .github/                 # GitHub workflows and templates
│   └── .vscode/                 # VS Code settings
└── ...

your-project/                    # Any project directory
├── dotconfig-hub.yaml          # Project-specific settings
├── .claude/                     # ← Synced from templates
├── .github/                     # ← Synced from templates
├── .vscode/                     # ← Synced from templates
└── ...
```

### Configuration Files

**Templates Repository** (`~/dotconfig-templates/config.yaml`):
```yaml
environment_sets:
  my_project_init_template:
    description: "Complete project initialization template"
    tools:
      claude_config:
        project_dir: my_project_init_template
        files:
          - .claude/CLAUDE.md
          - .claude/commands/*.md
      
      vscode:
        project_dir: my_project_init_template
        files:
          - .vscode/settings.json
          - .vscode/extensions.json
      
      github:
        project_dir: my_project_init_template
        files:
          - .github/workflows/*.yml
          - .github/ISSUE_TEMPLATE/*.md
          - .github/dependabot.yml
```

**Project Configuration** (`./dotconfig-hub.yaml`):
```yaml
templates_source: ~/dotconfig-templates
active_environment_sets:
  - my_project_init_template
sync_preferences:
  auto_sync: false
  create_backups: true
  dry_run_default: false
```

## 💻 Commands

### Setup Commands

```bash
# Configure templates source (interactive)
dotconfig-hub setup

# Configure with specific directory
dotconfig-hub setup --templates-dir ~/dotconfig-templates

# Initialize project (interactive)
dotconfig-hub init

# Initialize with specific environment set
dotconfig-hub init --env-set my_project_init_template --force
```

### Sync Commands

```bash
# Sync all active environment sets
dotconfig-hub sync

# Preview changes without applying
dotconfig-hub sync --dry-run

# Sync specific tool only
dotconfig-hub sync --tool claude_config

# Auto-sync from templates to project
dotconfig-hub sync --auto-sync local

# Auto-sync from project to templates  
dotconfig-hub sync --auto-sync remote
```

### Information Commands

```bash
# Show configuration status
dotconfig-hub list
```

## 💬 Interactive Mode

All commands support interactive mode when arguments are omitted:

- **`dotconfig-hub setup`** prompts for templates directory
- **`dotconfig-hub init`** shows available environment sets with descriptions
- **`dotconfig-hub sync`** asks for sync direction on each changed file

Example sync interaction:
```
Choose action:
  Update [P]roject (Hub → Project)
  Update [H]ub (Project → Hub)
  [S]kip this file
  [D]isplay full diff
  [C]hanges only (context diff)
Select [p/h/s/d/c] (s):
```

## 🔧 Common Workflows

### Daily Development

```bash
cd your-project
dotconfig-hub sync --dry-run    # Check what would change
dotconfig-hub sync              # Apply changes
```

### Setting Up New Project

```bash
cd new-project
uv add dotconfig-hub
dotconfig-hub setup             # Point to your templates
dotconfig-hub init              # Choose environment set
dotconfig-hub sync              # Get all configurations
```

### Updating Templates

```bash
cd project-with-improved-configs
dotconfig-hub sync --auto-sync remote  # Push improvements to templates
```

### Creating New Environment Set

1. Add configuration to `~/dotconfig-templates/config.yaml`
2. Create corresponding files in template directory
3. Use `dotconfig-hub init` in projects to activate

## 🎯 Use Cases

Perfect for managing:

- **🤖 AI Assistant Instructions**: Claude, GitHub Copilot, Cursor configurations
- **⚙️ IDE Settings**: VS Code settings, extensions, tasks, launch configs
- **🔄 CI/CD Workflows**: GitHub Actions, pre-commit hooks, dependabot
- **📏 Code Quality**: ESLint, Prettier, flake8, Black configurations
- **📝 Project Templates**: Issue templates, PR templates, contributing guides

## 📝 Examples

### Python Development Environment

```yaml
environment_sets:
  python_dev:
    description: "Python development with linting and testing"
    tools:
      vscode:
        project_dir: python_dev
        files:
          - .vscode/settings.json      # Python-specific settings
          - .vscode/extensions.json    # Recommended extensions
      
      linting:
        project_dir: python_dev  
        files:
          - .flake8
          - pyproject.toml            # Black, isort config
          - .pre-commit-config.yaml
      
      github:
        project_dir: python_dev
        files:
          - .github/workflows/test.yml
          - .github/dependabot.yml
```

### AI Assistant Configurations

```yaml
environment_sets:
  ai_assistants:
    description: "AI coding assistant instructions"
    tools:
      claude:
        project_dir: ai_assistants
        files:
          - .claude/CLAUDE.md
          - .claude/commands/*.md
      
      cursor:
        project_dir: ai_assistants
        files:
          - .cursorrules
```

## 👩‍💻 Development

This project was developed using [Claude Code](https://claude.ai/code), Anthropic's official CLI for Claude.

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

### Requirements

- Python 3.8+
- Dependencies: click, pyyaml, rich, gitpython

## 📄 License

MIT License - see LICENSE file for details

---

**Happy configuring!** 🚀 Keep your development environment consistent across all your projects.