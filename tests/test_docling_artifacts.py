"""Cross-platform integrity checks for the reviewed Docling model bundle."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_verifier_module():
    script_path = Path(__file__).parents[1] / "scripts" / "verify_docling_artifacts.py"
    spec = importlib.util.spec_from_file_location("verify_docling_artifacts", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_docling_artifact_manifest_uses_posix_path_order(tmp_path: Path) -> None:
    """The model lock is identical when created on Windows and verified on Linux."""

    (tmp_path / "docling").mkdir()
    (tmp_path / "RapidOcr").mkdir()
    (tmp_path / "docling" / "model.bin").write_bytes(b"docling")
    (tmp_path / "RapidOcr" / "model.bin").write_bytes(b"rapidocr")

    verifier = _load_verifier_module()

    assert [entry["path"] for entry in verifier._bundle_entries(tmp_path)] == [
        "RapidOcr/model.bin",
        "docling/model.bin",
    ]
