# runpad

A self-hosted web app for running predefined actions from buttons. Think OliveTin's "safe buttons for shell commands" crossed with Home Assistant's dashboards and device state, but highly opinionated: one way to do each thing, configured in the UI, backed by Postgres.

Two ways to get a button:

1. **Feature catalog.** Pick a feature from a curated list (for example "Docker container control"), fill in a short form, and runpad creates the buttons and state tiles for you.
2. **Custom button.** Define any command yourself. This is the escape hatch, and it is a first-class path, not a hack.

## Product principles

- **Opinionated over configurable.** If there are two reasonable ways to do something, pick one and remove the other. Do not add settings to avoid making a decision.
- **No YAML.** All configuration lives in Postgres and is edited in the UI. The only file-based config is environment variables for deployment.
- **Features are curated, in-repo code.** No plugin marketplace, no third-party integration loader. A new feature is a pull request.
- **Postgres is the only dependency.** No Redis, no message broker, no separate worker container.
- **Two containers, one compose file.** `app` and `db`. A fresh `docker compose up` must produce a working instance.
- **Safe by default.** Running commands from a browser is dangerous. See "Security rules" below; they are not optional.

## Vocabulary

Use these terms consistently in code, API, and UI.

| Term | Meaning |
|---|---|
| **Pad** | A page of buttons and tiles. A user can have several pads. |
| **Button** | A tile on a pad that triggers an Action. |
| **Tile** | A read-only tile on a pad that shows State (for example "container: running"). |
| **Action** | The thing that executes: an executor, a target, a command template, and typed arguments. Buttons point at Actions. |
| **Feature** | A catalog entry, defined in code, that bundles a config form, one or more Action templates, and optional State polling. |
| **Feature instance** | A Feature the user has enabled and configured. Owns the Buttons, Tiles, and Actions it generated. |
| **Target** | Where an Action runs: an SSH host, an HTTP endpoint, or the app container itself. |
| **Run** | One execution of an Action: who triggered it, when, exit code, duration, captured output. |
| **State** | A current value reported by a Feature instance (up/down, running/stopped, a number). |

## Stack

**Backend**
- Python 3.13+, FastAPI, Pydantic v2
- SQLAlchemy 2.x (async) with psycopg 3, Alembic for migrations
- asyncssh for SSH execution, httpx2 (the maintained successor to httpx) for HTTP execution
- `uv` for dependency management, `ruff` for lint and format, `pytest` for tests

**Frontend**
- React, TypeScript, Vite
- TanStack Query for server state, Tailwind for styling
- API types generated from the backend's OpenAPI schema (`openapi-typescript`); never hand-write API types

**Runtime**
- Postgres 17
- One app image: the Vite build is copied into the image and served by FastAPI as static files. No separate frontend container, no nginx.
- Multi-arch image (`linux/amd64`, `linux/arm64`), published as `davidhfrankelcodes/runpad`

## Repository layout

```
runpad/
├── CLAUDE.md
├── compose.yaml            # production-style: app + db
├── compose.dev.yaml        # dev overrides: bind mounts, reload, exposed db port
├── Dockerfile              # multi-stage: frontend build -> python runtime
├── .env.example
├── backend/
│   ├── pyproject.toml
│   ├── alembic/
│   ├── app/
│   │   ├── main.py         # app factory, static file mount, lifespan
│   │   ├── config.py       # env-based settings (pydantic-settings)
│   │   ├── db.py
│   │   ├── models/         # SQLAlchemy models
│   │   ├── schemas/        # Pydantic request/response models
│   │   ├── api/            # routers, one module per resource
│   │   ├── executors/      # ssh.py, http.py, local.py
│   │   ├── features/       # one module per catalog feature
│   │   ├── runner.py       # run lifecycle, timeouts, output capture
│   │   ├── poller.py       # State polling loop
│   │   └── security.py     # auth, sessions, secret encryption
│   └── tests/
├── frontend/
│   ├── package.json
│   └── src/
└── scripts/                # bash helpers; every dev command runs through these
```

