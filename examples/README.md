# PageSeeds Configuration Examples

This directory contains example configuration files for setting up PageSeeds CLI.

## Files

### `projects.json`

Defines the websites you want to manage with PageSeeds.

**Location:** `~/.config/automation/projects.json`

Each project needs:
- `name` - Display name for the project
- `path` - Absolute path to the repository
- `content_dir` - Relative path to your markdown content (optional, auto-detected if not specified)

### `manifest.json`

Per-project configuration for Google Search Console integration.

**Location:** `{target_repo}/.github/automation/manifest.json`

Used by:
- `pageseeds automation seo gsc-indexing-report`
- `pageseeds automation seo gsc-page-context`

### `secrets.env`

API keys and credentials.

**Location:** `~/.config/automation/secrets.env`

**Never commit this file to version control!**

## Quick Setup

1. Copy `secrets.env` and fill in your API keys:
   ```bash
   mkdir -p ~/.config/automation
   cp examples/secrets.env ~/.config/automation/secrets.env
   # Edit with your keys
   ```

2. Copy and customize `projects.json`:
   ```bash
   cp examples/projects.json ~/.config/automation/projects.json
   # Edit with your project paths
   ```

3. For each project, bootstrap the automation workspace:
   ```bash
   pageseeds automation repo init --to /path/to/your/project
   ```

4. (Optional) Add GSC manifest to projects using Google Search Console:
   ```bash
   cp examples/manifest.json /path/to/your/project/.github/automation/
   # Edit with your site details
   ```
