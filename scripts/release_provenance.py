"""Create and validate the evidence-bound staging promotion receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit
from xml.etree import ElementTree

WORKFLOW_PATH = ".github/workflows/azure-application-deploy.yml"
SCHEMA_VERSION = 3
EVIDENCE_PATHS = {
    "catalogue_audit": "catalogue-audit.json",
    "candidate_smoke": "candidate-smoke.json",
    "chromium_junit": "truth-first-chromium.xml",
    "chromium_screenshot": "chromium/truth-first-application-plan.png",
}


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _junit_counts(path: Path) -> dict[str, int]:
    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return {
        key: sum(int(suite.attrib.get(key, "0")) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }


def _url_belongs_to_root(source_url: str, root_url: str) -> bool:
    source = urlsplit(source_url)
    root = urlsplit(root_url)
    source_host = (source.hostname or "").casefold().removeprefix("www.")
    root_host = (root.hostname or "").casefold().removeprefix("www.")
    source_path = unquote(source.path).rstrip("/") or "/"
    root_path = unquote(root.path).rstrip("/") or "/"
    return (
        source.scheme == root.scheme == "https"
        and source_host == root_host
        and (
            root_path == "/"
            or source_path == root_path
            or source_path.startswith(f"{root_path}/")
        )
        and (not root.query or sorted(parse_qsl(source.query)) == sorted(parse_qsl(root.query)))
    )


def _validate_evidence(root: Path) -> None:
    audit = _load_json(root / EVIDENCE_PATHS["catalogue_audit"])
    required = audit.get("manifest_required_count")
    manifest_matches = audit.get("manifest_matches")
    if (
        audit.get("ready") is not True
        or not isinstance(required, int)
        or required < 12
        or not isinstance(audit.get("minimum_records"), int)
        or audit["minimum_records"] < 12
        or not isinstance(audit.get("publishable_count"), int)
        or audit["publishable_count"] < 12
        or audit.get("manifest_matched_count") != required
        or audit.get("missing_manifest_entries") != []
        or audit.get("ambiguous_manifest_entries") != []
    ):
        raise ValueError("catalogue audit does not prove every launch manifest entry")
    if not isinstance(manifest_matches, list) or len(manifest_matches) != required:
        raise ValueError("catalogue manifest match evidence count is inconsistent")
    names: set[str] = set()
    for match in manifest_matches:
        if not isinstance(match, dict):
            raise ValueError("catalogue manifest match evidence is malformed")
        name = match.get("canonical_name")
        root_url = match.get("official_root_url")
        source_url = match.get("source_url")
        try:
            uuid.UUID(str(match.get("opportunity_id")))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "catalogue manifest match evidence has an invalid opportunity"
            ) from exc
        if (
            not isinstance(name, str)
            or not name.strip()
            or name.casefold() in names
            or not isinstance(root_url, str)
            or not isinstance(source_url, str)
            or not _url_belongs_to_root(source_url, root_url)
        ):
            raise ValueError("catalogue manifest match evidence is incomplete or inconsistent")
        names.add(name.casefold())

    smoke = _load_json(root / EVIDENCE_PATHS["candidate_smoke"])
    if smoke.get("status") != "staging_smoke_passed":
        raise ValueError("candidate smoke evidence is invalid")

    counts = _junit_counts(root / EVIDENCE_PATHS["chromium_junit"])
    if counts != {"tests": 1, "failures": 0, "errors": 0, "skipped": 0}:
        raise ValueError(f"Chromium journey evidence is invalid: {counts}")

    screenshot = root / EVIDENCE_PATHS["chromium_screenshot"]
    if not screenshot.is_file() or screenshot.stat().st_size == 0:
        raise ValueError("Chromium success screenshot is missing or empty")
    if not screenshot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Chromium screenshot evidence is not a PNG file")


def create_receipt(
    *,
    root: Path,
    repository: str,
    commit_sha: str,
    image_reference: str,
    run_id: int,
    run_attempt: int,
) -> dict[str, Any]:
    _validate_evidence(root)
    if not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
        raise ValueError("commit SHA must be immutable")
    if not re.search(r"@sha256:[0-9a-f]{64}$", image_reference):
        raise ValueError("image reference must use an immutable digest")
    evidence = {
        key: {"path": relative_path, "sha256": _sha256(root / relative_path)}
        for key, relative_path in EVIDENCE_PATHS.items()
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "repository": repository,
        "workflow_path": WORKFLOW_PATH,
        "commit_sha": commit_sha,
        "image_reference": image_reference,
        "staging_run_id": run_id,
        "run_attempt": run_attempt,
        "environment": "staging",
        "evidence": evidence,
        "created_at": datetime.now(UTC).isoformat(),
    }


def validate_receipt(
    *,
    root: Path,
    receipt: dict[str, Any],
    workflow_run: dict[str, Any],
    expected_repository: str,
    expected_run_id: int,
    expected_head_sha: str,
) -> None:
    if workflow_run.get("path") != WORKFLOW_PATH:
        raise ValueError("workflow path mismatch")
    if workflow_run.get("status") != "completed" or workflow_run.get("conclusion") != "success":
        raise ValueError("staging workflow run was not successful")
    if workflow_run.get("event") != "workflow_dispatch":
        raise ValueError("staging workflow event mismatch")
    if workflow_run.get("id") != expected_run_id:
        raise ValueError("workflow run ID mismatch")
    repository = (workflow_run.get("head_repository") or {}).get("full_name")
    if repository != expected_repository:
        raise ValueError("workflow repository mismatch")
    if workflow_run.get("head_sha") != expected_head_sha:
        raise ValueError("workflow commit mismatch")

    if receipt.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("receipt schema version mismatch")
    if receipt.get("repository") != expected_repository:
        raise ValueError("receipt repository mismatch")
    if receipt.get("workflow_path") != WORKFLOW_PATH:
        raise ValueError("receipt workflow path mismatch")
    if receipt.get("environment") != "staging":
        raise ValueError("receipt environment mismatch")
    if receipt.get("staging_run_id") != expected_run_id:
        raise ValueError("receipt run ID mismatch")
    if receipt.get("run_attempt") != workflow_run.get("run_attempt"):
        raise ValueError("receipt run attempt mismatch")
    if receipt.get("commit_sha") != expected_head_sha:
        raise ValueError("receipt commit mismatch")
    if not re.search(r"@sha256:[0-9a-f]{64}$", str(receipt.get("image_reference", ""))):
        raise ValueError("receipt image reference is mutable")

    evidence = receipt.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != set(EVIDENCE_PATHS):
        raise ValueError("receipt evidence set is incomplete")
    for key, relative_path in EVIDENCE_PATHS.items():
        item = evidence.get(key)
        if not isinstance(item, dict) or item.get("path") != relative_path:
            raise ValueError(f"{key} evidence path mismatch")
        if item.get("sha256") != _sha256(root / relative_path):
            raise ValueError(f"{key} evidence digest mismatch")
    _validate_evidence(root)


def capture_audit(
    *, raw_path: Path, output_path: Path, execution_path: Path, execution: str, status: str
) -> dict[str, Any]:
    execution_path.write_text(
        json.dumps({"execution": execution, "status": status}, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    ansi = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
    audit = None
    for line in reversed(raw_path.read_text(encoding="utf-8").splitlines()):
        cleaned = ansi.sub("", line).strip()
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            continue
        try:
            candidate = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and "ready" in candidate:
            audit = candidate
            break
    if audit is None:
        raise ValueError("catalogue audit did not emit machine-readable JSON")
    output_path.write_text(json.dumps(audit, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if status != "Succeeded":
        raise ValueError(f"catalogue audit job ended with {status}")
    required = audit.get("manifest_required_count")
    if (
        audit.get("ready") is not True
        or not isinstance(required, int)
        or required < 12
        or audit.get("manifest_matched_count") != required
    ):
        raise ValueError("catalogue audit is not launch-ready for the manifest")
    return audit


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)

    capture = commands.add_parser("capture-audit")
    capture.add_argument("--raw", type=Path, required=True)
    capture.add_argument("--output", type=Path, required=True)
    capture.add_argument("--execution-output", type=Path, required=True)
    capture.add_argument("--execution", required=True)
    capture.add_argument("--status", required=True)

    create = commands.add_parser("create")
    create.add_argument("--root", type=Path, required=True)
    create.add_argument("--repository", required=True)
    create.add_argument("--commit-sha", required=True)
    create.add_argument("--image-reference", required=True)
    create.add_argument("--run-id", type=int, required=True)
    create.add_argument("--run-attempt", type=int, required=True)

    validate = commands.add_parser("validate")
    validate.add_argument("--root", type=Path, required=True)
    validate.add_argument("--workflow-run", type=Path, required=True)
    validate.add_argument("--expected-repository", required=True)
    validate.add_argument("--expected-run-id", type=int, required=True)
    validate.add_argument("--expected-head-sha", required=True)
    validate.add_argument("--github-output", type=Path)
    return result


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    if args.command == "capture-audit":
        capture_audit(
            raw_path=args.raw,
            output_path=args.output,
            execution_path=args.execution_output,
            execution=args.execution,
            status=args.status,
        )
        return
    if args.command == "create":
        receipt = create_receipt(
            root=args.root,
            repository=args.repository,
            commit_sha=args.commit_sha,
            image_reference=args.image_reference,
            run_id=args.run_id,
            run_attempt=args.run_attempt,
        )
        (args.root / "release-provenance.json").write_text(
            json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        return

    receipt = _load_json(args.root / "release-provenance.json")
    workflow_run = _load_json(args.workflow_run)
    validate_receipt(
        root=args.root,
        receipt=receipt,
        workflow_run=workflow_run,
        expected_repository=args.expected_repository,
        expected_run_id=args.expected_run_id,
        expected_head_sha=args.expected_head_sha,
    )
    if args.github_output is not None:
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write(f"source_reference={receipt['image_reference']}\n")
            output.write(f"staging_sha={receipt['commit_sha']}\n")


if __name__ == "__main__":
    main()
