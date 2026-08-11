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


def test_frontend_keeps_tokens_out_of_local_storage_and_never_trusts_anchor_markup(client) -> None:
    javascript = client.get("/static/app.js").text

    assert "localStorage" not in javascript
    assert 'stringValue.includes("<a ")' not in javascript
    assert "data?.error?.message" in javascript
