"""Validate Azure-reported billing currency before a numeric budget is deployed."""

import argparse
import json
import re

CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")


def validate_currency(expected: str, observed: str, amount: int) -> dict[str, object]:
    expected = expected.strip().upper()
    observed = observed.strip().upper()
    if not CURRENCY_PATTERN.fullmatch(expected) or not CURRENCY_PATTERN.fullmatch(observed):
        raise ValueError("Expected and observed billing currency must be three-letter ISO codes")
    if amount <= 0:
        raise ValueError("Budget amount must be positive")
    if expected != observed:
        raise ValueError(
            f"Budget currency mismatch: expected {expected}, Azure reported {observed}"
        )
    return {"status": "currency_confirmed", "currency": expected, "amount": amount}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected", required=True)
    parser.add_argument("--observed", required=True)
    parser.add_argument("--amount", type=int, required=True)
    arguments = parser.parse_args()
    print(
        json.dumps(
            validate_currency(arguments.expected, arguments.observed, arguments.amount),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
