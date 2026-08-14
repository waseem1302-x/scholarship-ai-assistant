"""Fail closed before a release candidate is allowed to mutate shared schema."""

import json
from importlib.resources import files

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core.config import get_settings


def validate_release_policy() -> dict[str, object]:
    policy = json.loads(files("app").joinpath("release_policy.json").read_text(encoding="utf-8"))
    required = {
        "schema_version",
        "alembic_heads",
        "migration_classification",
        "compatible_with_previous_release",
        "rollback_strategy",
        "reviewed_at",
    }
    missing = sorted(required - policy.keys())
    if missing:
        raise RuntimeError(f"Release migration policy is incomplete: {', '.join(missing)}")
    heads = sorted(ScriptDirectory.from_config(Config("alembic.ini")).get_heads())
    if sorted(policy["alembic_heads"]) != heads:
        raise RuntimeError("Release migration policy does not match the current Alembic head")
    if policy["migration_classification"] not in {"expand", "contract", "none"}:
        raise RuntimeError("Release migration classification is invalid")
    if policy["migration_classification"] == "contract":
        raise RuntimeError("Contract migrations require a separate, explicitly approved workflow")
    if not policy["compatible_with_previous_release"]:
        raise RuntimeError(
            "Automated staged releases must remain compatible with the prior revision"
        )
    if len(str(policy["rollback_strategy"]).strip()) < 40:
        raise RuntimeError("Release migration rollback strategy is not actionable")
    return policy


def main() -> None:
    settings = get_settings()
    if settings.env != "production" or not settings.migration_only:
        raise RuntimeError("Release preflight must run in isolated production migration mode")
    if "@sha256:" not in settings.release_version:
        raise RuntimeError("Release preflight requires an immutable image digest release version")
    policy = validate_release_policy()
    print(
        json.dumps(
            {
                "status": "release_preflight_passed",
                "alembic_heads": policy["alembic_heads"],
                "migration_classification": policy["migration_classification"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
