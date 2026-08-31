import importlib
from pathlib import Path

from sqlalchemy.dialects.postgresql import dialect as postgresql_dialect

from app.modules.catalogue_ingestion.review_models import CatalogueCandidateReview

_migration_path = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "20260830_0054_rich_catalogue_materialization.py"
)
_migration_spec = importlib.util.spec_from_file_location("review_migration", _migration_path)
assert _migration_spec and _migration_spec.loader
REVIEW_MIGRATION = importlib.util.module_from_spec(_migration_spec)
_migration_spec.loader.exec_module(REVIEW_MIGRATION)


def test_candidate_review_constraint_names_fit_postgresql_identifier_limit() -> None:
    postgres = postgresql_dialect()

    for constraint in CatalogueCandidateReview.__table__.constraints:
        if constraint.name:
            postgres.validate_identifier(constraint.name)


def test_scoped_fact_foreign_key_names_fit_postgresql_identifier_limit() -> None:
    postgres = postgresql_dialect()

    table_names = (
        "scoped_deadlines",
        "funding_components",
        "required_documents",
        "application_steps",
    )
    for table_name in table_names:
        name = REVIEW_MIGRATION._scoped_fact_foreign_key_name(table_name)
        assert name == f"fk_{table_name}_programme_id"
        postgres.validate_identifier(name)
