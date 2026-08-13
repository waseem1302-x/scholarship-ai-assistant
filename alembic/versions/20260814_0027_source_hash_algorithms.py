"""Type source content hashes as SHA-256 digests.

Revision ID: 20260814_0027
Revises: 20260814_0026
Create Date: 2026-08-14
"""

import sqlalchemy as sa

from alembic import op

revision = "20260814_0027"
down_revision = "20260814_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sources") as batch_op:
        batch_op.add_column(
            sa.Column(
                "hash_algorithm", sa.String(length=16), nullable=False, server_default="sha256"
            )
        )
    with op.batch_alter_table("source_excerpts") as batch_op:
        batch_op.add_column(
            sa.Column(
                "hash_algorithm", sa.String(length=16), nullable=False, server_default="sha256"
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("source_excerpts") as batch_op:
        batch_op.drop_column("hash_algorithm")
    with op.batch_alter_table("sources") as batch_op:
        batch_op.drop_column("hash_algorithm")
