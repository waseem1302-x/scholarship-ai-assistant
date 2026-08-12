import re
from pathlib import Path

from fastapi.testclient import TestClient


def frontend_asset_path(html: str, extension: str) -> str:
    match = re.search(rf'(?:src|href)="(/assets/[^\"]+\.{extension})"', html)
    assert match is not None
    return match.group(1)


def test_react_frontend_is_served_at_the_canonical_root(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert '<div id="root"></div>' in response.text
    assert "Scholarship AI Assistant" in response.text

    bundle = client.get(frontend_asset_path(response.text, "js"))
    stylesheet = client.get(frontend_asset_path(response.text, "css"))

    assert bundle.status_code == 200
    assert stylesheet.status_code == 200
    assert "Make your next scholarship decision with confidence." in bundle.text
    assert "input:focus" in stylesheet.text
    assert "textarea:focus" in stylesheet.text


def test_react_routes_use_the_same_frontend_shell(client: TestClient) -> None:
    root = client.get("/")
    for path in (
        "/auth",
        "/auth/password-reset",
        "/verify-email",
        "/catalogue",
        "/catalogue/example-id",
        "/dashboard",
        "/admin",
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert response.text == root.text


def test_legacy_app_paths_redirect_to_the_canonical_routes(client: TestClient) -> None:
    response = client.get("/app/catalogue?country=Malaysia", follow_redirects=False)

    assert response.status_code == 308
    assert response.headers["location"] == "/catalogue?country=Malaysia"


def test_frontend_html_has_no_encoding_artifacts(client: TestClient) -> None:
    html = client.get("/").text

    assert "\u00c3\u201a" not in html
    assert "T\u00c3\u0192" not in html


def test_primary_frontend_has_baseline_accessibility_contract(client: TestClient) -> None:
    html = client.get("/").text

    assert '<html lang="en">' in html
    assert '<meta name="viewport"' in html
    assert '<div id="root"></div>' in html
    assert "onclick=" not in html


def test_react_client_keeps_tokens_out_of_browser_storage_and_untrusted_html() -> None:
    source_paths = Path("frontend/src").rglob("*.ts*")
    source = "\n".join(path.read_text(encoding="utf-8") for path in source_paths)

    assert "localStorage" not in source
    assert "sessionStorage" not in source
    assert "dangerouslySetInnerHTML" not in source
    assert 'credentials: "same-origin"' in source
    assert '"X-CSRF-Token"' in source
