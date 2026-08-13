from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.core.config import Settings
from app.core.feature_gates import FeatureGateMiddleware
from app.core.http_security import SecurityHeadersMiddleware
from app.core.middleware import configure_http_middleware
from app.core.observability import ObservabilityMiddleware
from app.core.proxy_headers import AzureContainerAppsProxyHeadersMiddleware
from app.core.rate_limit import AuthRateLimitMiddleware


def settings(**changes: object) -> Settings:
    return Settings(
        env="development",
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret="middleware-composition-test-secret-at-least-32",
        **changes,
    )


def middleware_classes(application: FastAPI) -> list[type]:
    return [item.cls for item in application.user_middleware]


def test_default_http_middleware_order_is_explicit() -> None:
    application = FastAPI()

    configure_http_middleware(application, settings())

    assert middleware_classes(application) == [
        SecurityHeadersMiddleware,
        ObservabilityMiddleware,
        AuthRateLimitMiddleware,
        FeatureGateMiddleware,
        CORSMiddleware,
    ]


def test_security_headers_apply_to_http_responses() -> None:
    application = FastAPI()
    configure_http_middleware(application, settings())

    @application.get("/probe")
    def probe() -> dict[str, bool]:
        return {"ok": True}

    response = TestClient(application).get("/probe")

    assert response.headers["content-security-policy"].startswith("default-src 'self'")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["x-frame-options"] == "DENY"


def test_explicit_proxy_is_the_outermost_http_middleware() -> None:
    application = FastAPI()

    configure_http_middleware(application, settings(trusted_proxy_ips="10.0.0.1"))

    assert middleware_classes(application)[0] is ProxyHeadersMiddleware


def test_azure_proxy_is_the_outermost_http_middleware() -> None:
    application = FastAPI()

    configure_http_middleware(
        application,
        settings(trusted_proxy_mode="azure-container-apps"),
    )

    assert middleware_classes(application)[0] is AzureContainerAppsProxyHeadersMiddleware