## Commands

Docker is the only host requirement. Python, uv, Node, and npm run in containers; never install them on the host. Every dev command goes through `scripts/`.

```bash
scripts/init-env.sh                  # create .env with generated secrets (first time only)
docker compose up -d                 # production-style: app + db on :8080

scripts/dev.sh                       # dev stack: backend reload on :8080, Vite on :5173, db on 127.0.0.1:5432
scripts/check.sh                     # everything that must pass before a task is done
scripts/test.sh [pytest args]        # backend tests against the compose db
scripts/migration.sh "describe change"   # alembic revision --autogenerate
scripts/gen-api.sh                   # regenerate frontend/src/api/schema.ts from OpenAPI
scripts/icons.sh                     # render favicons, app icons, social preview from frontend/icons/*.svg
scripts/release.sh                   # push davidhfrankelcodes/runpad:<version> + :latest (amd64, arm64), tag v<version>

# Anything else runs in the tools container, from backend/, frontend/, or the repo root:
scripts/tools.sh backend uv add <package>
scripts/tools.sh frontend npm install <package>
```

`compose.dev.yaml` adds the `web` (Vite) and `tools` services; `tools` is built from the `tools` stage of the Dockerfile and is never part of the published image.

Before calling any task done: `scripts/check.sh` passes (ruff, pytest, eslint, frontend build).

Releasing: bump `version` in `backend/pyproject.toml` and `frontend/package.json` in a commit on a clean `main`, then run `scripts/release.sh`. It refuses to overwrite a version already on Docker Hub, runs `check.sh`, builds both platforms with `docker buildx` (arm64 through QEMU on an amd64 host), verifies the pushed manifest, and tags the commit.

## Compose contract

`compose.yaml` must stay this simple. Do not add services.

