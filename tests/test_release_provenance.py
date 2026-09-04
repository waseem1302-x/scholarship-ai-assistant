import hashlib
import json
from pathlib import Path

import pytest

from scripts.release_provenance import capture_audit, create_receipt, validate_receipt


def _write_evidence(root: Path) -> dict[str, Path]:
    root.mkdir()
    paths = {
        "catalogue_audit": root / "catalogue-audit.json",
        "candidate_smoke": root / "candidate-smoke.json",
        "chromium_junit": root / "truth-first-chromium.xml",
        "chromium_screenshot": root / "chromium" / "truth-first-application-plan.png",
    }
    paths["chromium_screenshot"].parent.mkdir()
    paths["catalogue_audit"].write_text(
        json.dumps(
            {
                "ready": True,
                "minimum_records": 12,
                "publishable_count": 12,
                "manifest_required_count": 12,
                "manifest_matched_count": 12,
                "manifest_matches": [
                    {
                        "canonical_name": f"Flagship {index}",
                        "official_root_url": f"https://official{index}.example/programme/",
                        "opportunity_id": f"00000000-0000-0000-0000-{index:012d}",
                        "source_url": f"https://official{index}.example/programme/call/",
                    }
                    for index in range(12)
                ],
                "missing_manifest_entries": [],
                "ambiguous_manifest_entries": [],
            }
        ),
        encoding="utf-8",
    )
    paths["candidate_smoke"].write_text(
        json.dumps({"status": "staging_smoke_passed"}), encoding="utf-8"
    )
    paths["chromium_junit"].write_text(
        '<testsuite tests="1" failures="0" errors="0" skipped="0"/>',
        encoding="utf-8",
    )
    paths["chromium_screenshot"].write_bytes(b"\x89PNG\r\n\x1a\nexample")
    return paths


def _workflow_run() -> dict[str, object]:
    return {
        "id": 123,
        "run_attempt": 2,
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
        "head_sha": "a" * 40,
        "path": ".github/workflows/azure-application-deploy.yml",
        "head_repository": {"full_name": "owner/repository"},
    }


def test_release_receipt_binds_run_identity_and_hashes_real_evidence(tmp_path: Path) -> None:
    root = tmp_path / "release-provenance"
    evidence = _write_evidence(root)

    receipt = create_receipt(
        root=root,
        repository="owner/repository",
        commit_sha="a" * 40,
        image_reference="registry.example/app@sha256:" + "b" * 64,
        run_id=123,
        run_attempt=2,
    )
    validate_receipt(
        root=root,
        receipt=receipt,
        workflow_run=_workflow_run(),
        expected_repository="owner/repository",
        expected_run_id=123,
        expected_head_sha="a" * 40,
    )

    assert receipt["schema_version"] == 3
    for key, path in evidence.items():
        assert receipt["evidence"][key]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda run, receipt, root: run.update(path=".github/workflows/other.yml"), "workflow"),
        (lambda run, receipt, root: run.update(conclusion="failure"), "successful"),
        (lambda run, receipt, root: run.update(run_attempt=3), "attempt"),
        (lambda run, receipt, root: run.update(head_sha="c" * 40), "commit"),
        (
            lambda run, receipt, root: (root / "candidate-smoke.json").write_text(
                json.dumps({"status": "staging_smoke_passed", "tampered": True}),
                encoding="utf-8",
            ),
            "digest",
        ),
    ],
)
def test_release_receipt_rejects_wrong_run_or_tampered_evidence(
    tmp_path: Path, mutation, message: str
) -> None:
    root = tmp_path / "release-provenance"
    _write_evidence(root)
    receipt = create_receipt(
        root=root,
        repository="owner/repository",
        commit_sha="a" * 40,
        image_reference="registry.example/app@sha256:" + "b" * 64,
        run_id=123,
        run_attempt=2,
    )
    run = _workflow_run()
    mutation(run, receipt, root)

    with pytest.raises(ValueError, match=message):
        validate_receipt(
            root=root,
            receipt=receipt,
            workflow_run=run,
            expected_repository="owner/repository",
            expected_run_id=123,
            expected_head_sha="a" * 40,
        )


def test_release_receipt_rejects_non_png_screenshot(tmp_path: Path) -> None:
    root = tmp_path / "release-provenance"
    paths = _write_evidence(root)
    paths["chromium_screenshot"].write_bytes(b"not-a-png")

    with pytest.raises(ValueError, match="PNG"):
        create_receipt(
            root=root,
            repository="owner/repository",
            commit_sha="a" * 40,
            image_reference="registry.example/app@sha256:" + "b" * 64,
            run_id=123,
            run_attempt=2,
        )


def test_release_receipt_rejects_incomplete_manifest_match_content(tmp_path: Path) -> None:
    root = tmp_path / "release-provenance"
    paths = _write_evidence(root)
    audit = json.loads(paths["catalogue_audit"].read_text(encoding="utf-8"))
    audit["manifest_matches"].pop()
    paths["catalogue_audit"].write_text(json.dumps(audit), encoding="utf-8")

    with pytest.raises(ValueError, match="manifest match evidence"):
        create_receipt(
            root=root,
            repository="owner/repository",
            commit_sha="a" * 40,
            image_reference="registry.example/app@sha256:" + "b" * 64,
            run_id=123,
            run_attempt=2,
        )


def test_capture_audit_keeps_machine_json_and_execution_identity(tmp_path: Path) -> None:
    raw = tmp_path / "audit.raw"
    output = tmp_path / "audit.json"
    execution = tmp_path / "execution.json"
    raw.write_text(
        '2026-09-04T00:00:00Z {"ready":true,"manifest_required_count":12,'
        '"manifest_matched_count":12}\n',
        encoding="utf-8",
    )

    audit = capture_audit(
        raw_path=raw,
        output_path=output,
        execution_path=execution,
        execution="audit-run-123",
        status="Succeeded",
    )

    assert audit["ready"] is True
    assert json.loads(output.read_text(encoding="utf-8"))["manifest_matched_count"] == 12
    assert json.loads(execution.read_text(encoding="utf-8")) == {
        "execution": "audit-run-123",
        "status": "Succeeded",
    }
