"""Bounded, redaction-safe product smoke for a zero-traffic staging candidate."""

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from typing import Any


class SmokeClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.cookies = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))
        self.access_token: str | None = None

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        expected: set[int] | None = None,
    ) -> tuple[int, Any]:
        headers = {"Accept": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if method not in {"GET", "HEAD"}:
            csrf = next(
                (cookie.value for cookie in self.cookies if cookie.name == "csrf_token"), None
            )
            if csrf:
                headers["X-CSRF-Token"] = urllib.parse.unquote(csrf)
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode() if payload is not None else None,
            headers=headers,
            method=method,
        )
        try:
            with self.opener.open(request, timeout=15) as response:
                status = response.status
                raw = response.read()
        except urllib.error.HTTPError as error:
            status = error.code
            raw = error.read()
        allowed = expected or {200}
        if status not in allowed:
            raise RuntimeError(f"Smoke request {method} {path} returned unexpected status {status}")
        return status, json.loads(raw) if raw else None

    def login(self, email: str, password: str) -> None:
        _, body = self.request("POST", "/api/v1/auth/login", {"email": email, "password": password})
        self.access_token = body["access_token"]


def require_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Protected staging smoke value {name} is required")
    return value


def run(base_url: str) -> dict[str, object]:
    anonymous = SmokeClient(base_url)
    _, ready = anonymous.request("GET", "/health/ready")
    if ready != {"status": "ready"}:
        raise RuntimeError("Readiness response contract failed")
    _, catalogue = anonymous.request("GET", "/api/v1/opportunities?limit=1")
    if not isinstance(catalogue.get("items"), list):
        raise RuntimeError("Catalogue response contract failed")
    anonymous.request("GET", "/api/v1/applications", expected={401})

    user_a = SmokeClient(base_url)
    user_b = SmokeClient(base_url)
    user_a.login(
        require_environment("SMOKE_USER_A_EMAIL"),
        require_environment("SMOKE_USER_A_PASSWORD"),
    )
    user_b.login(
        require_environment("SMOKE_USER_B_EMAIL"),
        require_environment("SMOKE_USER_B_PASSWORD"),
    )
    user_a.request("GET", "/api/v1/beta/policy")
    user_a.request("GET", "/api/v1/profiles/me")

    _, applications = user_a.request("GET", "/api/v1/applications?limit=1")
    created = False
    if applications["items"]:
        application = applications["items"][0]
    else:
        if not catalogue["items"]:
            raise RuntimeError("Staging smoke requires one reviewed public opportunity")
        _, application = user_a.request(
            "POST",
            "/api/v1/applications",
            {"opportunity_id": catalogue["items"][0]["id"]},
            expected={201},
        )
        created = True
    application_id = application["id"]
    user_b.request("GET", f"/api/v1/applications/{application_id}", expected={404})
    user_b.request(
        "PATCH",
        f"/api/v1/applications/{application_id}",
        {"notes": "cross-tenant attack", "expected_version": application["version"]},
        expected={404},
    )
    user_b.request("DELETE", f"/api/v1/applications/{application_id}", expected={404})
    if created:
        user_a.request("DELETE", f"/api/v1/applications/{application_id}", expected={204})
    return {
        "status": "staging_smoke_passed",
        "database_ready": True,
        "redis_exercised_by_login_limit": True,
        "catalogue_contract": True,
        "anonymous_private_route_blocked": True,
        "authenticated_contract": True,
        "tenant_read_update_delete_attacks_blocked": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.base_url), sort_keys=True))


if __name__ == "__main__":
    main()