```yaml
services:
  app:
    image: davidhfrankelcodes/runpad:latest
    build: .
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

- The app container runs `alembic upgrade head` on start, then launches uvicorn.
- `GET /healthz` returns 200 only when the database is reachable.
- All deployment config is environment variables, documented in `.env.example`.
- The Docker socket is never mounted into the app container.

## Architecture

### Execution

- An Action has exactly one **executor**: `ssh`, `http`, or `local`.
  - `ssh`: run a command on a Target host using a stored key.
  - `http`: send a request to a URL (webhooks, device APIs).
  - `local`: run inside the app container. Useful for tests and simple scripts; it cannot touch the host.
- Targets have kind `ssh` (host, port, username, an `ssh_key` secret, pinned host key) or `http` (base URL, optional bearer-token secret). `local` Actions need no Target.
- Secrets have kind `ssh_key` (generated in runpad or imported; passphrase-protected keys are rejected) or `text`. A secret used by a Target cannot be deleted.
- Host-level features (Docker, systemd, power) always go through an `ssh` Target, including for the machine runpad itself runs on.
- Runs execute in-process as asyncio tasks managed by `runner.py`. There is no job queue.
- `local` and `ssh` Actions run an admin-written script with `sh -c`. Typed arguments arrive as `$ARG_<NAME>` and as `$1..$n` (definition order), never interpolated into the script. Text secrets can be exposed as named env vars and are redacted from output.
- `ssh` Runs send one fixed command line (`executors/ssh.py: REMOTE_WRAPPER`); arguments, secret variables, and the script travel on stdin, so none of them appear in the remote process list. The wrapper runs the script in its own session and keeps stdin open as a lifeline: closing it (cancel, timeout, dropped connection) kills the remote process group, and leftovers are killed when the script exits. Remote hosts need POSIX `sh` and `head -c`; `setsid` is used when present.
- `http` Actions send one request to the Target: method, a path relative to the base URL, and an optional JSON body. `{name}` placeholders are filled from typed arguments: percent-encoded in the path, substituted into the parsed JSON (never into raw text). Exit code is 0 for 2xx, otherwise the HTTP status. Redirects are not followed.
- `local` Runs get a minimal environment (never the app's own), a private temporary working directory, and their own process group, killed in full on finish, cancel, or timeout. `tini` is PID 1 in the image so orphans are reaped.
- Every Action has a mandatory timeout (default 30s) and a concurrency policy: `reject` (default; a new Run is refused while one is in progress) or `allow`.
- Output (stdout and stderr merged) is captured, capped at 512 KiB, and stored on the Run row. Live output streams to the browser over Server-Sent Events. A Run ends as `succeeded`, `failed`, `timed_out`, `cancelled`, or `interrupted`.
- On startup, any Run still marked `running` is set to `interrupted`.

### Features

Each feature is one module in `backend/app/features/` exposing a manifest:

- `id`, `name`, `description`, `icon`, `category`
- `ConfigModel`: a Pydantic model; the UI renders the setup form from its JSON schema
- `build(config)`: returns the Actions, Buttons, and Tiles to create
- `poll(config)` (optional): returns current State; called on an interval by `poller.py`

Rules:
- Features are registered explicitly in `features/__init__.py`. No dynamic discovery, no entry points.
- Enabling a feature creates a Feature instance; deleting the instance deletes everything it generated.
- Objects generated by a feature are marked as managed. Users can move, rename, and hide them, but not edit their command.
- A feature never needs its own table. Config is JSONB on `feature_instances`, validated by `ConfigModel`.

How it fits together (`features/base.py`, `feature_instances.py`):
- `build(config)` returns `ActionTemplate`s, each with a stable `key` and an optional `ButtonTemplate`. They become ordinary Actions with `feature_instance_id` and `feature_key` set; there is no separate execution path.
- Config values reach scripts through `ScriptSpec.env` (fixed environment variables), never interpolated into the script text. Validate them tightly in `ConfigModel` anyway (for example, a regex for container names).
- A config field typed `SshTargetId` or `HttpTargetId` renders as a target picker, and the server checks the Target exists and has that kind.
- Managed Actions cannot be edited or deleted through the actions API (409). Their Buttons can be relabeled, recolored, moved between pads, or removed like any other.
- Changing an instance's config rebuilds its Actions in place, matched by `key`, so Buttons and Run history stay attached. Button labels that still match the previously generated label are updated; labels the admin changed are kept.
- Descriptions are shown to members on pads: describe the effect in words ("Stops the plex container."), not the command.
- `build()` returns a `Build`: Action templates plus `TileTemplate`s (a State key and a label). Tiles go on the chosen pad next to the buttons.

State polling (`poller.py`):
- A feature's `poll` is a `Poll(probe, parse, interval_seconds=30)`. `probe(config)` returns a read-only command (executor, target, spec); `parse(config, ProbeResult)` turns its exit code and output, or its connection error, into `StateValue`s. Test `parse` against real command output, including failures.
- Probes use the same target resolution and executors as Runs. The latest result lives on the `states` row (value, tone, detail, `checked_at`, `changed_at`). A probe is recorded as a Run (attributed to `system`, no `action_id`, named "Check <instance>") only when it changes a State's value or tone; detail-only changes such as ping latency are not recorded. Recording every probe would bury real button presses in the run history.
- Instances are polled right after they are created or reconfigured, and right after a Run of one of their Actions finishes, so a pressed button updates its tile immediately. A config change clears the instance's States.
- State changes and Run starts and finishes are published on an in-process `EventBus` and streamed at `GET /api/v1/events`. The stream starts with a `ready` event once subscribed; clients refetch then, since earlier changes were not sent. Members only receive States of tiles on pads they can see, and their own Runs. Slow subscribers are dropped; the browser reconnects (and gets `ready` again).
- The events stream never ends on its own, so uvicorn runs with `--timeout-graceful-shutdown 5`.

Starter catalog for v1:

| Feature | Executor | Buttons | State | Needs on the host |
|---|---|---|---|---|
| Docker container | ssh | start, stop, restart | running / stopped / not found | `docker` without sudo |
| Docker Compose stack | ssh | start (up), stop (down), update (pull and up) | services up, e.g. 2/3 up | `docker compose` without sudo |
| systemd service | ssh | start, stop, restart | active / inactive / failed | root or passwordless `sudo` |
| Host power | ssh | reboot, shut down | reachable / unreachable, uptime | systemd; root or passwordless `sudo` |
| Wake-on-LAN | ssh | wake | none | `python3`, on the sleeping machine's network |
| Webhook | http | send | none | |
| Ping check | local | none | up / down, latency | (runs `ping` in the runpad container) |

Commands that need root use `features.base.AS_ROOT`: directly as root, otherwise `sudo -n`. Host power schedules the reboot through `systemd-run` a few seconds out, so the Run reports success before the connection drops and the reboot is outside the Run's process group.

### Themes

Each user picks a theme.park theme on their Account page (`users.theme`, e.g. `theme-options/nord`; `PUT /api/v1/auth/theme`). The browser loads `{RUNPAD_THEMEPARK_URL}/css/{theme}.css` after runpad's own CSS, and lists themes from `{RUNPAD_THEMEPARK_URL}/themes.json`. `RUNPAD_THEMEPARK_URL` defaults to `https://theme-park.dev` and can point at a self-hosted theme.park. The choice is remembered in the browser (`frontend/src/theme.ts`), so the login screen uses it too.

