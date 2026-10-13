# ntfy Server Deployment

This directory contains a reference deployment of a self-hosted [ntfy](https://ntfy.sh) server. The server sends `rclone-sync-runner` run summaries to Android devices and to the Linux desktop.

For the compared options and the reasons for this choice, see [docs/20261013-alternative-notification-solutions.md](../../docs/20261013-alternative-notification-solutions.md).

## Files

| File | Purpose |
|---|---|
| `docker-compose.yml` | The ntfy service, with Caddy labels for HTTPS |
| `setup.sh` | Makes the users, the topic permissions, and the publisher token |

## Configuration

| Setting | Value | Reason |
|---|---|---|
| `NTFY_CACHE_DURATION` | `168h` | Clients get missed messages for 7 days |
| `NTFY_CACHE_FILE` | `/var/cache/ntfy/cache.db` | The message history stays after a restart |
| `NTFY_AUTH_DEFAULT_ACCESS` | `deny-all` | Anonymous users cannot read or write |
| `NTFY_BEHIND_PROXY` | `true` | ntfy gets the client IP from the proxy headers, for rate limits. With the Cloudflare proxy, this is a Cloudflare IP (see [Operations](#operations)) |
| `NTFY_ENABLE_LOGIN` | `true` | The web app shows a login form |
| `mem_limit` | `64m` | Protects the other services on the e2-micro VM. ntfy uses about 20 MB |
| `GOMEMLIMIT` | `48MiB` | The Go garbage collector frees memory before the container reaches `mem_limit` |

Access rules that `setup.sh` makes:

| User | Topic `rclone-sync` | Used by |
|---|---|---|
| `ceshine` | read-only | Android app, web app, desktop CLI |
| `rclone-runner` | write-only | `rclone-sync-runner` (with an access token) |

If the publisher token leaks, a person can send messages with it, but cannot read the history.

## Prerequisites

- A host with Docker and Docker Compose.
- [caddy-docker-proxy](https://github.com/lucaslorentz/caddy-docker-proxy) runs on the host and uses the external `caddy` network.
- A DNS record for `ntfy.ceshine.net` that points to the host. Use the same settings as the records for the other services.

## Deployment

1. Copy the files to the host:

   ```bash
   ssh ceshine@gcpfree mkdir -p ntfy
   scp deploy/ntfy/docker-compose.yml deploy/ntfy/setup.sh ceshine@gcpfree:ntfy/
   ```

2. On the host, start the server:

   ```bash
   cd ~/ntfy
   docker compose up -d
   ```

   Caddy reads the labels and gets the TLS certificate automatically.

3. On the host, run the setup script:

   ```bash
   ./setup.sh
   ```

   The script asks for the password of the reader user. Then it prints the publisher token (`tk_...`). Keep the token in a password manager, and put it in the `rclone-sync-runner` config when the ntfy notifier is available. Do not commit the token.

   You can run the script again. It does not change existing users, and it does not make a second token. To change the names, set environment variables, for example `NTFY_TOPIC=backups ./setup.sh`. See the header of `setup.sh` for all variables.

4. Send a test message:

   ```bash
   curl -H "Authorization: Bearer tk_..." -H "Title: Test" -d "Hello" https://ntfy.ceshine.net/rclone-sync
   ```

## Clients

**Android:**
1. Install the ntfy app (Google Play or F-Droid).
2. In Settings, add the user for `https://ntfy.ceshine.net`.
3. Subscribe to `rclone-sync` on `https://ntfy.ceshine.net`.

The app keeps a WebSocket connection open with a foreground service. It keeps received messages for 1 month by default.

**Linux desktop, history:** Open `https://ntfy.ceshine.net`, log in, and subscribe to `rclone-sync`. You can install the web app as a PWA.

**Linux desktop, pop-up notifications:** Install the ntfy CLI. Make a token for the reader user, so that the config file does not contain your password:

```bash
docker exec ntfy ntfy token add --label=desktop ceshine
```

Then add this to `~/.config/ntfy/client.yml`, and run `chmod 600 ~/.config/ntfy/client.yml`:

```yaml
default-host: https://ntfy.ceshine.net
default-token: tk_...
subscribe:
  - topic: rclone-sync
    command: notify-send "$t" "$m"
```

Then start the user service:

```bash
systemctl --user enable --now ntfy-client
```

Use the user service, not the system service. The system service cannot show notifications on your desktop.

## Operations

- **Upgrade:** Change the image tag in `docker-compose.yml`, then run `docker compose up -d`. Do not use `latest`.
- **Backup:** Back up the `ntfy_lib` volume. It contains the users and the tokens. The `ntfy_cache` volume contains only temporary messages. Stop the server during the backup, so that the database copy is complete:

  ```bash
  docker compose stop
  docker run --rm -v ntfy_lib:/data:ro -v "$PWD":/backup alpine tar czf /backup/ntfy_lib.tar.gz -C /data .
  docker compose start
  ```

- **Reset the reader password:** `docker exec -it ntfy ntfy user change-pass ceshine`.
- **Show tokens:** `docker exec ntfy ntfy token list rclone-runner`. This command shows the full token.
- **Revoke the publisher access:** A token can make more tokens for its user. Thus, if a token leaks, removing only that token is not sufficient. Delete the user, then run `./setup.sh` again. The script makes the user, the permissions, and a new token again:

  ```bash
  docker exec ntfy ntfy user del rclone-runner
  ./setup.sh
  ```

- **Cloudflare proxy:** Cloudflare closes idle connections after about 100 seconds. ntfy sends a keep-alive message every 45 seconds by default, so the connections stay open. If delivery is not reliable, set the DNS record to "DNS only".
- **Client IPs with the Cloudflare proxy:** Caddy does not trust the `X-Forwarded-For` header from Cloudflare. Thus ntfy sees Cloudflare IPs as client IPs, and the rate limits apply to these IPs. For one user, this is not a problem. If you need the real IPs, add `NTFY_PROXY_FORWARDED_HEADER: CF-Connecting-IP` to the compose file.
