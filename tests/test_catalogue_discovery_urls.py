import pytest

from app.modules.catalogue_ingestion.url_policy import (
    URLNormalizationPolicy,
    URLRejectionCode,
    normalize_comparison_url,
    normalize_discovery_lead_url,
)


@pytest.mark.parametrize(
    ("raw_url", "expected"),
    (
        (
            "https://EXAMPLE.edu:443/scholarships/csc/?utm_source=news&b=2&a=1#deadline",
            "https://example.edu/scholarships/csc?a=1&b=2",
        ),
        (
            "https://example.edu/path?b=2&a=3&a=1&a=1",
            "https://example.edu/path?a=1&a=1&a=3&b=2",
        ),
        (
            "https://b\u00fccher.example/Stipendium",
            "https://xn--bcher-kva.example/Stipendium",
        ),
        (
            "https://example.edu:8443/path/",
            "https://example.edu:8443/path",
        ),
        (
            "https://[2606:4700:4700::1111]:443/path",
            "https://[2606:4700:4700::1111]/path",
        ),
    ),
)
def test_discovery_url_normalization_is_deterministic(raw_url: str, expected: str) -> None:
    result = normalize_discovery_lead_url(raw_url)

    assert result.rejection_code is None
    assert result.normalized is not None
    assert result.normalized.value == expected


@pytest.mark.parametrize(
    ("raw_url", "expected_code"),
    (
        ("", URLRejectionCode.EMPTY),
        ("http://example.edu/scholarship", URLRejectionCode.UNSUPPORTED_SCHEME),
        ("https://user:secret@example.edu/path", URLRejectionCode.CREDENTIALS),
        ("https://@example.edu/path", URLRejectionCode.CREDENTIALS),
        ("https://example.edu:not-a-port/path", URLRejectionCode.INVALID_PORT),
        ("https://example.edu:0/path", URLRejectionCode.INVALID_PORT),
        ("https://example..edu/path", URLRejectionCode.INVALID_HOST),
        ("https://localhost/path", URLRejectionCode.INTERNAL_HOST),
        ("https://catalogue.internal/path", URLRejectionCode.INTERNAL_HOST),
        ("https://127.0.0.1/path", URLRejectionCode.PRIVATE_LITERAL),
        ("https://100.64.0.1/path", URLRejectionCode.PRIVATE_LITERAL),
        ("https://[::1]/path", URLRejectionCode.PRIVATE_LITERAL),
        ("https://[::ffff:127.0.0.1]/path", URLRejectionCode.PRIVATE_LITERAL),
        ("https://example.edu/login", URLRejectionCode.AUTHENTICATION_TARGET),
        ("https://example.edu/login.aspx", URLRejectionCode.AUTHENTICATION_TARGET),
        ("https://example.edu/%6Cogin", URLRejectionCode.AUTHENTICATION_TARGET),
        ("https://example.edu/%256Cogin", URLRejectionCode.AUTHENTICATION_TARGET),
        ("https://example.edu/path;jsessionid=abc", URLRejectionCode.AUTHENTICATION_TARGET),
        ("https://example.edu/path?session=x", URLRejectionCode.AUTHENTICATION_TARGET),
        ("https://example.edu/path?%2573ession=x", URLRejectionCode.AUTHENTICATION_TARGET),
        ("https://example.edu/bad%escape", URLRejectionCode.MALFORMED),
        ("https://example.edu/path with space", URLRejectionCode.MALFORMED),
        ("https://example.edu/" + "a" * 2040, URLRejectionCode.TOO_LONG),
    ),
)
def test_discovery_url_policy_fails_closed(
    raw_url: str,
    expected_code: URLRejectionCode,
) -> None:
    result = normalize_discovery_lead_url(raw_url)

    assert result.normalized is None
    assert result.rejection_code is expected_code


def test_comparison_policy_preserves_existing_http_support() -> None:
    assert normalize_comparison_url("HTTP://Example.edu:80/path/?utm_source=x") == (
        "http://example.edu/path"
    )


def test_url_policy_configuration_is_bounded() -> None:
    with pytest.raises(ValueError, match="HTTP/HTTPS subset"):
        URLNormalizationPolicy(
            allowed_schemes=frozenset({"ftp"}),
            reject_non_public_hosts=True,
            reject_authentication_targets=True,
        )
    with pytest.raises(ValueError, match="length must be between"):
        URLNormalizationPolicy(
            allowed_schemes=frozenset({"https"}),
            reject_non_public_hosts=True,
            reject_authentication_targets=True,
            max_length=0,
        )
    with pytest.raises(ValueError, match="length must be between"):
        URLNormalizationPolicy(
            allowed_schemes=frozenset({"https"}),
            reject_non_public_hosts=True,
            reject_authentication_targets=True,
            max_length=2049,
        )
