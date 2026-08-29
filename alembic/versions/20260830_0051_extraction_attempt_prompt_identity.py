"""include prompt hash in extraction attempt uniqueness

Revision ID: 20260830_0051
Revises: 20260830_0050
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260830_0051"
down_revision: str | None = "20260830_0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "uq_catalogue_extraction_version"
_OLD_COLUMNS = (
    "candidate_id",
    "source_id",
    "content_hash",
    "schema_version",
    "provider",
    "model",
)
_NEW_COLUMNS = (
    "candidate_id",
    "source_id",
    "content_hash",
    "schema_version",
    "prompt_hash",
    "provider",
    "model",
)


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "catalogue_extraction_attempts", type_="unique")
    op.create_unique_constraint(
        _CONSTRAINT,
        "catalogue_extraction_attempts",
        list(_NEW_COLUMNS),
    )


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "catalogue_extraction_attempts", type_="unique")
    op.create_unique_constraint(
        _CONSTRAINT,
        "catalogue_extraction_attempts",
        list(_OLD_COLUMNS),
    )
