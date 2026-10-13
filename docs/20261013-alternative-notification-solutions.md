# Alternative Notification Solutions

- Date: 2026-10-13
- Status: Decided: self-hosted ntfy on the GCP VM (see section 7)
- Scope: A new notifier for `rclone-sync-runner`, in addition to the Telegram notifier
- Writing style: Most of this document uses ASD-STE100 (Simplified Technical English)

## 1. Requirements

1. The notifier must send run summaries to a **Linux desktop** and to **Android** devices.
2. The solution must be **free**.
3. Self-hosting is permitted. A lightweight free GCP VM (e2-micro) is available.
4. Each client must show a **complete notification history** of at least the **past 2–3 days**. This includes clients that were offline for some time.

## 2. Summary

| Option | Hosting | Linux desktop | Android | History (≥ 2 days) | Effort |
|---|---|---|---|---|---|
| **ntfy (self-hosted)** | GCP VM | Web app (PWA) + CLI daemon | Official app | **Yes**, with `cache-duration` | Low |
| ntfy (ntfy.sh, hosted) | None | Web app + CLI daemon | Official app | **No**: 12-hour server cache | Very low |
| **Gotify** | GCP VM | `gotify-desktop` daemon + Web UI | Official app | **Yes**: server keeps all messages | Low, plus a cleanup job |
| Discord webhook | None | Native app | Native app | Yes: channel history | Very low |
| Matrix | matrix.org or GCP VM | Element / FluffyChat | Element / FluffyChat | Yes: room history | High |
| Pushover | None | Browser client | Native app | Yes | **Not free** |

**Decision:** Use **self-hosted ntfy** on the GCP VM. ntfy needs less maintenance for the history requirement. **Gotify** is the alternative: it is simpler and keeps all history by default, but it needs a cleanup job.

## 3. Options

### 3.1 ntfy

ntfy is an open-source push server. A publisher sends one HTTP POST to a "topic". All clients that subscribe to the topic get the message.

#### 3.1.1 Hosted on ntfy.sh

- The free tier allows **250 messages per day**. This limit is sufficient for a few sync runs each day.
- You do not need an account. The topic name works as a password. Use a long random topic name.
- The ntfy.sh operator can read the messages. Do not send sensitive data.
- The Google Play version of the Android app uses Firebase (FCM) for ntfy.sh topics. This gives the lowest battery use.
- **History:** The server cache keeps messages for **12 hours**. You cannot change this value. If a device is offline for more than 12 hours, it loses the messages from that time. A new device sees only the last 12 hours.

Result: ntfy.sh **does not meet** requirement 4. It is useful for a quick test.

#### 3.1.2 Self-hosted on the GCP VM

- The server is a single Go binary. It uses little memory and fits on an e2-micro VM.
- **Access control:** If you do not configure auth, all persons can read and write all topics. Set these values:

  ```yaml
  auth-file: "/var/lib/ntfy/user.db"
  auth-default-access: "deny-all"
  ```

  Then make a user and an access token (`ntfy user add`, `ntfy access`, `ntfy token add`). The publisher sends `Authorization: Bearer tk_...`. Note: a token currently gives full access to its user account. This includes the creation of more tokens. Use a dedicated user for the notifier. To revoke access after a token leak, delete the user, not only the token.

- **History:** Set a persistent cache and a longer cache time:

  ```yaml
  cache-file: "/var/cache/ntfy/cache.db"
  cache-duration: "168h"   # 7 days
  ```

  The default cache is **in memory** for 12 hours, and a restart deletes it. The server deletes messages older than `cache-duration` automatically.

- **Android:** A self-hosted server does not use Firebase. The app keeps a WebSocket connection open with a foreground service. The battery cost is small, but it is more than with FCM.
- **HTTPS:** Use a reverse proxy, for example Caddy, which gets a certificate automatically.

Result: Self-hosted ntfy **meets** all requirements.

#### 3.1.3 Client-side history

Clients also keep their own copy of messages:

| Client | Local storage | Default auto-delete |
|---|---|---|
| Android app | Local database | 1 month (configurable) |
| Web app | Browser IndexedDB | 1 week (configurable) |
| CLI (`ntfy subscribe`) | None | — |

A client that is always online keeps a full history in local storage. A client that was offline, or a new client, gets missed messages **only from the server cache**. For this reason, the server `cache-duration` is the important setting.

#### 3.1.4 Linux desktop

Two methods are available. You can use both at the same time.

