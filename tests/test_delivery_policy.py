import re
from pathlib import Path

import yaml


def workflow_source(name: str) -> str:
    return Path(f".github/workflows/{name}").read_text(encoding="utf-8")


def test_every_third_party_action_is_pinned_to_a_full_commit_sha() -> None:
    for path in Path(".github/workflows").glob("*.yml"):
        source = path.read_text(encoding="utf-8")
        for reference in re.findall(r"\buses:\s*([^\s#]+)", source):
            assert re.search(r"@[0-9a-f]{40}$", reference), f"mutable action in {path}: {reference}"


def test_ci_enforces_lock_coverage_real_browsers_and_honest_security_scans() -> None:
    source = workflow_source("ci.yml")

    assert "uv sync --frozen --extra dev" in source
    assert "--cov-fail-under=85" in source
    assert "chromium firefox webkit" in source
    assert "e2e and browser_compat" in source
    assert "scan-type: fs" in source
    assert "scanners: vuln,misconfig,secret" in source
    assert "scan-type: image" in source
    assert "continue-on-error" not in source


def test_release_workflow_keeps_candidate_off_traffic_until_product_smoke() -> None:
    source = workflow_source("azure-application-deploy.yml")

    smoke = source.index("Run product and tenant-isolation smoke against candidate")
    promotion = source.index("Promote candidate traffic atomically")
    provenance = source.index("Upload staging promotion manifest")
    assert smoke < promotion < provenance
    assert "staging_run_id" in source
    assert "actions/download-artifact@" in source
    assert "@sha256:" in source
    assert source.count('--job-execution-name "$execution_name"') == 2
    assert "sort_by([].properties, &startTime)[-1].status" not in source
    dispatch_inputs = source.split("workflow_dispatch:", 1)[1].split("permissions:", 1)[0]
    assert "image_reference" not in dispatch_inputs
    assert "continue-on-error" not in source


def test_delivery_files_are_valid_yaml_and_have_no_latest_tool_pin() -> None:
    for path in Path(".github/workflows").glob("*.yml"):
        assert yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "azcliversion: latest" not in workflow_source("azure-infrastructure.yml")


def test_runtime_bases_are_digest_pinned_and_compose_owns_fresh_data_volume() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    compose = Path("compose.yaml").read_text(encoding="utf-8")

    assert len(re.findall(r"^FROM .*@sha256:[0-9a-f]{64}", dockerfile, re.MULTILINE)) == 2
    assert "pip install --no-cache-dir --require-hashes" in dockerfile
    assert "external: true" not in compose
    assert "${POSTGRES_DATA_VOLUME:-" in compose
    assert "APP_DOCUMENT_LAB_ENABLED: ${APP_DOCUMENT_LAB_ENABLED:-false}" in compose
