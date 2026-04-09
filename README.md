# rclone-sync-runner

Run sequential `rclone sync` jobs from a YAML config file.

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- [rclone](https://rclone.org/)

## Install

Install locally:

```bash
uv sync --frozen
```

or the following to make the `rclone-sync-runner` available system-wide:

```bash
uv tool install .
```

## Configuration

This project uses YAML config files to define sync jobs:

```yaml
version: 1
global:
  rclone_bin: rclone
  log_level: INFO
  continue_on_error: true
  # extra_args applied to every job unless a job overrides them:
  extra_args:
    - --fast-list
jobs:
  - name: photos
    source: /data/photos
    destination: remote:photos
    # Overrides global extra_args for this job:
    extra_args:
      - --delete-during
  - name: docs
    source: /data/docs
    destination: remote:docs
    # Omit extra_args (or set to null) to inherit global extra_args.
    # Set extra_args: [] to explicitly suppress global extra_args.
notifications:
  telegram:
    bot_token: "123456789:replace_with_real_token"
    chat_id: "-1001234567890"
    # Optional for Telegram topics:
    # message_thread_id: 42
    disable_notification: false
```

Refer to [configs/example.yml](configs/example.yml) for a more complete example.

## Folder Discovery

The `discovery` command helps bootstrap a sync config by finding matching folder
pairs across two rclone remotes. It lists the immediate children of `FOLDER_A`
and searches `FOLDER_B` recursively (up to `--max-depth`) for subdirectories
with the same name.

```bash
uv run rclone-sync-runner discovery FOLDER_A FOLDER_B
```

Example — match top-level folders in a local path against a cloud remote:

```bash
uv run rclone-sync-runner discovery /data/photos gdrive:Backups --max-depth 2 --output draft.yaml
```

For each folder found in `FOLDER_A`:

- **MATCH** — exactly one matching name found in `FOLDER_B`; a sync job is emitted.
- **SKIP (no match)** — no folder with that name exists anywhere in `FOLDER_B`.
- **SKIP (ambiguous)** — two or more folders with that name were found; review manually.

The generated `draft.yaml` is a valid (but incomplete) `RunnerConfig` that you
can edit before using with `rclone-sync-runner run`.

Options:

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--max-depth` | `-d` | `3` | Maximum search depth inside `FOLDER_B` |
| `--output` | `-o` | `draft.yaml` | Output path for the generated YAML config |
| `--rclone-bin` | | `rclone` | Path or name of the rclone binary |

## Running Sync Jobs

The `run` command executes all sync jobs defined in a YAML config file sequentially.

```bash
uv run rclone-sync-runner run --config configs/sync.yaml
```

Preview without making remote changes:

```bash
uv run rclone-sync-runner run --config configs/sync.yaml --dry-run
```

Options:

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--config` | `-c` | *(required)* | Path to the YAML config file |
| `--dry-run` | `-n` | `false` | Pass `--dry-run` to rclone without writing any changes |
| `--progress` | `-p` | `false` | Print live stats updates (speed, ETA, transfer progress) during each job |

`--dry-run` must be set at the CLI level and is rejected in both `global.extra_args` and per-job `extra_args`.

The CLI prints a summary table and exits with:

- `0` when all jobs succeed
- `1` when one or more jobs fail
- `2` for config/runtime errors

## Notification Channels

### Telegram

If `notifications.telegram` is configured, the runner posts a run summary message to the configured Telegram chat when execution finishes.

To discover the correct Telegram chat ID for your bot, run:

```bash
uv run python scripts/telegram_get_chat_id.py --config configs/sync.yaml
```

This helper reads `notifications.telegram` from the config and prints sender info, chat ID, and timestamp for the latest message sent to the bot. Because it validates with `RunnerConfig`, `notifications.telegram.chat_id` must exist in the config (a temporary dummy value is fine).

## Development

```bash
uvx ruff check .
uvx ruff format --line-length 120
uv run pytest
```

## Acknowledgments

- The [AGENTS.md](./AGENTS.md) was adapted from the example in this blog post: [Getting Good Results from Claude Code](https://www.dzombak.com/blog/2025/08/getting-good-results-from-claude-code/).

## License

MIT License. See [LICENSE](LICENSE) for details.