### Custom buttons

A custom button is an Action the user writes by hand: executor, target, command, optional arguments. It uses exactly the same Action, Run, and executor code as feature-generated buttons. There is no second code path.

### Data model

Tables: `users`, `sessions`, `targets`, `secrets`, `pads`, `buttons`, `tiles`, `actions`, `feature_instances`, `states`, `runs`.

- UUID primary keys, `created_at` and `updated_at` on every table, timestamps stored in UTC.
- `runs` is append-only and doubles as the audit log.
- Every schema change goes through an Alembic migration. Never call `create_all` outside tests.

### API

- REST under `/api/v1`, one router per resource, Pydantic models in and out.
- `POST /api/v1/actions/{id}/run` starts a Run and returns it immediately.
- `GET /api/v1/runs/{id}/stream` streams output (SSE).
- `GET /api/v1/events` streams State changes and Run status changes (SSE).
- The frontend only talks to `/api/v1`. No server-rendered pages.

### Auth

- Local accounts with username and password (argon2), server-side sessions in Postgres, HTTP-only cookies.
- Two roles: `admin` (configure everything) and `member` (press buttons on pads they can see).
- A pad lists the members who can see it; admins see every pad. A member can run an Action only if it is behind a button on a pad they can see, and pad responses never include an Action's command or secret mappings.
- First run shows a one-time setup screen that creates the admin.
- Session cookies hold a random token; only its SHA-256 hash is stored. Sessions slide to 30 days from last use.
- Unsafe requests to `/api/` must send `X-Requested-With: runpad` (CSRF guard); the frontend client adds it.
- Users are deactivated, never deleted, so Runs keep their attribution. There is always at least one active admin.
- Failed logins are rate limited in Postgres (`login_limits.py`, table `login_failures`): 10 per client IP and 50 per username in 15 minutes, then 429 with `Retry-After`. The client IP comes from uvicorn, which trusts `X-Forwarded-For` only from `FORWARDED_ALLOW_IPS` (set from `RUNPAD_TRUSTED_PROXIES` in compose).

## Security rules

These are hard requirements. Do not relax them to make a feature easier.

