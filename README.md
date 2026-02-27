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
```

Refer to [configs/example.yml](configs/example.yml) for a more complete example.

## Run

```bash
uv run rclone-sync-runner run --config configs/sync.yaml
```

The CLI prints a summary table and exits with:

- `0` when all jobs succeed
- `1` when one or more jobs fail
- `2` for config/runtime errors

## Development

```bash
uvx ruff check .
uvx ruff format --line-length 120
uv run pytest
```
