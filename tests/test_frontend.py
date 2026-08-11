import re
from html.parser import HTMLParser

from fastapi.testclient import TestClient


class FrontendParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.sections: set[str] = set()
        self.forms: set[str] = set()
        self.scripts: list[str] = []
        self.stylesheets: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        element_id = attributes.get("id")
        if element_id:
            self.ids.append(element_id)
            if tag == "section":
                self.sections.add(element_id)
            if tag == "form":
                self.forms.add(element_id)
        if tag == "script" and attributes.get("src"):
            self.scripts.append(attributes["src"] or "")
        if tag == "link" and attributes.get("rel") == "stylesheet":
            self.stylesheets.append(attributes.get("href") or "")
        if tag == "a" and attributes.get("href"):
            self.links.append(attributes["href"] or "")


def parse_frontend(html: str) -> FrontendParser:
    parser = FrontendParser()
    parser.feed(html)
    return parser


def test_frontend_shell_exposes_slice_10_product_flows(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200

    html = response.text
    parser = parse_frontend(html)

    assert "Scholarship AI Assistant" in html
    assert "does not guarantee admission" in html
    assert "official-source seed records" in html
    assert "/static/app.js" in parser.scripts
    assert "/static/styles.css" in parser.stylesheets
    assert "/docs" in parser.links
    assert {
        "auth-panel",
        "workspace",
        "opportunities",
        "profile",
        "matches",
        "tracker",
        "admin",
    } <= (parser.sections)
    assert {"auth-form", "opportunity-filters", "profile-form", "admin-create-form"} <= parser.forms
    assert "review-list" in parser.ids
    assert "quality-list" in parser.ids


def test_frontend_html_has_unique_ids_and_no_encoding_artifacts(client: TestClient) -> None:
    html = client.get("/").text
    parser = parse_frontend(html)

    duplicated_ids = {element_id for element_id in parser.ids if parser.ids.count(element_id) > 1}

    assert duplicated_ids == set()
    assert "Â" not in html
    assert "TÃ" not in html


def test_frontend_static_assets_are_product_specific(client: TestClient) -> None:
    css = client.get("/static/styles.css")
    js = client.get("/static/app.js")

    assert css.status_code == 200
    assert js.status_code == 200
    assert "workspace" in css.text
    assert "@media (max-width: 1100px)" in css.text
    assert "Official source evidence" in js.text
    assert "Phase 2 checks" in js.text
    assert "/admin/review-queue" in js.text
    assert "/admin/data-quality-issues" in js.text
    assert "/review-actions" in js.text
    assert "Resolve conflict" in js.text
    assert "request_recheck" in js.text
    assert "Funding package" in js.text
    assert "Match scores and eligibility explanations are decision support" in js.text
    assert "does not guarantee" not in js.text.lower()
    assert "Â" not in js.text
    assert "TÃ" not in js.text


def test_primary_frontend_has_baseline_accessibility_contract(client: TestClient) -> None:
    html = client.get("/").text
    css = client.get("/static/styles.css").text

    assert '<html lang="en">' in html
    assert "<main" in html
    assert 'role="status"' in html
    assert 'autocomplete="email"' in html
    assert "input:focus" in css
    assert "textarea:focus" in css
    assert "onclick=" not in html


def test_frontend_javascript_does_not_reintroduce_duplicate_function_definitions(
    client: TestClient,
) -> None:
    js = client.get("/static/app.js").text
    function_names = re.findall(r"^(?:async\s+)?function\s+([A-Za-z0-9_]+)\(", js, re.MULTILINE)
    duplicated_functions = {
        function_name for function_name in function_names if function_names.count(function_name) > 1
    }

    assert duplicated_functions == set()
