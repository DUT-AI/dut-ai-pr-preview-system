# DUT AI PR Preview System

Private GitHub App for reviewing pull requests in
`DUT-AI/dut-ai-pr-preview-system`. The hosted application is owned by DUT AI;
the review engine is adapted from Nexpeak's MIT-licensed
[`deepseek-harness-pr-review`](https://github.com/nexpeakcore/deepseek-harness-pr-review).

The default policy is preview-only: a worker stores the review result and
comment preview in PostgreSQL, while publication requires an authenticated
admin action and `PUBLISH_ENABLED=true`.

## Runtime layout

```text
GitHub webhook -> FastAPI app -> PostgreSQL job -> worker
                                              -> src/engine
                                              -> Harness + LLM
                                              -> persisted preview
```

- `app/server/controller.py`: FastAPI routes for login, UI, webhook, and API.
- `app/server/services.py`: webhook, review-job, and publication use cases.
- `app/server/repositories.py`: PostgreSQL persistence and GitHub App API client.
- `app/server/config.py`, `models.py`, `schema.sql`: shared server configuration,
  data objects, and one database schema.
- `app/ui/`: Jinja templates and CSS; `app/worker.py`: background job loop.
- `src/engine/`: secret-isolated subprocess gateway and engine runner.
- `src/claims.py`, `src/verify.py`, `src/synthesize.py`: adapted upstream review
  logic used by the engine.
- `docker-compose.yml`: production-like stack.
- `compose.dev.yml`: development image, source mounts, and FastAPI reload.

The removed legacy `web/` dashboard is not part of this architecture; `app/`
is the only web application.

## GitHub App credentials

Create one private GitHub App owned by `DUT-AI`, install it only on this
repository, and configure:

- repository permissions: Metadata read, Contents read, Pull requests read/write,
  Issues read/write;
- webhook event: Pull request;
- webhook secret: use the generated `GITHUB_WEBHOOK_SECRET` from `.env`;
- webhook URL: `https://<server>/webhooks/github`;
- webhook URL for the current development tunnel:
  `https://fairinsight.luongduytoan.io.vn/webhooks/github`. Change it in the
  GitHub App settings when the production domain is ready;
- private key: download it to `secrets/github-app.pem`;
- `GITHUB_APP_ID`: the App ID shown in the app settings;
- `GITHUB_INSTALLATION_ID`: the numeric ID in the installation URL.

Do not use a personal access token. Do not commit `.env`, the PEM file, or any
installation token.

## Local secrets

Generate the ignored `.env` file without printing secrets:

```bash
python scripts/init_env.py
```

If `.env` already exists, expand it to the current full layout while preserving
its existing credentials:

```bash
python scripts/init_env.py --update
```

The file is split into Docker, PostgreSQL, Web UI/API, admin session, GitHub App,
LLM, and review-policy sections. It includes both sides of every published port:

| Setting | Default | Meaning |
|---|---:|---|
| `POSTGRES_EXTERNAL_PORT` | `5433` | PostgreSQL port on the Docker host |
| `POSTGRES_INTERNAL_PORT` | `5432` | PostgreSQL port inside the Compose network |
| `WEB_EXTERNAL_PORT` | `8000` | admin UI/API port on the Docker host |
| `WEB_INTERNAL_PORT` | `8000` | FastAPI port inside the web container |

PostgreSQL is reachable from the host at
`POSTGRES_BIND_HOST:POSTGRES_EXTERNAL_PORT`; web and worker use
`POSTGRES_HOST:POSTGRES_INTERNAL_PORT`. Both services receive a `DATABASE_URL`
built by Compose from the explicit database name, user, password, host, and
internal port. Use a URL-safe PostgreSQL password.

Both database and web ports use the numeric loopback bind `127.0.0.1` required
by Docker and are accessed through `localhost`. This publishes the ports without
exposing them to the public network. Only change a bind address to `0.0.0.0`
after adding the required firewall, authentication, and TLS controls.

The project does not use a standalone admin `JWT_SECRET`. Admin login and CSRF
use signed cookies backed by `SESSION_SECRET`; GitHub App JWTs are generated from
`GITHUB_APP_ID` and the PEM mounted from `GITHUB_PRIVATE_KEY_FILE` on the host to
`GITHUB_PRIVATE_KEY_PATH` inside the containers. Compose never passes the local
plaintext `ADMIN_PASSWORD` to the application.

Replace the two GitHub ID placeholders and add the downloaded private key before
starting the full stack. Keep `PUBLISH_ENABLED=false` until a stored preview is
explicitly approved. Never give an LLM provider credential to the
terminal-capable Harness process.

Changing a published port and recreating a container does not remove data.
Changing `POSTGRES_DB`, `POSTGRES_USER`, or `POSTGRES_PASSWORD` does not rewrite
an already initialized PostgreSQL volume; migrate the database credential inside
PostgreSQL or provision a deliberate new volume instead of deleting production
data.

## Docker development

Build the Linux development image and run all tests inside it:

```bash
docker build --target development -t dut-ai-pr-preview:dev .
docker run --rm dut-ai-pr-preview:dev python -m pytest -v
```

After GitHub App credentials are filled, start the reload-enabled stack:

```bash
docker compose -f docker-compose.yml -f compose.dev.yml up --build
```

With the defaults, the admin UI is available at `http://localhost:8000`.
Use `WEB_BIND_HOST` and `WEB_EXTERNAL_PORT` from `.env` when either value is
changed. Development overrides the secure-cookie flag for local HTTP only.

## Docker deployment

On the Linux server, keep `.env` and `secrets/github-app.pem` outside source
control, terminate TLS in front of the loopback-bound service, then run:

```bash
docker compose build
docker compose up -d postgres web worker
docker compose ps
```

Because the main file now uses the conventional `docker-compose.yml` name, the
production commands do not need a `-f` argument. The GitHub App webhook URL is
managed in GitHub and remains `https://<domain>/webhooks/github`; update it after
the final server domain and reverse proxy are ready.

Publication is disabled by `PUBLISH_ENABLED=false` in `.env`. Set it to `true`
only for an explicitly selected preview after checking the stored head SHA, then
disable it again.

## Static validation

```bash
python -m compileall src app
git diff --check
```

## CLI compatibility

The engine-origin CLI remains available as `dut-ai-pr-review`; the upstream
`harness-pr-review` name remains an alias so existing automation does not
break. The hosted app does not use the removed local dashboard command.

## License and attribution

This project is based on
[`deepseek-harness-pr-review`](https://github.com/nexpeakcore/deepseek-harness-pr-review)
by Nexpeak and is distributed under the [MIT License](LICENSE). The original
copyright and permission notice are preserved. DUT AI Club maintains the
hosted application and project-specific changes.
