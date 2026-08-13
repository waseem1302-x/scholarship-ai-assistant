from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.proxy_headers import AzureContainerAppsProxyHeadersMiddleware


def test_azure_container_apps_uses_rightmost_forwarded_client_and_proto() -> None:
    app = FastAPI()
    app.add_middleware(AzureContainerAppsProxyHeadersMiddleware)

    @app.get("/")
    def inspect_request(request: Request) -> dict[str, str]:
        assert request.client is not None
        return {"client": request.client.host, "scheme": request.url.scheme}

    response = TestClient(app).get(
        "/",
        headers={
            "X-Forwarded-For": "198.51.100.100, 203.0.113.42",
            "X-Forwarded-Proto": "https",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"client": "203.0.113.42", "scheme": "https"}
