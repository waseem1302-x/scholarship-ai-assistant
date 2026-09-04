from scripts import staging_smoke


class _SmokeClient:
    next_index = 0

    def __init__(self, base_url: str) -> None:
        self.index = self.next_index
        type(self).next_index += 1

    def login(self, email: str, password: str) -> None:
        assert email and password

    def request(self, method, path, payload=None, expected=None):
        if path == "/health/ready":
            return 200, {"status": "ready"}
        if path == "/api/v1/opportunities?limit=1":
            return 200, {"items": [{"id": "opportunity-1"}]}
        if self.index == 0 and path == "/api/v1/applications":
            return 401, None
        if path in {"/api/v1/beta/policy", "/api/v1/profiles/me"}:
            return 200, {}
        if self.index == 1 and path == "/api/v1/applications?limit=1":
            return 200, {"items": [{"id": "application-1", "version": 1}]}
        if self.index == 2 and path.startswith("/api/v1/applications/application-1"):
            return 404, None
        raise AssertionError(f"Unexpected smoke request: {self.index=} {method=} {path=}")


def test_staging_smoke_reports_the_complete_six_boolean_success_contract(
    monkeypatch,
) -> None:
    _SmokeClient.next_index = 0
    monkeypatch.setattr(staging_smoke, "SmokeClient", _SmokeClient)
    for name in (
        "SMOKE_USER_A_EMAIL",
        "SMOKE_USER_A_PASSWORD",
        "SMOKE_USER_B_EMAIL",
        "SMOKE_USER_B_PASSWORD",
    ):
        monkeypatch.setenv(name, "protected-value")

    assert staging_smoke.run("https://staging.example") == {
        "status": "staging_smoke_passed",
        "database_ready": True,
        "redis_exercised_by_login_limit": True,
        "catalogue_contract": True,
        "anonymous_private_route_blocked": True,
        "authenticated_contract": True,
        "tenant_read_update_delete_attacks_blocked": True,
    }
