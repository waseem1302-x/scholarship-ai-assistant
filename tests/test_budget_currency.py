import pytest

from scripts.validate_budget_currency import validate_currency


def test_budget_currency_requires_exact_azure_billing_currency() -> None:
    assert validate_currency("MYR", "myr", 500) == {
        "status": "currency_confirmed",
        "currency": "MYR",
        "amount": 500,
    }


def test_budget_currency_rejects_mismatch_and_invalid_amount() -> None:
    with pytest.raises(ValueError, match="mismatch"):
        validate_currency("MYR", "USD", 500)
    with pytest.raises(ValueError, match="positive"):
        validate_currency("MYR", "MYR", 0)
