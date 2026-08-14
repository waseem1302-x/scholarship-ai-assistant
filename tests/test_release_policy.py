import json
from importlib.resources import files

import pytest

from app.cli.release_preflight import validate_release_policy


def test_release_policy_matches_real_alembic_head_and_is_rolling_safe() -> None:
    policy = validate_release_policy()

    assert policy["migration_classification"] in {"expand", "none"}
    assert policy["compatible_with_previous_release"] is True
    assert policy["contract_migration_deferred"] is True


def test_release_policy_is_packaged_with_the_runtime() -> None:
    policy = json.loads(files("app").joinpath("release_policy.json").read_text(encoding="utf-8"))
    assert policy["schema_version"] == 1


def test_contract_classification_is_rejected_by_the_staged_preflight(monkeypatch) -> None:
    policy = json.loads(files("app").joinpath("release_policy.json").read_text(encoding="utf-8"))
    policy["migration_classification"] = "contract"

    class ContractPolicy:
        def joinpath(self, _name: str):
            return self

        def read_text(self, *, encoding: str) -> str:
            assert encoding == "utf-8"
            return json.dumps(policy)

    monkeypatch.setattr("app.cli.release_preflight.files", lambda _package: ContractPolicy())
    with pytest.raises(RuntimeError, match="Contract migrations"):
        validate_release_policy()
