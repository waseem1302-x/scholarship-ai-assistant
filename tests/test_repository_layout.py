from pathlib import Path

import yaml


def test_catalogue_worker_uses_committed_baseline_and_ignored_live_override() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    env_files = compose["services"]["catalogue-worker"]["env_file"]

    assert env_files == [
        {"path": "./config/catalogue/worker.env.example"},
        {"path": "./.local/env/catalogue-worker.env", "required": False},
    ]
    assert Path("config/catalogue/worker.env.example").is_file()


def test_local_credentials_and_runtime_evidence_are_excluded_from_git_and_docker() -> None:
    gitignore = Path(".gitignore").read_text(encoding="utf-8").splitlines()
    dockerignore = Path(".dockerignore").read_text(encoding="utf-8").splitlines()

    assert ".catalogue-local/" in gitignore
    assert ".local/" in gitignore
    assert ".azure/" in gitignore
    assert ".env.*" in gitignore
    assert "!.env.example" in gitignore

    assert ".catalogue-local" in dockerignore
    assert ".local" in dockerignore
    assert ".azure" in dockerignore
    assert ".env.*" in dockerignore


def test_catalogue_worker_example_is_fail_closed_and_contains_no_live_credential() -> None:
    example = Path("config/catalogue/worker.env.example").read_text(encoding="utf-8")

    assert "APP_CATALOGUE_AI_INGESTION_ENABLED=false" in example
    assert "APP_CATALOGUE_AI_PROVIDER=unavailable" in example
    assert "APP_CATALOGUE_SCHEDULED_INGESTION_ENABLED=false" in example
    assert "AZURE_CLIENT_SECRET=" not in "\n".join(
        line for line in example.splitlines() if not line.lstrip().startswith("#")
    )
