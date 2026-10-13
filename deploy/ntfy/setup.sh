#!/usr/bin/env bash
# Create ntfy users, topic permissions, and a publisher token for rclone-sync-runner.
#
# Run on the host where the ntfy container runs. Safe to run more than once:
# existing users are kept, permissions are set again, and a new token is made
# only when the publisher has no token with the expected label.
#
# Settings (environment variables):
#   NTFY_CONTAINER   Container name                 (default: ntfy)
#   NTFY_TOPIC       Topic for run summaries        (default: rclone-sync)
#   READER_USER      Your user for apps and web UI  (default: ceshine)
#   PUBLISHER_USER   User for the runner            (default: rclone-runner)
#   TOKEN_LABEL      Label of the publisher token   (default: rclone-sync-runner)

set -euo pipefail

NTFY_CONTAINER="${NTFY_CONTAINER:-ntfy}"
NTFY_TOPIC="${NTFY_TOPIC:-rclone-sync}"
READER_USER="${READER_USER:-ceshine}"
PUBLISHER_USER="${PUBLISHER_USER:-rclone-runner}"
TOKEN_LABEL="${TOKEN_LABEL:-rclone-sync-runner}"

ntfy_exec() {
    docker exec "$NTFY_CONTAINER" ntfy "$@"
}

# `docker inspect` fails when the container does not exist; treat that as "not running".
running="$(docker inspect -f '{{.State.Running}}' "$NTFY_CONTAINER" 2>/dev/null || true)"
if [[ "$running" != "true" ]]; then
    echo "Error: container '$NTFY_CONTAINER' is not running. Start it with 'docker compose up -d'." >&2
    exit 1
fi

echo "==> Reader user '$READER_USER'"
# Capture the output first, so that `set -e` stops the script if ntfy fails.
user_list="$(ntfy_exec user list 2>&1)"
# Exact match on the name field (grep would read the name as a regex).
if awk -v u="$READER_USER" '$1 == "user" && $2 == u { found = 1 } END { exit !found }' <<<"$user_list"; then
    echo "User exists; skipping."
else
    # Interactive: ntfy asks for the password and a confirmation.
    docker exec -it "$NTFY_CONTAINER" ntfy user add "$READER_USER"
fi

echo "==> Publisher user '$PUBLISHER_USER'"
# Nobody logs in as the publisher, so use a random password. Pass it through the
# environment, not the command line, so it does not show in the process list.
publisher_password="$(head -c 32 /dev/urandom | base64 | tr -d '/+=' | head -c 32)"
NTFY_PASSWORD="$publisher_password" docker exec -e NTFY_PASSWORD "$NTFY_CONTAINER" \
    ntfy user add --ignore-exists "$PUBLISHER_USER"
unset publisher_password

echo "==> Permissions on topic '$NTFY_TOPIC'"
ntfy_exec access "$READER_USER" "$NTFY_TOPIC" read-only
ntfy_exec access "$PUBLISHER_USER" "$NTFY_TOPIC" write-only

echo "==> Publisher token (label '$TOKEN_LABEL')"
token_list="$(ntfy_exec token list "$PUBLISHER_USER" 2>&1)"
if grep -qF "($TOKEN_LABEL)" <<<"$token_list"; then
    echo "A token with this label exists; skipping. Show the full token with:"
    echo "  docker exec $NTFY_CONTAINER ntfy token list $PUBLISHER_USER"
else
    ntfy_exec token add --label="$TOKEN_LABEL" "$PUBLISHER_USER"
    echo "Put this token in the rclone-sync-runner config. Do not commit it."
fi
