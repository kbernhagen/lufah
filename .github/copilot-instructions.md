# Lufah Copilot Instructions

**lufah** is a Python CLI utility for controlling Folding@Home v8 clients remotely via WebSocket.

## Architecture Overview

- **CLI Layer** ([cli_typer.py](../src/lufah/cli_typer.py)): Typer-based command dispatcher. Commands map to functions in `commands/core/` that receive `argparse.Namespace` with populated clients.
- **FahClient** ([fahclient.py](../src/lufah/fahclient.py)): Manages WebSocket connection to a single FAH client. Handles async message processing, state updates, and command dispatch.
- **Updatable** ([updatable.py](../src/lufah/updatable.py)): Dict subclass representing client state. Supports atomic updates via `do_update()` for efficient state merging (backward-compat for 8.1-8.3).
- **Commands** ([commands/core/](../src/lufah/commands/core/)): Stateless async functions taking `args.clients` list (populated by CLI validation layer).

## Key Patterns

### Multi-Client Async Pattern
Commands operate on multiple clients simultaneously:
```python
await asyncio.gather(*[c.connect() for c in args.clients])
for client in args.clients:
    await client.send_command(command)  # or custom logic
```
See [finish_fold_pause.py](../src/lufah/commands/core/finish_fold_pause.py) for canonical pattern.

### Address/Group Parsing
Input format: `[host][:port][/group]` or comma-separated hosts. Validation in [validate.py](../src/lufah/validate.py):
- Single host: `/group` suffix is optional, extracts via [split_address_and_group()](../src/lufah/util.py)
- Multi-host (comma-separated): No group suffix allowed
- Default: `localhost:7396`

### State Access
Client state accessed via `client.data` (Updatable dict):
- JSON structure mirrors FAH Web Control API
- Use `.get(key, default)` for safe access; supports dot-notation in `do_get` command
- Version-specific handling: check `client.version` tuple (e.g., `< (8, 2)` for peers fallback)

### Constants
[const.py](../src/lufah/const.py): FAH config keys, group/global distinction, version-specific differences.
- `GLOBAL_CONFIG_KEYS`: User/team/passkey (8.3+)
- `GROUP_CONFIG_KEYS`: CPU/GPU/idle behavior per group
- `READ_ONLY_*`: Prevent external modification (paused, gpus, finish)

## Developer Workflows

### Build & Test
```bash
make lint        # ruff + pylint
make test        # pytest -vv
make build       # clean lint test + package
make install-user  # via pipx (local user)
```

### Environment
Uses `uv` (UV package manager) for dependency management. Setup:
```bash
make setup       # uv sync --frozen (dev deps)
make sync-no-dev # minimal runtime
```

### Adding Commands
1. Create `commands/core/new_cmd.py` with async function `async def do_new_cmd(args):`
2. Import in [cli_typer.py](../src/lufah/cli_typer.py), add callback + help text
3. Add to `COMMANDS_ORDER` list for help ordering
4. Test via `make test` and `lufah new-cmd -h`

## Integration Points

- **WebSocket**: [websockets](https://github.com/python-websockets/websockets) library for async I/O
- **CLI Framework**: Typer (slim) for argument parsing; uses argparse under the hood
- **Logging**: [logger.py](../src/lufah/logger.py) provides module-level logger
- **Exception Handling**: Custom hierarchy in [exceptions.py](../src/lufah/exceptions.py) (FahClientError, FahClientNotConnected, etc.)

## Common Patterns to Avoid

- **Don't** mutate `args.clients` list—it's pre-populated by validation
- **Don't** assume version < 8.3 structure—check `client.version`; use Updatable's compat_mode as fallback
- **Don't** block on sync I/O in commands—use async/await throughout
- **Don't** hardcode localhost:7396—always use validated address input

## Testing
Test file: [tests/test_updatable.py](../tests/test_updatable.py). Run with `make test`. For CLI testing, use mock client data in [data/](../data/) directory (lufahwatch3.jsonl historical snapshots).
