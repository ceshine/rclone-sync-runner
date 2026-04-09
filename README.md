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
jobs:
  - name: photos
    source: /data/photos
    destination: remote:photos
    extra_args:
      - --delete-during
  - name: docs
    source: /data/docs
    destination: remote:docs
notifications:
  telegram:
    bot_token: "123456789:replace_with_real_token"
    chat_id: "-1001234567890"
    # Optional for Telegram topics:
    # message_thread_id: 42
    disable_notification: false
```

Refer to [configs/example.yml](configs/example.yml) for a more complete example.

## Run

```bash
uv run rclone-sync-runner run --config configs/sync.yaml
```

Preview without making remote changes:

```bash
uv run rclone-sync-runner run --config configs/sync.yaml --dry-run
```

`--dry-run` (or `-n`) must be set at the CLI level and is rejected in per-job `extra_args`.

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
