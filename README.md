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
- `compose.yml`: production-like stack.
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

The generated `.env` has only eight entries: the PostgreSQL password, four
GitHub App values, the recoverable local admin password plus its hash, and the
session-signing secret. Compose passes only the admin hash to the application.
Replace the two GitHub ID placeholders and add the downloaded private key before
starting the full stack.

Docker/code supply the current defaults: port `8000`, the single allowed DUT-AI
repository, secure cookies in production, the internal keyless llama.cpp URL
and model, and publication disabled. They may still be overridden explicitly
through Compose when deployment requirements change. Never give an LLM provider
credential to the terminal-capable Harness process.

## Docker development

Build the Linux development image and run all tests inside it:

```bash
docker build --target development -t dut-ai-pr-preview:dev .
docker run --rm dut-ai-pr-preview:dev python -m pytest -v
```

After GitHub App credentials are filled, start the reload-enabled stack:

```bash
docker compose -f compose.yml -f compose.dev.yml up --build
```

The admin UI is available at `http://127.0.0.1:8000`. Development overrides
the secure-cookie flag for local HTTP only.

## Docker deployment

On the Linux server, keep `.env` and `secrets/github-app.pem` outside source
control, terminate TLS in front of the loopback-bound service, then run:

```bash
docker compose build
docker compose up -d postgres web worker
docker compose ps
```

Publication is disabled by default even though it is no longer repeated in
`.env`. Set `PUBLISH_ENABLED=true` only for an explicitly selected preview after
checking the stored head SHA, then remove the override again.

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
