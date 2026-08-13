from sqlalchemy.dialects import sqlite

from app.modules.opportunities.models import ApplicationWindowState
from app.modules.opportunities.repository import OpportunityRepository


def test_open_now_is_filtered_with_materialized_window_columns(db_session) -> None:
    repository = OpportunityRepository(db_session)

    statement = repository._public_opportunities_statement(open_now=True).limit(20).offset(40)
    sql = str(statement.compile(dialect=sqlite.dialect()))

    assert "catalogue_application_opening_date" in sql
    assert "catalogue_application_deadline" in sql
    assert "catalogue_cycle_is_archived" in sql
    assert "LIMIT ? OFFSET ?" in sql


def test_window_state_filter_is_translated_to_sql(db_session) -> None:
    repository = OpportunityRepository(db_session)
    statement = repository._public_opportunities_statement(
        application_window_state=ApplicationWindowState.UPCOMING
    )
    sql = str(statement.compile(dialect=sqlite.dialect()))

    assert "CASE" in sql
    assert "catalogue_application_opening_date" in sql


def test_data_quality_issue_queue_is_sql_queryable(db_session) -> None:
    repository = OpportunityRepository(db_session)
    statement = repository._data_quality_issues_statement().limit(20).offset(40)
    sql = str(statement.compile(dialect=sqlite.dialect()))

    assert "UNION ALL" in sql
    assert "required_documents" in sql
    assert "CAST" in sql
    assert "LIMIT ? OFFSET ?" in sql


def test_public_structured_filters_do_not_search_eligibility_prose(db_session) -> None:
    repository = OpportunityRepository(db_session)
    statement = repository._public_opportunities_statement(
        field="Artificial Intelligence",
        nationality="Pakistani",
        application_fee="not_required",
        english_requirement="IELTS",
    )
    sql = str(statement.compile(dialect=sqlite.dialect()))

    assert "eligibility_rule_values" in sql
    assert "lower(opportunities.field_eligibility)" not in sql
    assert "lower(opportunities.nationality_eligibility)" not in sql
    assert "lower(opportunities.application_fee_info)" not in sql
    assert "lower(opportunities.english_language_requirement)" not in sql
    assert " LIKE " not in sql.upper()
