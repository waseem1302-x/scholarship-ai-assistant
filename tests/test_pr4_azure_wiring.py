from pathlib import Path


def test_pr4_crawler_gate_is_explicit_and_fail_closed_in_azure_job() -> None:
    source = Path("infra/azure/scheduled-jobs.bicep").read_text(encoding="utf-8")

    assert "param catalogueBoundedCrawlingEnabled bool = false" in source
    assert "name: 'APP_CATALOGUE_BOUNDED_CRAWLING_ENABLED'" in source
    assert "value: string(catalogueBoundedCrawlingEnabled)" in source