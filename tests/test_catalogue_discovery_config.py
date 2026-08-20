from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app


def _base_settings(**changes: object) -> Settings:
    values: dict[str, object] = {
        "env": "test",
        "database_url": "sqlite+pysqlite:///:memory:",
        "jwt_secret": "discovery-config-test-secret-at-least-32-characters",
    }
    values.update(changes)
    return Settings(**values)


def _enabled_settings(**changes: object) -> Settings:
    values: dict[str, object] = {
        "catalogue_web_discovery_enabled": True,
        "catalogue_web_discovery_provider": "azure_responses_web_search",
        "catalogue_web_discovery_endpoint": "https://scholarship-ai.services.ai.azure.com",
        "catalogue_web_discovery_model": "gpt-5-mini",
        "catalogue_discovery_max_estimated_cost_per_run": Decimal("1.00"),
        "catalogue_discovery_max_estimated_cost_per_provider_request": Decimal("0.10"),
    }
    values.update(changes)
    return _base_settings(**values)


def test_discovery_defaults_are_disabled_and_fail_closed() -> None:
    settings = _base_settings()

    assert settings.catalogue_web_discovery_enabled is False
    assert settings.catalogue_web_discovery_provider == "unavailable"
    assert settings.catalogue_web_discovery_endpoint is None
    assert settings.catalogue_web_discovery_model == "unconfigured"
    assert settings.catalogue_web_discovery_token_scope == "https://ai.azure.com/.default"
    assert settings.catalogue_discovery_max_estimated_cost_per_run == Decimal("0")
    assert settings.catalogue_discovery_max_estimated_cost_per_provider_request == Decimal("0")


def test_disabled_discovery_does_not_change_application_startup(monkeypatch) -> None:
    settings = _base_settings()
    monkeypatch.setattr("app.main.get_settings", lambda: settings)

    application = create_app()

    assert application.state.settings is settings
    assert application.state.settings.catalogue_web_discovery_enabled is False


def test_enabled_discovery_loads_from_explicit_environment(monkeypatch) -> None:
    environment = {
        "APP_CATALOGUE_WEB_DISCOVERY_ENABLED": "true",
        "APP_CATALOGUE_WEB_DISCOVERY_PROVIDER": "azure_responses_web_search",
        "APP_CATALOGUE_WEB_DISCOVERY_ENDPOINT": ("https://scholarship-ai.services.ai.azure.com"),
        "APP_CATALOGUE_WEB_DISCOVERY_MODEL": "gpt-5-mini",
        "APP_CATALOGUE_DISCOVERY_MAX_ESTIMATED_COST_PER_RUN": "1.00",
        "APP_CATALOGUE_DISCOVERY_MAX_ESTIMATED_COST_PER_PROVIDER_REQUEST": "0.10",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    settings = Settings(_env_file=None)

    assert settings.catalogue_web_discovery_enabled is True
    assert settings.catalogue_web_discovery_provider == "azure_responses_web_search"
    assert settings.catalogue_discovery_max_estimated_cost_per_run == Decimal("1.00")


def test_malformed_environment_fails_application_startup(monkeypatch) -> None:
    monkeypatch.setenv("APP_CATALOGUE_WEB_DISCOVERY_ENABLED", "true")
    monkeypatch.setenv("APP_CATALOGUE_WEB_DISCOVERY_PROVIDER", "unavailable")
    monkeypatch.setattr("app.main.get_settings", lambda: Settings(_env_file=None))

    with pytest.raises(ValidationError, match="PROVIDER"):
        create_app()


def test_explicit_stable_discovery_configuration_is_accepted() -> None:
    settings = _enabled_settings()

    assert settings.catalogue_web_discovery_provider == "azure_responses_web_search"
    assert settings.catalogue_web_discovery_timeout_seconds == 30
    assert settings.catalogue_web_discovery_max_retries == 2
    assert settings.catalogue_web_discovery_max_response_bytes == 500_000
    assert settings.catalogue_discovery_max_queries_per_run == 5
    assert settings.catalogue_discovery_max_provider_calls_per_run == 5
    assert settings.catalogue_discovery_max_leads_per_run == 25
    assert settings.catalogue_discovery_max_urls_per_query == 5
    assert settings.catalogue_discovery_max_tool_calls_per_provider_request == 1


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"catalogue_web_discovery_provider": "unavailable"}, "PROVIDER"),
        ({"catalogue_web_discovery_endpoint": None}, "ENDPOINT"),
        ({"catalogue_web_discovery_endpoint": "http://example.test"}, "HTTPS"),
        (
            {"catalogue_web_discovery_endpoint": "https://user@example.test"},
            "uncredentialed HTTPS",
        ),
        (
            {"catalogue_web_discovery_endpoint": "https://example.test?preview=true"},
            "uncredentialed HTTPS",
        ),
        ({"catalogue_web_discovery_model": "unconfigured"}, "MODEL"),
        ({"catalogue_web_discovery_model": "   "}, "MODEL"),
        (
            {"catalogue_web_discovery_token_scope": "https://ai.azure.com"},
            "TOKEN_SCOPE",
        ),
        ({"catalogue_discovery_max_queries_per_run": 0}, "MAX_QUERIES_PER_RUN"),
        (
            {"catalogue_discovery_max_provider_calls_per_run": 0},
            "MAX_PROVIDER_CALLS_PER_RUN",
        ),
        ({"catalogue_discovery_max_leads_per_run": 0}, "MAX_LEADS_PER_RUN"),
        ({"catalogue_discovery_max_urls_per_query": 0}, "MAX_URLS_PER_QUERY"),
        (
            {"catalogue_discovery_max_estimated_cost_per_run": Decimal("0")},
            "MAX_ESTIMATED_COST_PER_RUN",
        ),
        (
            {"catalogue_discovery_max_estimated_cost_per_provider_request": Decimal("0")},
            "MAX_ESTIMATED_COST_PER_PROVIDER_REQUEST",
        ),
        (
            {"catalogue_discovery_max_tool_calls_per_provider_request": 0},
            "MAX_TOOL_CALLS_PER_PROVIDER_REQUEST",
        ),
    ],
)
def test_enabled_discovery_rejects_missing_or_unsafe_configuration(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        _enabled_settings(**changes)


def test_enabled_discovery_rejects_preview_provider_mode() -> None:
    with pytest.raises(ValidationError, match="catalogue_web_discovery_provider"):
        _enabled_settings(catalogue_web_discovery_provider="azure_responses_web_search_preview")


def test_enabled_discovery_rejects_request_cost_above_run_ceiling() -> None:
    with pytest.raises(ValidationError, match="cannot exceed"):
        _enabled_settings(
            catalogue_discovery_max_estimated_cost_per_run=Decimal("0.05"),
            catalogue_discovery_max_estimated_cost_per_provider_request=Decimal("0.10"),
        )


def test_enabled_discovery_rejects_per_query_urls_above_run_lead_ceiling() -> None:
    with pytest.raises(ValidationError, match="MAX_URLS_PER_QUERY cannot exceed"):
        _enabled_settings(
            catalogue_discovery_max_urls_per_query=6,
            catalogue_discovery_max_leads_per_run=5,
        )
