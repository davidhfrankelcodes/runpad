# runpad

A self-hosted web app for running predefined actions from buttons. Put "restart Plex", "reboot the NAS", or "deploy" on a pad, see live status next to the buttons, and let family or teammates press them without giving them a shell.

- **Feature catalog.** Pick a feature (for example *Docker container*), fill in a short form, and runpad creates the buttons and status tiles.
- **Custom buttons.** Write your own command, with typed arguments, for anything the catalog doesn't cover.
- **Configured in the UI.** No YAML. Everything lives in Postgres.
- **Two containers.** The app and Postgres. Nothing else to run.

## Quick start

Save this as `compose.yaml`:

```yaml
services:
  app:
    image: davidhfrankelcodes/runpad:latest
    ports:
      - "8080:8080"
    environment:
      DATABASE_URL: postgresql+psycopg://runpad:${POSTGRES_PASSWORD}@db:5432/runpad
      RUNPAD_SECRET_KEY: ${RUNPAD_SECRET_KEY}
      RUNPAD_THEMEPARK_URL: ${RUNPAD_THEMEPARK_URL:-https://theme-park.dev}
      FORWARDED_ALLOW_IPS: ${RUNPAD_TRUSTED_PROXIES:-127.0.0.1}
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped

  db:
    image: postgres:17
    environment:
      POSTGRES_USER: runpad
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: runpad
    volumes:
      - runpad-db:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U runpad -d runpad"]
      interval: 5s
      timeout: 3s
      retries: 10
    restart: unless-stopped

volumes:
  runpad-db:
```

Create a `.env` next to it with two generated secrets, then start it:

```bash
printf 'POSTGRES_PASSWORD=%s\nRUNPAD_SECRET_KEY=%s\n' "$(openssl rand -hex 24)" "$(openssl rand -hex 32)" > .env
docker compose up -d
```

Open http://localhost:8080 and create the admin account on the setup screen.

Keep `RUNPAD_SECRET_KEY` safe. It encrypts stored SSH keys and tokens, and losing or changing it makes them unreadable.

Images are published for `linux/amd64` and `linux/arm64`.

## Getting started

1. **Secrets:** generate an SSH key in runpad (or import one) and add its public key to `~/.ssh/authorized_keys` on each host runpad should control.
2. **Targets:** add each host as an SSH target. runpad shows the host's key fingerprint for you to confirm, then pins it. HTTP endpoints (webhooks, device APIs) are HTTP targets, with an optional bearer token.
3. **Pads:** create a pad, a page of buttons and tiles.
4. **Features:** add features from the catalog, or write custom buttons in the pad editor.
5. **Users:** add members and choose which pads each one can see. Members can only press buttons on their pads; admins configure everything.

To control the machine runpad runs on, add it as an SSH target too. The Docker socket is never mounted into the app container.

### On your phone

runpad works at phone width, and can be added to your home screen to open like an app: in Chrome or Edge on Android, menu → *Install app*; in Safari on iOS, Share → *Add to Home Screen*.

## Feature catalog

| Feature | Buttons | Status tile | Needs on the host |
|---|---|---|---|
| Docker container | start, stop, restart | running / stopped / not found | `docker` without sudo (e.g. in the `docker` group) |
| Docker Compose stack | start, stop, update (pull and recreate) | services up, e.g. 2/3 up | `docker compose` without sudo |
| systemd service | start, stop, restart | active / inactive / failed | root, or passwordless `sudo` |
| Host power | reboot, shut down | reachable / unreachable, uptime | systemd; root, or passwordless `sudo` |
| Wake-on-LAN | wake | none | `python3`, on the sleeping machine's network |
| Webhook | send | none | an HTTP target |
| Ping check | none | up / down, latency | nothing (pings from the runpad container) |

Status tiles update every 30 seconds, and right after one of the feature's buttons runs.

## Custom buttons

A custom button runs a script with `sh` on an SSH host or inside the runpad container, or sends an HTTP request. Arguments are typed: text that must match a pattern, a whole number in a range, a choice from a list, or yes/no. They are validated on the server and reach the script as `$ARG_<NAME>` and `$1`, `$2`, …, never pasted into the script text. Text secrets can be exposed to the script as environment variables and are redacted from the output.

Every action has a timeout, and can be set to ask for confirmation before it runs.

## Themes

runpad is styled with [theme.park](https://theme-park.dev) variables. Each user picks any theme.park theme, or the community themes, on their Account page; the choice applies to them only.

Themes load from `https://theme-park.dev` by default. To use a [self-hosted theme.park](https://docs.theme-park.dev/setup/#docker) instead, set `RUNPAD_THEMEPARK_URL` in `.env`, for example `RUNPAD_THEMEPARK_URL=http://themepark.lan:8080`.

## Security

- Secrets are encrypted at rest and never returned by the API after they are saved.
- SSH host keys are pinned when a target is created; a changed key fails the run.
- The API can only run stored actions. There is no endpoint for running arbitrary commands.
- Password guessing is rate limited per client IP and per username.
- Every run is recorded with who started it, its output, and its exit code. Status changes found by polling are recorded as runs by `system`.
- Members never see the commands behind their buttons.

## Configuration

Deployment settings are the two environment variables above, plus two optional ones:

- `RUNPAD_THEMEPARK_URL`: where themes load from (see [Themes](#themes)).
- `RUNPAD_TRUSTED_PROXIES`: behind a reverse proxy, set this to the proxy's IP address so runpad sees real client addresses. Login rate limiting counts failures per client IP; without this, every client appears as the proxy.

Failed logins are logged as `Failed login for user '<name>' from <ip>`, for tools like fail2ban. After 10 failures from one IP, or 50 for one username, within 15 minutes, logins are refused until older failures expire. Everything else (users, targets, secrets, pads, buttons) is configured in the UI.

`GET /healthz` returns 200 when the database is reachable. The API is under `/api/v1`, with interactive docs at `/api/v1/docs`.

## Development

Docker is the only requirement; Python, Node, and their tools run in containers.

```bash
scripts/init-env.sh     # create .env (first time only)
scripts/dev.sh          # backend with reload on :8080, Vite on :5173, Postgres on 127.0.0.1:5432
scripts/check.sh        # ruff, pytest, eslint, and the frontend build
scripts/test.sh -k ssh  # backend tests, with pytest arguments
```

See [CLAUDE.md](CLAUDE.md) for the architecture, conventions, and the checklist for adding a feature.

To release, bump the version in `backend/pyproject.toml` and `frontend/package.json`, commit on a clean `main`, and run `scripts/release.sh`. It builds both platforms, pushes `davidhfrankelcodes/runpad:<version>` and `:latest`, and tags the commit.

## License

[MIT](LICENSE). Themes are by [theme.park](https://github.com/themepark-dev/theme.park), also MIT.

