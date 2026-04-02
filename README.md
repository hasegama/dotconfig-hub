# dotconfig-hub

Centrally manage and distribute your development configurations across projects.

dotconfig-hub keeps your dotfiles, IDE settings, AI assistant instructions, CI/CD workflows, and other configuration templates in a single **hub repository**, and syncs them bidirectionally to any number of projects.

## Key Features

- **Environment Sets** — Group related configurations (e.g., Python dev, AI assistants) and activate them per project.
- **Bidirectional Sync** — Push templates to projects, or pull project improvements back to the hub.
- **Interactive Mode** — When arguments are omitted, CLI prompts guide you through each action.
- **Init-Only Files** — Mark files that should only be delivered on first setup and never overwritten.
- **File Rename Rules** — Rename files during delivery (e.g., `.gitignore.hub` in the hub becomes `.gitignore` in the project).
- **Compare & Merge** — Diff files across environment sets and selectively merge between them.
- **Project Tracking** — Automatically records which projects use which environment sets.
- **Safe Operations** — Dry-run previews, automatic backups, and content-based change detection.

## Installation

Requires Python 3.9+.

```bash
# From PyPI
pip install dotconfig-hub
# or
uv add dotconfig-hub

# From source
git clone https://github.com/hasegama/dotconfig-hub.git
cd dotconfig-hub
pip install -e .
```

## Quick Start

### 1. Prepare a templates repository

Clone or create a repository that will serve as your central hub:

```bash
git clone https://github.com/your-org/dotconfig-templates.git ~/dotconfig-templates
```

