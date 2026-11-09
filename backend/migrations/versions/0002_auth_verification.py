"""Email verification, college email domains and token revocation.

Revision ID: 0002_auth_verification
Revises: 0001_baseline
Create Date: 2026-11-09

- colleges.email_domains: JSON list of accepted lowercase domains (the app's
  startup sync fills it from COLLEGE_EMAIL_DOMAINS and the built-in defaults).
- users.date_of_birth, users.email_verified_at (existing accounts stay
  unverified and verify at their next login), users.token_version,
  users.is_active.
- email_codes: hashed one-time codes for verification and password reset.
- Existing emails are lowercased where that cannot collide with another row.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0002_auth_verification'
down_revision: Union[str, Sequence[str], None] = '0001_baseline'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('colleges', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('email_domains', sa.JSON(), nullable=False, server_default=sa.text("'[]'"))
        )

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('date_of_birth', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('email_verified_at', sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column('token_version', sa.Integer(), nullable=False, server_default=sa.text('0'))
        )
        batch_op.add_column(
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true())
        )

    op.create_table('email_codes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('purpose', sa.String(length=16), nullable=False),
    sa.Column('code_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False, server_default=sa.text('0')),
    sa.Column('consumed_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('email_codes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_email_codes_id'), ['id'], unique=False)
        batch_op.create_index('ix_email_codes_user_purpose', ['user_id', 'purpose'], unique=False)

    # Emails are now stored lowercase and trimmed. Rows whose normalised form would
    # collide with another account are left as they are (lookups are
    # case-insensitive, so they still work) for an operator to resolve.
    op.execute(
        sa.text(
            "UPDATE users SET email = lower(trim(email)) "
            "WHERE email <> lower(trim(email)) AND NOT EXISTS ("
            "SELECT 1 FROM users AS other "
            "WHERE other.id <> users.id AND lower(trim(other.email)) = lower(trim(users.email)))"
        )
    )


def downgrade() -> None:
    """Downgrade schema. (Lowercased emails are not restored.)"""
    with op.batch_alter_table('email_codes', schema=None) as batch_op:
        batch_op.drop_index('ix_email_codes_user_purpose')
        batch_op.drop_index(batch_op.f('ix_email_codes_id'))

    op.drop_table('email_codes')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('is_active')
        batch_op.drop_column('token_version')
        batch_op.drop_column('email_verified_at')
        batch_op.drop_column('date_of_birth')

    with op.batch_alter_table('colleges', schema=None) as batch_op:
        batch_op.drop_column('email_domains')