1. **Pop-up notifications:** Run `ntfy subscribe --from-config` as a systemd **user** service. Set a `command` with `notify-send` in `~/.config/ntfy/client.yml`:

   ```yaml
   subscribe:
     - topic: rclone-sync
       command: notify-send "$t" "$m"
   ```

   ```bash
   systemctl --user enable --now ntfy-client
   ```

   Use the user service, not the system service. The system service runs as the `ntfy` user and cannot show notifications on your desktop. This method **keeps no history**.

2. **History:** Open the ntfy web app at the server URL. It shows the list of messages and gets missed messages from the server cache. You can install it as a PWA. For a one-time view in a terminal, use:

   ```bash
   ntfy subscribe --poll --since=48h rclone-sync
   ```

#### 3.1.5 Message features

- Title (`X-Title`), priority 1–5 (`X-Priority`), tags and emoji (`X-Tags`), click URL (`X-Click`).
- Markdown (`X-Markdown: true`). The Android app and the web app show Markdown. Without this header, ntfy shows plain text.
- The message body must be less than 4,096 bytes (4,095 bytes or less) and must be valid UTF-8. If the server has an `attachment-cache-dir`, ntfy sends a different body as an attachment. If not, the server rejects the message with HTTP 400 (`attachments not allowed`). The reference deployment has no `attachment-cache-dir`.
- Do **not** send the `Cache: no` header. That header removes the message from the server cache, so offline clients never get it.

### 3.2 Gotify

Gotify is a self-hosted push server. It is a small Go binary with a web UI. It uses an "inbox" model: the server keeps each message until a person or a client deletes it.

- **Android:** Official app (F-Droid and GitHub). The app keeps a WebSocket connection open.
- **Linux desktop:**
  - `gotify-desktop` (by desbma, Rust): a small daemon that sends messages to the desktop notification system. It is available in the AUR and nixpkgs, or you can build it with `cargo`.
  - The Gotify web UI shows the full message history.
- **iOS:** No app. This is not a requirement now.
- **Auth:** Required by default. Each publisher ("application") has its own token. This is safer than ntfy with no configuration.
- **Message features:** Title, priority, and Markdown. For Markdown, send JSON with `extras.client::display.contentType = "text/markdown"`. The web UI (v2.0.5+) and the Android app (v2.0.7+) show Markdown.
- **No hosted option, no Web Push, and no attachments.**

#### 3.2.1 History and retention