The hub contains a `config.yaml` that defines your environment sets (see [Configuration](#configuration)).

### 2. Set up a project

```bash
cd /path/to/your-project
dotconfig-hub setup --templates-dir ~/dotconfig-templates
dotconfig-hub init                  # Select environment sets interactively
dotconfig-hub sync                  # Sync files from hub to project
```

### 3. Keep in sync

```bash
dotconfig-hub sync --dry-run        # Preview what would change
dotconfig-hub sync                  # Apply interactively
dotconfig-hub sync --auto-sync local   # Hub -> Project (no prompts)
dotconfig-hub sync --auto-sync remote  # Project -> Hub (no prompts)
```

## How It Works

```
~/dotconfig-templates/              # Hub (templates repository)
├── config.yaml                     # Environment set definitions
├── project_mapping.yaml            # Auto-maintained project registry
├── my_project_init_template/       # Environment set directory
│   ├── .claude/
│   ├── .github/
│   └── .vscode/
└── minimal_template/
    └── .vscode/

your-project/                       # Any project
├── dotconfig-hub.yaml              # Project-level settings
├── .claude/                        # <- Synced from hub
├── .github/                        # <- Synced from hub
└── .vscode/                        # <- Synced from hub
```

Each **environment set** groups one or more **tools** (logical units like `vscode`, `github`, `claude_config`), and each tool maps to a set of files in the hub. When you sync, dotconfig-hub compares hub files against project files and lets you choose the sync direction per file.

## CLI Reference

### `setup`

Configure the templates source for the current project.

```bash
dotconfig-hub setup                          # Interactive
dotconfig-hub setup --templates-dir ~/path   # Explicit
```

### `global-config`

Set machine-wide defaults for templates source and environment sets. These are suggested during interactive `setup` prompts.

```bash
dotconfig-hub global-config --templates-dir ~/dotconfig-templates
dotconfig-hub global-config --env-sets my_project_init_template,minimal_template
```

### `init`

Activate environment sets for the current project.

```bash
dotconfig-hub init                            # Interactive selection
dotconfig-hub init --env-set my_project_init_template --force
```

### `sync`

Synchronize files between hub and project.

```bash
dotconfig-hub sync                            # Interactive per-file prompts
dotconfig-hub sync --dry-run                  # Preview only
dotconfig-hub sync --auto-sync local          # Hub -> Project
dotconfig-hub sync --auto-sync remote         # Project -> Hub
dotconfig-hub sync --tool claude_config       # Sync specific tool only
dotconfig-hub sync --env-set minimal_template # Sync specific environment set
dotconfig-hub sync --file ".gitignore"        # Sync files matching pattern
dotconfig-hub sync --include-init-only        # Force sync init_only files
```

Interactive sync prompt:

```
Choose action:
  Update [P]roject (Hub -> Project)
  Update [H]ub (Project -> Hub)
  [S]kip this file
  [D]isplay full diff
  [C]hanges only (context diff)
Select [p/h/s/d/c] (s):
```

### `list`

Show configuration status — templates source, available environment sets, and active tools.

```bash
dotconfig-hub list
```

### `projects`

View and manage tracked projects.

```bash
dotconfig-hub projects                                    # List all
dotconfig-hub projects --env-set my_project_init_template # Filter by set
dotconfig-hub projects --cleanup                          # Remove missing projects
```

### `compare`

Compare files across two environment sets within the hub. No project setup required.

```bash
dotconfig-hub compare set_a set_b               # Show common file diffs
dotconfig-hub compare set_a set_b --tool vscode  # Filter by tool
dotconfig-hub compare set_a set_b --file "*.json" # Filter by file pattern
dotconfig-hub compare set_a set_b --merge        # Interactive merge mode
dotconfig-hub compare set_a set_b --merge --dry-run
```

## Configuration

### Hub: `config.yaml`

Defines environment sets and their tools in the templates repository:

```yaml
environment_sets:
  my_project_init_template:
    description: "Complete project initialization template"
    tools:
      claude_config:
        project_dir: my_project_init_template
        files:
          - CLAUDE.md
          - .claude/commands/*.md
          - { source: ".github/CODEOWNERS", init_only: true }

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

      git_config:
        project_dir: my_project_init_template
        files:
          # Renamed on delivery: .gitignore.hub in the hub -> .gitignore in the project
          - { source: .gitignore.hub, target: .gitignore, init_only: true }
```

File entries can be:
- **String** — `"path/to/file"` or `"path/*.ext"` (glob patterns supported, always synced)
- **Dict** — `{ source: "file", init_only: true }` (synced only on first setup; never overwrites existing files)
- **Dict with rename** — `{ source: ".gitignore.hub", target: ".gitignore" }` (renamed during delivery; glob patterns not supported with rename)

### Project: `dotconfig-hub.yaml`

Created by `setup` and `init` in each project:

```yaml
templates_source: ~/dotconfig-templates
active_environment_sets:
  - my_project_init_template
```

### Project Mapping: `project_mapping.yaml`

Auto-maintained in the hub. Tracks which projects use which sets:

```yaml
projects:
  ~/workspace/my-project:
    environment_sets:
      - my_project_init_template
    last_synced: "2024-01-15T10:30:00Z"
```

## Use Cases

- **AI Assistant Instructions** — Claude (`CLAUDE.md`, commands), GitHub Copilot, Cursor rules
- **IDE Settings** — VS Code settings, extensions, tasks, launch configurations
- **CI/CD Workflows** — GitHub Actions, pre-commit hooks, Dependabot
- **Code Quality** — Linter and formatter configurations (ruff, ESLint, Prettier)
- **Project Templates** — Issue templates, PR templates, contributing guides, `.gitignore`

## Development

Built with [Claude Code](https://claude.ai/code).

### Dependencies

| Runtime | Development |
|---------|-------------|
| click | ruff |
| pyyaml | black |
| rich | pytest |
| gitpython | pre-commit |

### Contributing

1. Fork the repository
2. Create a feature branch (`feature/your-feature`)
3. Make your changes
4. Submit a pull request

See the [Git-Flow](https://nvie.com/posts/a-successful-git-branching-model/) branching model and [Conventional Commits](https://www.conventionalcommits.org/) for commit messages.

## License

MIT License — see [LICENSE](LICENSE) for details.
