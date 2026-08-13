"""Add SQL-queryable catalogue application-window projection.

Revision ID: 20260813_0023
Revises: 20260813_0022
Create Date: 2026-08-13
"""

import sqlalchemy as sa

from alembic import op

revision = "20260813_0023"
down_revision = "20260813_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "opportunities",
        sa.Column("catalogue_application_opening_date", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "opportunities",
        sa.Column("catalogue_application_deadline", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "opportunities",
        sa.Column(
            "catalogue_is_rolling",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "opportunities",
        sa.Column(
            "catalogue_cycle_is_archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    opportunities = sa.table(
        "opportunities",
        sa.column("id", sa.Uuid()),
        sa.column("application_opening_date", sa.DateTime(timezone=True)),
        sa.column("application_deadline", sa.DateTime(timezone=True)),
        sa.column("catalogue_application_opening_date", sa.DateTime(timezone=True)),
        sa.column("catalogue_application_deadline", sa.DateTime(timezone=True)),
        sa.column("catalogue_is_rolling", sa.Boolean()),
        sa.column("catalogue_cycle_is_archived", sa.Boolean()),
    )
    cycles = sa.table(
        "opportunity_cycles",
        sa.column("opportunity_id", sa.Uuid()),
        sa.column("application_opening_date", sa.DateTime(timezone=True)),
        sa.column("application_deadline", sa.DateTime(timezone=True)),
        sa.column("is_rolling", sa.Boolean()),
        sa.column("is_archived", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    connection = op.get_bind()
    connection.execute(
        opportunities.update().values(
            catalogue_application_opening_date=opportunities.c.application_opening_date,
            catalogue_application_deadline=opportunities.c.application_deadline,
            catalogue_is_rolling=False,
            catalogue_cycle_is_archived=False,
        )
    )

    cycles_by_opportunity: dict[object, list[object]] = {}
    for cycle in connection.execute(sa.select(cycles)).mappings():
        cycles_by_opportunity.setdefault(cycle["opportunity_id"], []).append(cycle)
    for opportunity_id, opportunity_cycles in cycles_by_opportunity.items():
        eligible = [cycle for cycle in opportunity_cycles if not cycle["is_archived"]]
        selected = max(
            eligible or opportunity_cycles,
            key=lambda cycle: (
                cycle["application_deadline"] is None,
                cycle["application_deadline"],
                cycle["created_at"],
            ),
        )
        connection.execute(
            opportunities.update()
            .where(opportunities.c.id == opportunity_id)
            .values(
                catalogue_application_opening_date=selected["application_opening_date"],
                catalogue_application_deadline=selected["application_deadline"],
                catalogue_is_rolling=selected["is_rolling"],
                catalogue_cycle_is_archived=selected["is_archived"],
            )
        )

    op.create_index(
        "ix_opportunities_catalogue_window",
        "opportunities",
        [
            "status",
            "catalogue_cycle_is_archived",
            "catalogue_application_opening_date",
            "catalogue_application_deadline",
        ],
    )
    op.create_index(
        op.f("ix_opportunities_catalogue_application_opening_date"),
        "opportunities",
        ["catalogue_application_opening_date"],
    )
    op.create_index(
        op.f("ix_opportunities_catalogue_application_deadline"),
        "opportunities",
        ["catalogue_application_deadline"],
    )
    op.create_index(
        op.f("ix_opportunities_catalogue_cycle_is_archived"),
        "opportunities",
        ["catalogue_cycle_is_archived"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_opportunities_catalogue_cycle_is_archived"), "opportunities")
    op.drop_index(op.f("ix_opportunities_catalogue_application_deadline"), "opportunities")
    op.drop_index(op.f("ix_opportunities_catalogue_application_opening_date"), "opportunities")
    op.drop_index("ix_opportunities_catalogue_window", "opportunities")
    op.drop_column("opportunities", "catalogue_cycle_is_archived")
    op.drop_column("opportunities", "catalogue_is_rolling")
    op.drop_column("opportunities", "catalogue_application_deadline")
    op.drop_column("opportunities", "catalogue_application_opening_date")