1. **Never build a shell string from user input.** Arguments are typed (string with regex, integer with range, enum, boolean), validated server-side, and passed as argv elements or environment variables. If a command template needs shell features, the arguments still arrive as quoted positional parameters, never interpolated text.
2. **Secrets are encrypted at rest** with a key derived from `RUNPAD_SECRET_KEY`. They are never returned by the API after creation, never logged, and are redacted from Run output.
3. **Every Run is attributed** to a user (or to `system` for polling) and recorded.
4. **Authorization is checked on the server** for every endpoint. The UI hiding a button is not access control.
5. **Destructive actions require confirmation**, set per Action (`confirm: true`). Reboot and shut down default to on.
6. **SSH host keys are pinned** when a Target is created. A changed host key fails the Run; it is never auto-accepted.
7. **No arbitrary command endpoint.** The API can run a stored Action by ID. It cannot run a command supplied in the request.

## Conventions

- Backend: full type hints, async all the way down, no blocking calls in request handlers. Business logic lives outside routers.
- Frontend: function components, no `any`, server state in TanStack Query, no global state library unless a real need appears.
- The UI works at phone width (390 px): no page may scroll sideways; wide tables scroll inside their own `overflow-x-auto` box. Below `md` the header becomes a Menu button. The app is installable (`frontend/public/manifest.webmanifest`, icons in `frontend/public/`).
- The UI documents itself. Every control whose effect is not obvious from its label gets a `tooltip` (on `Button` and `Badge`, or the `Tooltip` component): what it does, and what it keeps or removes for destructive actions. Status badges and colored indicators explain their meaning. Tooltips show on hover and keyboard focus and are the control's accessible description; keep them to one or two short sentences, and keep the facts in them true to the backend.
- Frontend colors come from [theme.park](https://theme-park.dev) variables, through the Tailwind tokens in `frontend/src/index.css` (`bg-card`, `bg-input`, `bg-raised`, `text-fg`, `text-muted`, `text-faint`, `border-line`, `bg-button`, `text-accent`, `text-link`, ...). Never use fixed colors like `zinc-*` for UI chrome, or a theme will miss it; light themes exist. Fixed colors are only for meaning: per-button colors (with `text-white`), run and state status colors, and the run output terminal. `--main-bg-color` may be a gradient, so it is only used as `background`.
- Tests: backend tests run against a real Postgres (the compose `db` service, in a separate `runpad_test` database), not SQLite. Every executor and every feature's `build()` has tests. Executors are tested against fakes, never real hosts.
- Scripts in `scripts/` are bash, use functions, `set -euo pipefail`, and print explicit numbered steps (`[1/4] Building frontend...`).
- Commits are small and imperative ("Add systemd service feature").
- Do not add a dependency without saying why in the PR or commit message.

## Adding a feature (checklist)

1. Create `backend/app/features/<feature_id>.py` with the manifest, `ConfigModel`, and `build()`.
2. Add `poll()` if the feature reports State.
3. Register it in `features/__init__.py`.
4. Add tests for `build()` output and, if present, `poll()` parsing.
5. Add an icon (`frontend/src/components/FeatureIcon.tsx`) and confirm the generated setup form reads well in the UI.
6. Add a row to the catalog table in this file.

## Build order

1. Skeleton: compose, Dockerfile, FastAPI app, `/healthz`, Alembic, empty React shell served by the backend.
2. Auth and first-run setup.
3. Targets and secrets.
4. Actions, the `local` executor, Runs, and SSE output streaming.
5. Pads and custom buttons (end to end: create a button, press it, watch output).
6. `ssh` and `http` executors.
7. Feature framework plus the first feature (Docker container).
8. State polling, Tiles, and the events stream.
9. Remaining starter catalog.
10. Multi-arch build and release script.

## Out of scope for v1

- Automations (trigger and condition rules), schedules, and scenes
- Plugin or third-party integration loading
- YAML or file-based import and export
- Device discovery
- Mobile apps, voice assistants
- SSO / OIDC
- Multi-tenant use

Do not start on any of these without being asked.
