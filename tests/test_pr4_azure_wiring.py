from pathlib import Path


def test_crawler_is_enabled_with_ten_page_default_in_azure_job() -> None:
    source = Path("infra/azure/scheduled-jobs.bicep").read_text(encoding="utf-8")

    assert "param catalogueBoundedCrawlingEnabled bool = true" in source
    assert "param catalogueAiMaxPagesPerCandidate int = 10" in source
    assert "name: 'APP_CATALOGUE_BOUNDED_CRAWLING_ENABLED'" in source
    assert "value: string(catalogueBoundedCrawlingEnabled)" in source
    assert "name: 'APP_CATALOGUE_AI_MAX_PAGES_PER_CANDIDATE'" in source
    assert "value: string(catalogueAiMaxPagesPerCandidate)" in source
