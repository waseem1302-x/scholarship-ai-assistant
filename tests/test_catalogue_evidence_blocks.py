from app.modules.catalogue_ingestion.evidence_blocks import (
    MAX_EVIDENCE_BLOCK_CHARACTERS,
    canonical_evidence_blocks,
)


def test_canonical_evidence_blocks_are_deterministic_and_preserve_offsets() -> None:
    text = ("A" * (MAX_EVIDENCE_BLOCK_CHARACTERS - 10)) + "\n\n" + ("B" * 80)

    first = canonical_evidence_blocks(text)
    second = canonical_evidence_blocks(text)

    assert first == second
    assert len(first) == 2
    assert [block.block_index for block in first] == [0, 1]
    assert all(len(block.block_id) == 64 for block in first)
    assert "A" * 10 in first[0].text
    for block in first:
        assert block.text == text[block.start_offset : block.end_offset]
        assert block.locator == {
            "start_offset": block.start_offset,
            "end_offset": block.end_offset,
        }


def test_canonical_evidence_blocks_do_not_mutate_or_drop_whitespace() -> None:
    text = "Heading\n\nEligibility includes a translated transcript.\n\nDeadline: 2027-05-15."

    blocks = canonical_evidence_blocks(text)

    assert "".join(block.text for block in blocks) == text
