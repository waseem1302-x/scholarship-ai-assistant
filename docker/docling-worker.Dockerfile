# Dedicated, offline document-conversion image. It contains no database or API
# credentials and is intended for a restricted-egress one-shot worker.
FROM python:3.12-slim-bookworm@sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    DOCLING_ARTIFACTS_PATH=/opt/docling/models

WORKDIR /app

RUN addgroup --system docling && adduser --system --ingroup docling docling

COPY pyproject.toml uv.lock README.md ./
COPY app ./app
COPY scripts/verify_docling_artifacts.py ./scripts/verify_docling_artifacts.py
COPY docker/docling-artifacts.lock.json ./docker/docling-artifacts.lock.json

RUN python -m pip install --no-cache-dir uv==0.11.33 \
    && UV_PROJECT_ENVIRONMENT=/opt/venv uv sync --frozen --no-dev --extra document-conversion \
    && /opt/venv/bin/docling-tools models download layout tableformer rapidocr --output-dir /opt/docling/models --quiet \
    && /opt/venv/bin/python scripts/verify_docling_artifacts.py --model-dir /opt/docling/models --lock docker/docling-artifacts.lock.json \
    && chown -R docling:docling /app /opt/docling /opt/venv

USER docling
ENTRYPOINT ["/opt/venv/bin/python", "-m", "app.modules.catalogue_ingestion.document_conversion_worker"]
