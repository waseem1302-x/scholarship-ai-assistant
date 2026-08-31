"""enrich scholarship information model and explicit evidence trust domains

Revision ID: 20260830_0056
Revises: 20260830_0055
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260830_0056"
down_revision: str | None = "20260830_0055"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("field_evidence") as batch_op:
        batch_op.add_column(sa.Column("trust_domain", sa.String(length=64), nullable=True))
        batch_op.create_index("ix_field_evidence_trust_domain", ["trust_domain"], unique=False)

    with op.batch_alter_table("funding_components") as batch_op:
        batch_op.add_column(sa.Column("unit", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("qualifier", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("original_text", sa.Text(), nullable=True))
        batch_op.create_index("ix_funding_components_frequency", ["frequency"], unique=False)

    with op.batch_alter_table("application_steps") as batch_op:
        batch_op.add_column(sa.Column("stage_type", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("required", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("actor_type", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("actor_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("outcome", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("original_text", sa.Text(), nullable=True))
        batch_op.create_index("ix_application_steps_stage_type", ["stage_type"], unique=False)

    with op.batch_alter_table("scholarship_eligibility_rules") as batch_op:
        batch_op.add_column(
            sa.Column("critical", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        batch_op.add_column(sa.Column("original_text", sa.Text(), nullable=True))
        batch_op.create_index(
            "ix_scholarship_eligibility_rules_critical",
            ["scholarship_id", "critical", "rule_type"],
            unique=False,
        )

    with op.batch_alter_table("opportunity_resources") as batch_op:
        batch_op.alter_column(
            "url",
            existing_type=sa.String(length=2048),
            nullable=True,
        )
        batch_op.add_column(sa.Column("contact_type", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("organization", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("contact_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("email", sa.String(length=320), nullable=True))
        batch_op.add_column(sa.Column("phone", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("address", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("original_text", sa.Text(), nullable=True))
        batch_op.create_index(
            "ix_opportunity_resources_contact_type", ["contact_type"], unique=False
        )
        batch_op.create_check_constraint(
            "ck_opportunity_resources_locator_present",
            "url IS NOT NULL OR email IS NOT NULL OR phone IS NOT NULL OR address IS NOT NULL",
        )

    with op.batch_alter_table("catalogue_materialized_claim_links") as batch_op:
        batch_op.add_column(sa.Column("trust_domain", sa.String(length=64), nullable=True))
        batch_op.create_index(
            "ix_catalogue_materialized_claim_links_trust_domain",
            ["trust_domain"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("catalogue_materialized_claim_links") as batch_op:
        batch_op.drop_index("ix_catalogue_materialized_claim_links_trust_domain")
        batch_op.drop_column("trust_domain")

    with op.batch_alter_table("opportunity_resources") as batch_op:
        batch_op.drop_constraint("ck_opportunity_resources_locator_present", type_="check")
        batch_op.drop_index("ix_opportunity_resources_contact_type")
        batch_op.drop_column("original_text")
        batch_op.drop_column("address")
        batch_op.drop_column("phone")
        batch_op.drop_column("email")
        batch_op.drop_column("contact_name")
        batch_op.drop_column("organization")
        batch_op.drop_column("contact_type")
        batch_op.alter_column(
            "url",
            existing_type=sa.String(length=2048),
            nullable=False,
        )

    with op.batch_alter_table("scholarship_eligibility_rules") as batch_op:
        batch_op.drop_index("ix_scholarship_eligibility_rules_critical")
        batch_op.drop_column("original_text")
        batch_op.drop_column("critical")

    with op.batch_alter_table("application_steps") as batch_op:
        batch_op.drop_index("ix_application_steps_stage_type")
        batch_op.drop_column("original_text")
        batch_op.drop_column("outcome")
        batch_op.drop_column("actor_name")
        batch_op.drop_column("actor_type")
        batch_op.drop_column("required")
        batch_op.drop_column("stage_type")

    with op.batch_alter_table("funding_components") as batch_op:
        batch_op.drop_index("ix_funding_components_frequency")
        batch_op.drop_column("original_text")
        batch_op.drop_column("qualifier")
        batch_op.drop_column("unit")

    with op.batch_alter_table("field_evidence") as batch_op:
        batch_op.drop_index("ix_field_evidence_trust_domain")
        batch_op.drop_column("trust_domain")
