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
COPY app ./app
COPY --from=frontend-build /app/web/frontend-dist ./app/web/frontend-dist
COPY data ./data
COPY alembic.ini ./
COPY alembic ./alembic

RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements.lock

USER app
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
