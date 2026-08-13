from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.feature_gates import FeatureGateMiddleware


def gated_client(**changes: object) -> TestClient:
    settings = Settings(
        env="development",
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret="feature-gate-test-secret-at-least-32-characters",
        **changes,
    )
    app = FastAPI()
    app.add_middleware(FeatureGateMiddleware, settings=settings)

    @app.get("/api/v1/document-lab/policy")
    @app.get("/api/v1/document-lab/export")
    @app.delete("/api/v1/document-lab/data")
    @app.post("/api/v1/assistant/answers")
    @app.post("/api/v1/document-lab/assets")
    @app.post("/api/v1/community/posts")
    @app.get("/api/v1/community/export")
    @app.delete("/api/v1/community/data")
    @app.patch("/api/v1/profiles/me")
    @app.post("/api/v1/saved-opportunities")
    @app.delete("/api/v1/auth/account")
    @app.get("/api/v1/saved-opportunities")
    def protected() -> dict[str, bool]:
        return {"reached": True}

    return TestClient(app)


def test_disabled_feature_gates_block_high_risk_routes_and_preserve_data_rights() -> None:
    client = gated_client(
        assistant_enabled=False,
        document_lab_enabled=False,
        community_enabled=False,
    )

    assert (
        client.post("/api/v1/assistant/answers").json()["error"]["code"] == "assistant_unavailable"
    )
    assert (
        client.post("/api/v1/document-lab/assets").json()["error"]["code"]
        == "document_lab_unavailable"
    )
    assert client.post("/api/v1/community/posts").json()["error"]["code"] == "community_unavailable"
    assert client.get("/api/v1/document-lab/policy").json() == {"reached": True}
    assert client.get("/api/v1/document-lab/export").json() == {"reached": True}
    assert client.delete("/api/v1/document-lab/data").json() == {"reached": True}
    assert client.get("/api/v1/community/export").json() == {"reached": True}
    assert client.delete("/api/v1/community/data").json() == {"reached": True}


def test_maintenance_mode_blocks_all_mutating_routes_by_default() -> None:
    client = gated_client(catalogue_maintenance_mode=True)

    responses = [
        client.patch("/api/v1/profiles/me"),
        client.post("/api/v1/saved-opportunities"),
        client.delete("/api/v1/auth/account"),
    ]

    assert all(response.status_code == 503 for response in responses)
    assert all(response.json()["error"]["code"] == "maintenance_mode" for response in responses)
    assert client.get("/api/v1/saved-opportunities").json() == {"reached": True}