- Each client loads the history from the server. All clients see the same history, also after a long time offline. This meets requirement 4 with no configuration.
- **Gotify cannot delete old messages automatically.** There is no retention setting up to v3.1.1 (2026-09-15). The feature request [gotify/server#376](https://github.com/gotify/server/issues/376) is still open.
- The REST API cannot delete messages by age. It can delete one message (`DELETE /message/{id}`) or all messages of one application (`DELETE /application/{id}/message`).

#### 3.2.2 Cleanup workarounds

**Option A: SQL with a systemd timer (simplest)**

```bash
sqlite3 /var/lib/gotify/data/gotify.db \
  "DELETE FROM messages WHERE date < datetime('now', '-7 days');"
```

Run the command once a day. Make sure that the path is the same as the `database.connection` setting. Risk: this command depends on the internal database schema. After each Gotify upgrade, make sure that the command still works.

**Option B: A script that uses the REST API (safer across upgrades)**

1. Get the messages with `GET /message?limit=...`, page by page.
2. Compare the `date` field of each message with the limit.
3. Delete each old message with `DELETE /message/{id}`.

This script needs a **client** token, not an application token. A community script does this: [GAS85/Gotify-old_Notifications_cleanup](https://github.com/GAS85/Gotify-old_Notifications_cleanup). Read the script before you use it.

Note: one notification per sync run adds only a few MB per year to the database. The cleanup job mainly keeps the message list short. It is not necessary for disk space.

### 3.3 Discord webhook

- Make a private Discord server and a channel webhook. The notifier sends a JSON POST to the webhook URL.
- Discord has native Linux and Android apps. The channel keeps the full history.
- No server and no bot account are necessary.
- Disadvantages: Discord can read the messages. The Discord app is heavy if you use it only for alerts. This option works the same way as the current Telegram notifier, so it adds little new value.

### 3.4 Matrix

- Matrix is an open chat protocol. It is the closest open-source replacement for Telegram.
- Clients: Element or FluffyChat on Linux and Android. Rooms keep the full history.
- You can use a free matrix.org account for a bot, or self-host a homeserver (for example Tuwunel, the successor of conduwuit).
- Disadvantage: a self-hosted homeserver with Android push needs a push gateway or UnifiedPush. This is much more work than ntfy or Gotify.
- Use Matrix only if you want chat and alerts in one app.

### 3.5 Not recommended

- **Pushover:** Not free. It costs $5 one time per platform after a 30-day trial. Closed source.
- **Pushbullet:** The free tier has limits, and development is slow.

## 4. Alternative design: Apprise

Apprise is a Python library. It sends to more than 100 services with one URL format (`ntfy://`, `gotify://`, `matrix://`, `discord://`, ...).

- **Advantage:** One `AppriseNotifier` class and one config field can select any of these services.
- **Disadvantages:** A large dependency. Less control of the message format. It duplicates the current `TelegramNotifier`.

A dedicated notifier for the selected service is simpler and agrees with the current design.

## 5. GCP VM notes (self-hosted options)

- The free e2-micro instance is free only in `us-west1`, `us-central1`, and `us-east1`.
- Free egress is **1 GB per month** (North America to all destinations, but not China and Australia). Notifications and WebSocket keep-alive messages use much less than this.
- Make sure that the VM has a static IP address or a DNS name. Phones connect to this address continuously.
- Tailscale is an alternative to a public endpoint. But then each phone must keep Tailscale connected all the time.

## 6. Integration with `rclone-sync-runner`

- The `Notifier` protocol (`rclone_sync_runner/notifiers/base.py`) has one method: `on_run_finished(summary: RunSummary)`. Both ntfy and Gotify need only one HTTP POST in this method.
- `httpx` is already installed, because `python-telegram-bot` uses it. You can add it as a direct dependency for clarity.
- Copy the error policy of `TelegramNotifier`: log a warning when the send fails, and do not raise an error. A notification failure must not fail the sync run.
- ntfy: cut the message body to 4,095 bytes or less before the send. Cut at a UTF-8 character boundary, for example `body.encode()[:4095].decode("utf-8", "ignore")`. Without this, the server rejects a long run summary, and the notifier only logs a warning.
- Suggested config fields:
  - ntfy: `server_url`, `topic`, `token` (optional), `priority`, `markdown`, `timeout_seconds`.
  - Gotify: `server_url`, `app_token`, `priority`, `markdown`, `timeout_seconds`.
- Tests: mock the HTTP transport (for example `httpx.MockTransport`) and check the URL, the headers, and the body. For ntfy, also test that a long summary is cut to 4,095 bytes or less and is valid UTF-8. Include a multi-byte character at the cut position.

## 7. Next steps

1. ~~Select ntfy or Gotify for the GCP VM.~~ Decision: self-hosted ntfy.
2. Deploy the ntfy server with HTTPS, auth, `cache-file`, and `cache-duration`. A reference deployment is in [deploy/ntfy/](../deploy/ntfy/README.md).
3. Implement the ntfy notifier and its tests.

## 8. References

- ntfy docs: [Publishing](https://docs.ntfy.sh/publish/), [Subscribe via CLI](https://docs.ntfy.sh/subscribe/cli/), [Server config](https://docs.ntfy.sh/config/), [Message cache](https://docs.ntfy.sh/config/#message-cache), [Fetch cached messages](https://docs.ntfy.sh/subscribe/api/#fetch-cached-messages)
- [ntfy.sh pricing](https://ntfy.sh/#pricing)
- [ntfy-android `Repository.kt`](https://github.com/binwiederhier/ntfy-android/blob/main/app/src/main/java/io/heckel/ntfy/db/Repository.kt) (auto-delete default)
- [ntfy web app `Prefs.js`](https://github.com/binwiederhier/ntfy/blob/main/web/src/app/Prefs.js) (auto-delete default)
- [Gotify message extras](https://gotify.net/docs/msgextras)
- [gotify/server#376: Configurable retention period for messages](https://github.com/gotify/server/issues/376)
- [GAS85/Gotify-old_Notifications_cleanup](https://github.com/GAS85/Gotify-old_Notifications_cleanup)
- [gotify-desktop](https://github.com/desbma/gotify-desktop)
- [GCP free tier: Compute](https://cloud.google.com/free/docs/compute-getting-started)
- [Apprise on PyPI](https://pypi.org/project/apprise)
- [PushBits](https://github.com/pushbits/server)
