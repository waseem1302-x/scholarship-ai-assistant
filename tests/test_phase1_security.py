from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_production_rejects_development_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="APP_JWT_SECRET"):
        Settings(env="production", jwt_secret="local-development-secret-change-me-now")


def test_primary_response_has_browser_security_headers(client) -> None:
    response = client.get("/")

    assert response.headers["content-security-policy"].startswith("default-src 'self'")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_phase_three_client_keeps_access_tokens_in_memory_and_uses_csrf_protection() -> None:
    javascript = (Path("frontend/src/api/client.ts")).read_text(encoding="utf-8")

    assert "localStorage" not in javascript
    assert "sessionStorage" not in javascript
    assert 'credentials: "same-origin"' in javascript
    assert '"X-CSRF-Token"' in javascript
