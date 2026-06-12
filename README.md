# dotconfig-hub

Centrally manage and distribute your development configurations across projects.

dotconfig-hub keeps your dotfiles, IDE settings, AI assistant instructions, CI/CD workflows, and other configuration templates in a single **hub repository**, and syncs them bidirectionally to any number of projects — with automatic versioned backups you can roll back to at any time.

## Key Features

- **Environment Sets** — Group related configurations (e.g., Python dev, AI assistants) and activate them per project.
- **Bidirectional Sync** — Push templates to projects, or pull project improvements back to the hub.
- **Interactive Mode** — When arguments are omitted, CLI prompts guide you through each action, showing diffs and full file paths before you decide.
- **Versioned Backups** — Every file overwritten or deleted during a sync is backed up as `<name>.bak.<timestamp>`. All backups from one sync run share the same timestamp, so each run forms a single restorable **version**.
- **Rollback** — Restore the hub or a project to any backup version with `dotconfig-hub rollback`.
- **Backup Cleanup** — Remove accumulated backup files per side with `dotconfig-hub clean`.
- **Delete with Backup** — When a file exists on only one side, sync can delete the surviving copy safely (it is renamed to a backup, never destroyed).
- **Init-Only Files** — Mark files that should only be delivered on first setup and never overwritten.
- **File Rename Rules** — Rename files during delivery (e.g., `.gitignore.hub` in the hub becomes `.gitignore` in the project).
- **Compare & Merge** — Diff files across environment sets and selectively merge between them.
- **Project Tracking** — Automatically records which projects use which environment sets.
- **Global Excludes** — Backup files and OS metadata (`.DS_Store`) are excluded from sync everywhere by default; add your own gitignore-style patterns via the top-level `exclude:` key.
- **Safe Operations** — Dry-run previews, confirmation prompts, and content-based change detection.

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

### 4. Undo or tidy up

```bash
dotconfig-hub rollback project      # Restore the project to a backup version
dotconfig-hub clean project         # Delete backup files in the project
dotconfig-hub clean hub             # Delete backup files in the hub
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

Set machine-wide defaults for templates source and environment sets (stored in `~/dotconfig-hub.yaml`). These are suggested during interactive `setup` prompts.

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
dotconfig-hub sync --all                      # Include init_only files too
```

For each differing file, the diff is shown followed by an interactive prompt (the file paths are repeated right above the prompt so long diffs never leave you guessing):

```
Select sync direction for:
Hub: ~/dotconfig-templates/my_project_init_template/.vscode/settings.json
Project: ~/workspace/your-project/.vscode/settings.json
Choose action:
  Update [P]roject (Hub → Project)
  Update [H]ub (Project → Hub)
  [S]kip this file
  [D]isplay full diff
  [C]hanges only (context diff)
Select [p/h/s/d/c] (s):
```

When a file exists on only one side, the `p`/`h` actions adapt: updating the side that has the file means **deleting** the surviving copy (with backup) so both sides match. For example, if the project-side file is missing:

```
  Update [H]ub (Project → Hub): delete Hub-side file (with backup)
```

The deleted file is renamed to `<name>.bak.<timestamp>`, never destroyed, and can be restored with `rollback`.

### `clean`

Delete the timestamped backup files (`<name>.bak.<YYYYMMDD_HHMMSS>`) that sync operations create. The hub and each project are cleaned independently: `project` targets the current directory, `hub` targets the templates source.

```bash
dotconfig-hub clean project             # Clean backups in the current project
dotconfig-hub clean hub                 # Clean backups in the hub
dotconfig-hub clean project --dry-run   # Preview deletions
dotconfig-hub clean project --yes       # Skip the confirmation prompt
```

Only files matching the dotconfig-hub backup naming convention are deleted; plain `.bak` files you created manually are left untouched.

### `rollback`

Restore files to a selected backup version. Like `clean`, it operates on one side at a time (`project` or `hub`).

```bash
dotconfig-hub rollback project                        # Pick a version interactively
dotconfig-hub rollback hub --version 20260612_153000  # Restore a specific version
dotconfig-hub rollback project --yes                  # Skip the confirmation prompt
```

Available versions are listed as a table (newest first) with their creation time and file count:

```
        Backup versions
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Version         ┃ Created             ┃ Files ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━┩
│ 20260612_153000 │ 2026-06-12 15:30:00 │     3 │
│ 20260601_120000 │ 2026-06-01 12:00:00 │     2 │
└─────────────────┴─────────────────────┴───────┘
```

Rolling back restores every file of the selected version to its original path — including files that were deleted with backup. The displaced current files are saved as a new backup version stamped with the rollback time, so a rollback can itself be undone. The selected backup files are kept, so the same version remains selectable later.

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

## Backups & Versions

Whenever sync overwrites or deletes a file, the previous content is preserved next to the original:

```
.vscode/settings.json                       # Current file
.vscode/settings.json.bak.20260612_153000   # Backup (version 20260612_153000)
```

Key properties:

- **One sync run = one version.** The timestamp suffix is fixed once per sync session, so every backup created in the same run shares the same suffix. Selecting a version in `rollback` restores a consistent snapshot of that run.
- **Backups never sync.** Files matching the backup naming convention are excluded from file discovery by default, so they don't propagate between hub and project.
- **Hub and project are independent.** Backups live on the side where the file was overwritten or deleted; `clean` and `rollback` therefore take an explicit `project` / `hub` target.
- **Nothing is silently destroyed.** Deletion during sync is a rename to a backup; rollback preserves the displaced files as a new version.

## Configuration

### Hub: `config.yaml`

Defines environment sets and their tools in the templates repository:

```yaml
# Global exclude patterns (optional, gitignore-style).
# Merged with the built-in defaults (.DS_Store), applied to every tool entry
# on both hub and project sides, regardless of entry order.
exclude:
  - Thumbs.db

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
- **Negation** — `"!pattern"` (excludes files matched by earlier entries of the same tool)
- **Dict** — `{ source: "file", init_only: true }` (synced only on first setup; never overwrites existing files)
- **Dict with rename** — `{ source: ".gitignore.hub", target: ".gitignore" }` (renamed during delivery; glob patterns not supported with rename)

Tool-level options:

- **`include_backup_files: true`** — Include `.bak` backup files in sync. By default, `.bak` files (including the timestamped backups dotconfig-hub creates, like `.bak.20260612_153000`) are excluded from file discovery. Set this to `true` on a tool if you need to sync `.bak` files explicitly.

Top-level options:

- **`exclude:`** — List of gitignore-style patterns excluded globally from file discovery. Patterns are merged with the built-in defaults (`.DS_Store`) and apply to every tool entry on both hub and project sides. A pattern without `/` matches the file name at any depth (e.g. `Thumbs.db`); a pattern containing `/` matches the path relative to the tool's `project_dir` (e.g. `build/*`). Use this for files that should never sync anywhere; use a `"!pattern"` entry inside a tool's `files` list only for entry-local, one-off exclusions.

### Project: `dotconfig-hub.yaml`

Created by `setup` and `init` in each project:

```yaml
templates_source: ~/dotconfig-templates
active_environment_sets:
  - my_project_init_template
```

### Global: `~/dotconfig-hub.yaml`

Machine-wide defaults managed by `global-config`. Used to pre-fill interactive `setup` prompts:

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
