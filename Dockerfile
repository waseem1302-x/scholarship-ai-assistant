# node:24-bookworm-slim, resolved 2026-08-14. Renovate this digest deliberately.
FROM node:24-bookworm-slim@sha256:3638d9a6fe4030bd716be989438248074489337ba3275657f93595428be4fc03 AS frontend-build

WORKDIR /frontend

COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile

COPY frontend ./
RUN CI=true pnpm build


# python:3.12-slim-bookworm, resolved 2026-08-14. Renovate this digest deliberately.
FROM python:3.12-slim-bookworm@sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY requirements.lock ./
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements.lock

COPY app ./app
COPY --from=frontend-build /app/web/frontend-dist ./app/web/frontend-dist
COPY data ./data
COPY alembic.ini ./
COPY alembic ./alembic

USER app
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


# Opt-in catalogue worker. Crawlee is installed from the frozen project lock
# only in this target; the API/default image keeps the smaller core runtime.
FROM runtime AS catalogue-worker

USER root
COPY pyproject.toml uv.lock README.md ./
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN --mount=type=cache,target=/root/.cache/uv \
    python -m pip install --no-cache-dir uv==0.11.33 \
    && UV_PROJECT_ENVIRONMENT=/opt/catalogue-venv uv sync --frozen --extra dev --extra crawlee \
    && /opt/catalogue-venv/bin/python -m playwright install --with-deps chromium \
    && chown -R app:app /opt/catalogue-venv /ms-playwright

ENV PATH="/opt/catalogue-venv/bin:$PATH"
USER app


# Keep the normal API runtime as the implicit target for `docker build .` and
# existing Compose services.
FROM runtime AS final
