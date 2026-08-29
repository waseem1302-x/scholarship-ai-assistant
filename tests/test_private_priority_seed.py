from __future__ import annotations

import json
import re
from pathlib import Path

from app.modules.catalogue_ingestion.seed_parser import (
    LocalSeedDocumentParser,
    SeedSourceLoader,
)

SEED_PATH = Path("data/seed/private_priority_scholarship_candidates.v1.json")


def _identity_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.casefold())


def test_private_priority_seed_is_review_only_parseable_and_deduplicated() -> None:
    payload = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    scholarships = payload["scholarships"]

    assert payload["visibility"] == "private"
    assert payload["publication_authorized"] is False
    assert payload["policy"]["seed_is_evidence"] is False
    assert payload["policy"]["third_party_pages_are_evidence"] is False
    assert len(scholarships) == 69

    identity_keys = [_identity_key(item["name"]) for item in scholarships]
    assert len(identity_keys) == len(set(identity_keys))
    assert all(
        any(keyword in {"priority-0", "priority-1", "priority-2"} for keyword in item["keywords"])
        for item in scholarships
    )

    loaded = SeedSourceLoader().load(str(SEED_PATH))
    parsed = LocalSeedDocumentParser().parse(loaded)
    assert len(parsed) == len(scholarships)

    names = {candidate.name for candidate in parsed}
    assert "Japanese Government MEXT Scholarship" in names
    assert "Chinese Government Scholarship" in names
    assert not any("Track Variant" in name for name in names)
    assert not any("Cohort" in name for name in names)
