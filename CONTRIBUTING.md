# Contributing to PageSeeds CLI

Thank you for your interest in contributing! This guide will help you get started.

## Development Setup

### Prerequisites

- Python 3.10 or higher
- [uv](https://docs.astral.sh/uv/) package manager
- Git

### Clone and Install

```bash
git clone <repo-url> pageseeds-cli
cd pageseeds-cli

# Install all packages in development mode
./scripts/install_uv_tools.sh
```

## Project Structure

```
pageseeds-cli/
├── packages/
│   ├── automation-cli/      # Repo management, Reddit, GSC tools
│   ├── seo-cli/             # Ahrefs SEO research
│   └── seo-content-cli/     # Content lifecycle management
├── dashboard_ptk/           # Interactive TUI dashboard
├── scripts/                 # Setup and utility scripts
├── examples/                # Example configuration files
└── .github/skills/          # Workflow knowledge base
```

## Development Workflow

### Running in Development Mode

Instead of installing packages, you can run them directly:

```bash
# SEO CLI
uv run --directory packages/seo-cli seo-cli --help

# Content CLI
uv run --directory packages/seo-content-cli seo-content-cli --help

# Automation CLI
uv run --directory packages/automation-cli automation-cli --help

# Dashboard
uv run --directory dashboard_ptk python -m dashboard
```

### Running Tests

```bash
cd dashboard_ptk
python tests/run_tests.py
```

Key tests that must pass:

| Test | Purpose |
|------|---------|
| `test_no_subprocess_outside_engine.py` | Ensures subprocess only in engine |
| `test_content_locator.py` | Content directory discovery |
| `test_frontmatter_dates.py` | Date handling safety |
| `test_project_preflight.py` | Project setup validation |

### Code Style

- **Python**: Follow PEP 8
- **Type hints**: Use them for new code
- **Docstrings**: Google style preferred
- **Line length**: 100 characters max

## Making Changes

### Adding a New CLI Command

1. Add command to the appropriate package in `packages/`
2. Update the package's README.md with usage examples
3. Register in `dashboard_ptk/dashboard/engine/tool_registry.py` if needed
4. Add tests

### Adding a New Workflow

1. Create workflow in `dashboard_ptk/dashboard/engine/workflows/`
2. Add normalizer in `dashboard_ptk/dashboard/engine/normalizers/` if needed
3. Update `dashboard_ptk/dashboard/engine/task_executor.py`
4. Add skill documentation in `.github/skills/`

### Changing Task Schema

1. Update schema version in `dashboard_ptk/dashboard/engine/task_store.py`
2. Add migration in `dashboard_ptk/dashboard/engine/migration.py`
3. Ensure backward compatibility
4. Add migration test

## Testing Guidelines

### Writing Tests

```python
# Example test structure
def test_my_feature():
    # Arrange
    input_data = {...}
    
    # Act
    result = my_function(input_data)
    
    # Assert
    assert result["status"] == "success"
```

### Integration Tests

Tests that call external services (Ahrefs, GSC, Reddit) should be marked:

```python
import pytest

@pytest.mark.integration
def test_ahrefs_api():
    # This test requires CAPSOLVER_API_KEY
    pass
```

Run integration tests separately:

```bash
pytest -m integration
```

## Submitting Changes

### Before Submitting

1. **Run all tests**
   ```bash
   cd dashboard_ptk && python tests/run_tests.py
   ```

2. **Check code style**
   ```bash
   ruff check packages/ dashboard_ptk/
   ```

3. **Type check** (optional but appreciated)
   ```bash
   mypy packages/automation-cli/src
   ```

4. **Update documentation**
   - README.md if user-facing changes
   - ARCHITECTURE.md if design changes
   - AGENTS.md if agent guidelines change

### Pull Request Process

1. Create a feature branch: `git checkout -b feature/my-feature`
2. Make your changes with clear commit messages
3. Add/update tests
4. Update documentation
5. Push and create a Pull Request

### PR Description Template

```markdown
## What changed
Brief description of changes

## Why
The problem being solved

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] Manual testing performed

## Documentation
- [ ] README updated (if user-facing)
- [ ] Architecture doc updated (if design changed)
```

## Architecture Principles

When contributing, keep these principles in mind:

1. **One execution path** - All workflows go through `dashboard/engine`
2. **CLI-first** - Deterministic steps use explicit CLI calls, not function calls
3. **Observable** - Agent outputs are always persisted to files
4. **Local secrets** - No API keys in repo files, use env vars or secrets.env
5. **Backward compatible** - Task state migrations preserve existing data

## Common Tasks

### Adding a New Dependency

```toml
# In the package's pyproject.toml
[project]
dependencies = [
    "existing-package~=1.2.0",
    "new-package~=2.0.0",  # Use ~= for compatible releases
]
```

Then update:
```bash
uv pip install -e packages/your-package
```

### Debugging the Dashboard

```bash
# Run with verbose logging
uv run --directory dashboard_ptk python -m dashboard --verbose

# Or add print statements (they appear in the terminal)
```

### Testing Against Real APIs

Create a `.env` file in the package directory:

```bash
CAPSOLVER_API_KEY=your-key-here
```

Then run:
```bash
uv run --directory packages/seo-cli seo-cli keyword-generator --keyword "test"
```

## Getting Help

- **Questions**: Open a Discussion on GitHub
- **Bugs**: Open an Issue with reproduction steps
- **Features**: Open a Discussion first to align on design

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
