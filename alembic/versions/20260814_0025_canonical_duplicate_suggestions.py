"""Add canonical catalogue identity and human duplicate suggestions.

Revision ID: 20260814_0025
Revises: 20260814_0024
Create Date: 2026-08-14
"""

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import sqlalchemy as sa

from alembic import op

revision = "20260814_0025"
down_revision = "20260814_0024"
branch_labels = None
depends_on = None


def _identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")[:120] or "catalogue-record"


def _canonical_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/") or "/",
            urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True))),
            "",
        )
    )


def upgrade() -> None:
    with op.batch_alter_table("opportunities") as batch_op:
        batch_op.drop_constraint("uq_opportunities_provider_name_country_intake", type_="unique")
    op.add_column("providers", sa.Column("canonical_id", sa.String(length=120), nullable=True))
    op.create_index(op.f("ix_providers_canonical_id"), "providers", ["canonical_id"], unique=True)
    op.add_column(
        "opportunities", sa.Column("programme_family_id", sa.String(length=120), nullable=True)
    )
    op.add_column("opportunities", sa.Column("cycle_id", sa.String(length=120), nullable=True))
    op.add_column("sources", sa.Column("canonical_url", sa.String(length=2048), nullable=True))

    connection = op.get_bind()
    providers = sa.table(
        "providers",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("canonical_id"),
    )
    opportunities = sa.table(
        "opportunities",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("intake_year", sa.Integer()),
        sa.column("programme_family_id"),
        sa.column("cycle_id"),
    )
    sources = sa.table(
        "sources",
        sa.column("id", sa.Uuid()),
        sa.column("url", sa.String()),
        sa.column("canonical_url"),
    )
    used_provider_ids: set[str] = set()
    for provider in connection.execute(sa.select(providers).order_by(providers.c.id)).mappings():
        canonical_id = _identifier(provider["name"])
        if canonical_id in used_provider_ids:
            canonical_id = f"{canonical_id[:111]}-{str(provider['id'])[:8]}"
        used_provider_ids.add(canonical_id)
        connection.execute(
            providers.update()
            .where(providers.c.id == provider["id"])
            .values(canonical_id=canonical_id)
        )
    for opportunity in connection.execute(sa.select(opportunities)).mappings():
        connection.execute(
            opportunities.update()
            .where(opportunities.c.id == opportunity["id"])
            .values(
                programme_family_id=_identifier(opportunity["name"]),
                cycle_id=str(opportunity["intake_year"]) if opportunity["intake_year"] else None,
            )
        )
    for source in connection.execute(sa.select(sources)).mappings():
        connection.execute(
            sources.update()
            .where(sources.c.id == source["id"])
            .values(canonical_url=_canonical_url(source["url"]))
        )

    op.create_index(
        "ix_opportunities_canonical_identity",
        "opportunities",
        ["provider_id", "programme_family_id", "cycle_id", "degree_level", "funding_type"],
    )
    op.create_index(
        op.f("ix_opportunities_programme_family_id"), "opportunities", ["programme_family_id"]
    )
    op.create_index(op.f("ix_opportunities_cycle_id"), "opportunities", ["cycle_id"])
    op.create_index(op.f("ix_sources_canonical_url"), "sources", ["canonical_url"])
    op.create_table(
        "duplicate_suggestions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("matched_opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Numeric(5, 4), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "confirmed_duplicate",
                "dismissed",
                name="duplicate_suggestion_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["matched_opportunity_id"], ["opportunities.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "opportunity_id", "matched_opportunity_id", name="uq_duplicate_suggestion_pair"
        ),
    )
    op.create_index(
        op.f("ix_duplicate_suggestions_opportunity_id"), "duplicate_suggestions", ["opportunity_id"]
    )
    op.create_index(
        op.f("ix_duplicate_suggestions_matched_opportunity_id"),
        "duplicate_suggestions",
        ["matched_opportunity_id"],
    )
    op.create_index(op.f("ix_duplicate_suggestions_status"), "duplicate_suggestions", ["status"])
    op.create_index(
        "ix_duplicate_suggestions_status_score", "duplicate_suggestions", ["status", "score"]
    )


def downgrade() -> None:
    op.drop_index("ix_duplicate_suggestions_status_score", table_name="duplicate_suggestions")
    op.drop_index(op.f("ix_duplicate_suggestions_status"), table_name="duplicate_suggestions")
    op.drop_index(
        op.f("ix_duplicate_suggestions_matched_opportunity_id"), table_name="duplicate_suggestions"
    )
    op.drop_index(
        op.f("ix_duplicate_suggestions_opportunity_id"), table_name="duplicate_suggestions"
    )
    op.drop_table("duplicate_suggestions")
    op.drop_index(op.f("ix_sources_canonical_url"), table_name="sources")
    op.drop_index(op.f("ix_opportunities_cycle_id"), table_name="opportunities")
    op.drop_index(op.f("ix_opportunities_programme_family_id"), table_name="opportunities")
    op.drop_index("ix_opportunities_canonical_identity", table_name="opportunities")
    op.drop_column("sources", "canonical_url")
    op.drop_column("opportunities", "cycle_id")
    op.drop_column("opportunities", "programme_family_id")
    op.drop_index(op.f("ix_providers_canonical_id"), table_name="providers")
    op.drop_column("providers", "canonical_id")
    with op.batch_alter_table("opportunities") as batch_op:
        batch_op.create_unique_constraint(
            "uq_opportunities_provider_name_country_intake",
            ["provider_id", "name", "country", "intake_year"],
        )
