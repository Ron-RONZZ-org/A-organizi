# Dev commands for A-organizi

```bash
# Install in dev mode
uv pip install -e .

# Run tests
uv run pytest tests/ -v

# Run linting
uv run ruff check src/
uv run ruff format --check src/

# Run a specific CLI command
A organizi --help
A organizi okazajo --help
A organizi okazajo aldoni --help
```
