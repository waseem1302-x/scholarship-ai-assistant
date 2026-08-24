# Dedicated, offline document-conversion image. It contains no database or API
# credentials and is intended for a restricted-egress one-shot worker.
FROM python:3.12-slim-bookworm@sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134 AS docling_artifacts

# Keep the reviewed model bundle in its own build layer so it can be verified
# independently of Python dependency installation.
COPY .docling-models /opt/docling/models


FROM python:3.12-slim-bookworm@sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    DOCLING_ARTIFACTS_PATH=/opt/docling/models

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends --yes \
        libgl1 \
        libglib2.0-0 \
        libxcb1 \
        libxext6 \
        libxrender1 \
    && rm -rf /var/lib/apt/lists/*

RUN addgroup --system docling && adduser --system --ingroup docling docling

COPY pyproject.toml uv.lock README.md ./
COPY app ./app
COPY scripts/verify_docling_artifacts.py ./scripts/verify_docling_artifacts.py
COPY docker/docling-artifacts.lock.json ./docker/docling-artifacts.lock.json
# The reviewed bundle is supplied with the build context and checked against
# the lock below.  The restricted worker never downloads model artifacts at
# build or runtime, which keeps the resulting conversion reproducible.
COPY --from=docling_artifacts /opt/docling/models /opt/docling/models

RUN --mount=type=cache,target=/root/.cache/uv \
    python -m pip install --no-cache-dir uv==0.11.33 \
    && UV_PROJECT_ENVIRONMENT=/opt/venv uv sync --frozen --no-dev --extra document-conversion \
    && /opt/venv/bin/python scripts/verify_docling_artifacts.py --model-dir /opt/docling/models --lock docker/docling-artifacts.lock.json \
    && chown -R docling:docling /app /opt/docling /opt/venv

USER docling
ENTRYPOINT ["/opt/venv/bin/python", "-m", "app.modules.catalogue_ingestion.document_conversion_worker"]
