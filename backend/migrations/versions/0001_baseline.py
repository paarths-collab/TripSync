"""Baseline: the schema as created by Base.metadata.create_all before migrations existed.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-11-09

A database that was created by the app's create_all before Alembic was added
already has these tables: mark it with `alembic stamp 0001_baseline` (once),
then run `alembic upgrade head`. New databases simply run `alembic upgrade head`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001_baseline'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('colleges',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('colleges', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_colleges_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_colleges_name'), ['name'], unique=True)

    op.create_table('tags',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=50), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('tags', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tags_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tags_name'), ['name'], unique=True)

    op.create_table('campus_landmarks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('college_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('kind', sa.Enum('CAMPUS_POINT', 'HUB', name='landmarkkind', native_enum=False, length=32), nullable=False),
    sa.Column('latitude', sa.Float(), nullable=False),
    sa.Column('longitude', sa.Float(), nullable=False),
    sa.Column('timezone', sa.String(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['college_id'], ['colleges.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('college_id', 'name', name='uq_landmark_college_name')
    )
    with op.batch_alter_table('campus_landmarks', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_campus_landmarks_college_id'), ['college_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_campus_landmarks_id'), ['id'], unique=False)

    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('hashed_password', sa.String(), nullable=False),
    sa.Column('full_name', sa.String(), nullable=True),
    sa.Column('college_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['college_id'], ['colleges.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_email'), ['email'], unique=True)
        batch_op.create_index(batch_op.f('ix_users_full_name'), ['full_name'], unique=False)
        batch_op.create_index(batch_op.f('ix_users_id'), ['id'], unique=False)

    op.create_table('conversations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user1_id', sa.Integer(), nullable=False),
    sa.Column('user2_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user1_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['user2_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.create_index('ix_conversation_users', ['user1_id', 'user2_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_conversations_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_conversations_user1_id'), ['user1_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_conversations_user2_id'), ['user2_id'], unique=False)

    op.create_table('corridor_estimates',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('origin_landmark_id', sa.Integer(), nullable=False),
    sa.Column('hub_id', sa.Integer(), nullable=False),
    sa.Column('direction', sa.Enum('TO_HUB', 'FROM_HUB', name='direction', native_enum=False, length=32), nullable=False),
    sa.Column('status', sa.Enum('VERIFIED', 'UNVERIFIED', name='estimatestatus', native_enum=False, length=32), nullable=False),
    sa.Column('distance_m', sa.Integer(), nullable=True),
    sa.Column('duration_s', sa.Integer(), nullable=True),
    sa.Column('failure', sa.String(), nullable=True),
    sa.Column('checked_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['hub_id'], ['campus_landmarks.id'], ),
    sa.ForeignKeyConstraint(['origin_landmark_id'], ['campus_landmarks.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('origin_landmark_id', 'hub_id', 'direction', name='uq_corridor_estimate')
    )
    with op.batch_alter_table('corridor_estimates', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_corridor_estimates_id'), ['id'], unique=False)

    op.create_table('idempotency_records',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('operation', sa.String(), nullable=False),
    sa.Column('key', sa.String(), nullable=False),
    sa.Column('target_id', sa.Integer(), nullable=False),
    sa.Column('response_status', sa.Integer(), nullable=False),
    sa.Column('response_body', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'operation', 'key', name='uq_idempotency_user_op_key')
    )
    with op.batch_alter_table('idempotency_records', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_idempotency_records_id'), ['id'], unique=False)

    op.create_table('pooling_requests',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('ACTIVE', 'MATCHED', 'CONNECTED', 'COMPLETED', 'CANCELLED', name='poolingrequeststatus'), nullable=False),
    sa.Column('start_latitude', sa.Float(), nullable=False),
    sa.Column('start_longitude', sa.Float(), nullable=False),
    sa.Column('destination_latitude', sa.Float(), nullable=False),
    sa.Column('destination_longitude', sa.Float(), nullable=False),
    sa.Column('destination_name', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('pooling_requests', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pooling_requests_id'), ['id'], unique=False)

    op.create_table('profiles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(), nullable=True),
    sa.Column('phone_number', sa.String(), nullable=True),
    sa.Column('bio', sa.Text(), nullable=True),
    sa.Column('year_of_study', sa.String(), nullable=True),
    sa.Column('reviews', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('preferences', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('social_media_links', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('emergency_contact', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id')
    )
    with op.batch_alter_table('profiles', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_profiles_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_profiles_username'), ['username'], unique=True)

    op.create_table('service_posts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('poster_user_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('status', sa.Enum('OPEN', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED', name='servicestatus'), nullable=False),
    sa.Column('team_size', sa.Integer(), nullable=False),
    sa.Column('deadline', sa.DateTime(), nullable=True),
    sa.Column('compensation_type', sa.Enum('VOLUNTEER', 'FIXED_PRICE', 'HOURLY_RATE', 'NEGOTIABLE', name='compensationtype'), nullable=False),
    sa.Column('compensation_amount', sa.Float(), nullable=True),
    sa.Column('requires_resume', sa.Boolean(), nullable=False),
    sa.Column('requires_cover_letter', sa.Boolean(), nullable=False),
    sa.Column('is_anonymous', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['poster_user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('service_posts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_service_posts_id'), ['id'], unique=False)

    op.create_table('travel_parties',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('state', sa.Enum('AGREED', 'COMPLETED', 'CANCELLED', 'DISPUTED', name='partystate', native_enum=False, length=32), nullable=False),
    sa.Column('agreed_departure', sa.DateTime(), nullable=False),
    sa.Column('meeting_landmark_id', sa.Integer(), nullable=False),
    sa.Column('hub_id', sa.Integer(), nullable=False),
    sa.Column('direction', sa.Enum('TO_HUB', 'FROM_HUB', name='direction', native_enum=False, length=32), nullable=False),
    sa.Column('timezone', sa.String(), nullable=False),
    sa.Column('transport_responsibility', sa.Text(), nullable=False),
    sa.Column('cost_note', sa.Text(), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('ended_at', sa.DateTime(), nullable=True),
    sa.Column('end_reason', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['hub_id'], ['campus_landmarks.id'], ),
    sa.ForeignKeyConstraint(['meeting_landmark_id'], ['campus_landmarks.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('travel_parties', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_travel_parties_id'), ['id'], unique=False)

    op.create_table('travel_requests',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('college_id', sa.Integer(), nullable=False),
    sa.Column('mode', sa.Enum('SHARED_TAXI_PARTY', name='travelmode', native_enum=False, length=32), nullable=False),
    sa.Column('origin_landmark_id', sa.Integer(), nullable=False),
    sa.Column('hub_id', sa.Integer(), nullable=False),
    sa.Column('direction', sa.Enum('TO_HUB', 'FROM_HUB', name='direction', native_enum=False, length=32), nullable=False),
    sa.Column('earliest_departure', sa.DateTime(), nullable=False),
    sa.Column('latest_departure', sa.DateTime(), nullable=False),
    sa.Column('arrive_by', sa.DateTime(), nullable=True),
    sa.Column('timezone', sa.String(), nullable=False),
    sa.Column('flexibility_consent', sa.Boolean(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('status', sa.Enum('OPEN', 'RESERVED', 'FULFILLED', 'CANCELLED', 'EXPIRED', name='travelrequeststatus', native_enum=False, length=32), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['college_id'], ['colleges.id'], ),
    sa.ForeignKeyConstraint(['hub_id'], ['campus_landmarks.id'], ),
    sa.ForeignKeyConstraint(['origin_landmark_id'], ['campus_landmarks.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('travel_requests', schema=None) as batch_op:
        batch_op.create_index('ix_travel_requests_corridor', ['college_id', 'origin_landmark_id', 'hub_id', 'direction', 'status'], unique=False)
        batch_op.create_index(batch_op.f('ix_travel_requests_id'), ['id'], unique=False)
        batch_op.create_index('ix_travel_requests_status_expires', ['status', 'expires_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_travel_requests_user_id'), ['user_id'], unique=False)

    op.create_table('messages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('conversation_id', sa.Integer(), nullable=False),
    sa.Column('sender_id', sa.Integer(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('is_read', sa.Boolean(), nullable=True),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ),
    sa.ForeignKeyConstraint(['sender_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_messages_conversation_id'), ['conversation_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_messages_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_messages_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_messages_sender_id'), ['sender_id'], unique=False)

    op.create_table('pair_suggestions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('request_low_id', sa.Integer(), nullable=False),
    sa.Column('request_high_id', sa.Integer(), nullable=False),
    sa.Column('rule_version', sa.String(), nullable=False),
    sa.Column('reason', sa.Enum('WINDOW_OVERLAP', 'FLEXIBLE_WINDOW', name='suggestionreason', native_enum=False, length=32), nullable=False),
    sa.Column('feasible_start', sa.DateTime(), nullable=False),
    sa.Column('feasible_end', sa.DateTime(), nullable=False),
    sa.Column('estimate_status', sa.Enum('VERIFIED', 'UNVERIFIED', name='estimatestatus', native_enum=False, length=32), nullable=False),
    sa.Column('estimate_distance_m', sa.Integer(), nullable=True),
    sa.Column('estimate_duration_s', sa.Integer(), nullable=True),
    sa.Column('estimate_failure', sa.String(), nullable=True),
    sa.Column('estimate_checked_at', sa.DateTime(), nullable=True),
    sa.Column('warnings', sa.JSON(), nullable=False),
    sa.Column('valid_until', sa.DateTime(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint('request_low_id < request_high_id', name='ck_pair_suggestion_order'),
    sa.ForeignKeyConstraint(['request_high_id'], ['travel_requests.id'], ),
    sa.ForeignKeyConstraint(['request_low_id'], ['travel_requests.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('request_low_id', 'request_high_id', 'rule_version', name='uq_pair_suggestion')
    )
    with op.batch_alter_table('pair_suggestions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pair_suggestions_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_pair_suggestions_request_high_id'), ['request_high_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_pair_suggestions_request_low_id'), ['request_low_id'], unique=False)

    op.create_table('party_change_proposals',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('party_id', sa.Integer(), nullable=False),
    sa.Column('proposer_id', sa.Integer(), nullable=False),
    sa.Column('new_departure', sa.DateTime(), nullable=True),
    sa.Column('new_meeting_landmark_id', sa.Integer(), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('expected_party_version', sa.Integer(), nullable=False),
    sa.Column('state', sa.Enum('PENDING', 'APPROVED', 'REJECTED', 'WITHDRAWN', 'SUPERSEDED', name='changestate', native_enum=False, length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('resolved_at', sa.DateTime(), nullable=True),
    sa.Column('resolved_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['new_meeting_landmark_id'], ['campus_landmarks.id'], ),
    sa.ForeignKeyConstraint(['party_id'], ['travel_parties.id'], ),
    sa.ForeignKeyConstraint(['proposer_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('party_change_proposals', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_party_change_proposals_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_party_change_proposals_party_id'), ['party_id'], unique=False)
        batch_op.create_index('uq_pending_change_party', ['party_id'], unique=True, postgresql_where=sa.text("state = 'PENDING'"), sqlite_where=sa.text("state = 'PENDING'"))

    op.create_table('party_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('party_id', sa.Integer(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=True),
    sa.Column('event_type', sa.String(), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('occurred_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['party_id'], ['travel_parties.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('party_id', 'version', name='uq_party_event_version')
    )
    with op.batch_alter_table('party_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_party_events_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_party_events_party_id'), ['party_id'], unique=False)

    op.create_table('party_members',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('party_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('request_id', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('report_outcome', sa.Enum('COMPLETED', 'DID_NOT_HAPPEN', name='reportoutcome', native_enum=False, length=32), nullable=True),
    sa.Column('reported_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['party_id'], ['travel_parties.id'], ),
    sa.ForeignKeyConstraint(['request_id'], ['travel_requests.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('party_members', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_party_members_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_party_members_party_id'), ['party_id'], unique=False)
        batch_op.create_index('uq_active_member_request', ['request_id'], unique=True, postgresql_where=sa.text('active'), sqlite_where=sa.text('active = 1'))
        batch_op.create_index('uq_active_member_user', ['user_id'], unique=True, postgresql_where=sa.text('active'), sqlite_where=sa.text('active = 1'))

    op.create_table('pooling_connections',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('sender_request_id', sa.Integer(), nullable=False),
    sa.Column('receiver_request_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('PENDING', 'APPROVED', 'REJECTED', name='poolingconnectionstatus'), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('responded_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['receiver_request_id'], ['pooling_requests.id'], ),
    sa.ForeignKeyConstraint(['sender_request_id'], ['pooling_requests.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('pooling_connections', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pooling_connections_id'), ['id'], unique=False)

    op.create_table('service_applications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('service_post_id', sa.Integer(), nullable=False),
    sa.Column('applicant_user_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('PENDING', 'ACCEPTED', 'REJECTED', name='applicationstatus'), nullable=False),
    sa.Column('cover_letter', sa.Text(), nullable=True),
    sa.Column('resume_url', sa.String(), nullable=True),
    sa.Column('proposed_rate', sa.Float(), nullable=True),
    sa.Column('application_date', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['applicant_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['service_post_id'], ['service_posts.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('service_applications', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_service_applications_id'), ['id'], unique=False)

    op.create_table('service_post_tags',
    sa.Column('service_post_id', sa.Integer(), nullable=False),
    sa.Column('tag_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['service_post_id'], ['service_posts.id'], ),
    sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ),
    sa.PrimaryKeyConstraint('service_post_id', 'tag_id')
    )
    op.create_table('service_reviews',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('service_post_id', sa.Integer(), nullable=False),
    sa.Column('reviewer_id', sa.Integer(), nullable=False),
    sa.Column('reviewee_id', sa.Integer(), nullable=False),
    sa.Column('rating', sa.Integer(), nullable=False),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['reviewee_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['reviewer_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['service_post_id'], ['service_posts.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('service_reviews', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_service_reviews_id'), ['id'], unique=False)

    op.create_table('connection_proposals',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('suggestion_id', sa.Integer(), nullable=True),
    sa.Column('proposer_id', sa.Integer(), nullable=False),
    sa.Column('recipient_id', sa.Integer(), nullable=False),
    sa.Column('proposer_request_id', sa.Integer(), nullable=False),
    sa.Column('recipient_request_id', sa.Integer(), nullable=False),
    sa.Column('pair_low_request_id', sa.Integer(), nullable=False),
    sa.Column('pair_high_request_id', sa.Integer(), nullable=False),
    sa.Column('proposer_request_version', sa.Integer(), nullable=False),
    sa.Column('recipient_request_version', sa.Integer(), nullable=False),
    sa.Column('state', sa.Enum('PENDING', 'ACCEPTED', 'DECLINED', 'EXPIRED', 'WITHDRAWN', name='proposalstate', native_enum=False, length=32), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('party_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('resolved_at', sa.DateTime(), nullable=True),
    sa.CheckConstraint('pair_low_request_id < pair_high_request_id', name='ck_proposal_pair_order'),
    sa.ForeignKeyConstraint(['party_id'], ['travel_parties.id'], ),
    sa.ForeignKeyConstraint(['proposer_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['proposer_request_id'], ['travel_requests.id'], ),
    sa.ForeignKeyConstraint(['recipient_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['recipient_request_id'], ['travel_requests.id'], ),
    sa.ForeignKeyConstraint(['suggestion_id'], ['pair_suggestions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('connection_proposals', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_connection_proposals_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_connection_proposals_proposer_id'), ['proposer_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_connection_proposals_recipient_id'), ['recipient_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_connection_proposals_suggestion_id'), ['suggestion_id'], unique=False)
        batch_op.create_index('uq_pending_proposal_pair', ['pair_low_request_id', 'pair_high_request_id'], unique=True, postgresql_where=sa.text("state = 'PENDING'"), sqlite_where=sa.text("state = 'PENDING'"))

    op.create_table('outbox_messages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('event_id', sa.Integer(), nullable=False),
    sa.Column('recipient_id', sa.Integer(), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('status', sa.Enum('PENDING', 'SENT', 'ACKED', 'FAILED', name='outboxstatus', native_enum=False, length=32), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('next_attempt_at', sa.DateTime(), nullable=False),
    sa.Column('last_error', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('sent_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['event_id'], ['party_events.id'], ),
    sa.ForeignKeyConstraint(['recipient_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('outbox_messages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_outbox_messages_event_id'), ['event_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_outbox_messages_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_outbox_messages_recipient_id'), ['recipient_id'], unique=False)
        batch_op.create_index('ix_outbox_status_next', ['status', 'next_attempt_at'], unique=False)



def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('outbox_messages', schema=None) as batch_op:
        batch_op.drop_index('ix_outbox_status_next')
        batch_op.drop_index(batch_op.f('ix_outbox_messages_recipient_id'))
        batch_op.drop_index(batch_op.f('ix_outbox_messages_id'))
        batch_op.drop_index(batch_op.f('ix_outbox_messages_event_id'))

    op.drop_table('outbox_messages')
    with op.batch_alter_table('connection_proposals', schema=None) as batch_op:
        batch_op.drop_index('uq_pending_proposal_pair', postgresql_where=sa.text("state = 'PENDING'"), sqlite_where=sa.text("state = 'PENDING'"))
        batch_op.drop_index(batch_op.f('ix_connection_proposals_suggestion_id'))
        batch_op.drop_index(batch_op.f('ix_connection_proposals_recipient_id'))
        batch_op.drop_index(batch_op.f('ix_connection_proposals_proposer_id'))
        batch_op.drop_index(batch_op.f('ix_connection_proposals_id'))

    op.drop_table('connection_proposals')
    with op.batch_alter_table('service_reviews', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_service_reviews_id'))

    op.drop_table('service_reviews')
    op.drop_table('service_post_tags')
    with op.batch_alter_table('service_applications', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_service_applications_id'))

    op.drop_table('service_applications')
    with op.batch_alter_table('pooling_connections', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_pooling_connections_id'))

    op.drop_table('pooling_connections')
    with op.batch_alter_table('party_members', schema=None) as batch_op:
        batch_op.drop_index('uq_active_member_user', postgresql_where=sa.text('active'), sqlite_where=sa.text('active = 1'))
        batch_op.drop_index('uq_active_member_request', postgresql_where=sa.text('active'), sqlite_where=sa.text('active = 1'))
        batch_op.drop_index(batch_op.f('ix_party_members_party_id'))
        batch_op.drop_index(batch_op.f('ix_party_members_id'))

    op.drop_table('party_members')
    with op.batch_alter_table('party_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_party_events_party_id'))
        batch_op.drop_index(batch_op.f('ix_party_events_id'))

    op.drop_table('party_events')
    with op.batch_alter_table('party_change_proposals', schema=None) as batch_op:
        batch_op.drop_index('uq_pending_change_party', postgresql_where=sa.text("state = 'PENDING'"), sqlite_where=sa.text("state = 'PENDING'"))
        batch_op.drop_index(batch_op.f('ix_party_change_proposals_party_id'))
        batch_op.drop_index(batch_op.f('ix_party_change_proposals_id'))

    op.drop_table('party_change_proposals')
    with op.batch_alter_table('pair_suggestions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_pair_suggestions_request_low_id'))
        batch_op.drop_index(batch_op.f('ix_pair_suggestions_request_high_id'))
        batch_op.drop_index(batch_op.f('ix_pair_suggestions_id'))

    op.drop_table('pair_suggestions')
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_messages_sender_id'))
        batch_op.drop_index(batch_op.f('ix_messages_id'))
        batch_op.drop_index(batch_op.f('ix_messages_created_at'))
        batch_op.drop_index(batch_op.f('ix_messages_conversation_id'))

    op.drop_table('messages')
    with op.batch_alter_table('travel_requests', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_travel_requests_user_id'))
        batch_op.drop_index('ix_travel_requests_status_expires')
        batch_op.drop_index(batch_op.f('ix_travel_requests_id'))
        batch_op.drop_index('ix_travel_requests_corridor')

    op.drop_table('travel_requests')
    with op.batch_alter_table('travel_parties', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_travel_parties_id'))

    op.drop_table('travel_parties')
    with op.batch_alter_table('service_posts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_service_posts_id'))

    op.drop_table('service_posts')
    with op.batch_alter_table('profiles', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_profiles_username'))
        batch_op.drop_index(batch_op.f('ix_profiles_id'))

    op.drop_table('profiles')
    with op.batch_alter_table('pooling_requests', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_pooling_requests_id'))

    op.drop_table('pooling_requests')
    with op.batch_alter_table('idempotency_records', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_idempotency_records_id'))

    op.drop_table('idempotency_records')
    with op.batch_alter_table('corridor_estimates', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_corridor_estimates_id'))

    op.drop_table('corridor_estimates')
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_conversations_user2_id'))
        batch_op.drop_index(batch_op.f('ix_conversations_user1_id'))
        batch_op.drop_index(batch_op.f('ix_conversations_id'))
        batch_op.drop_index('ix_conversation_users')

    op.drop_table('conversations')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_id'))
        batch_op.drop_index(batch_op.f('ix_users_full_name'))
        batch_op.drop_index(batch_op.f('ix_users_email'))

    op.drop_table('users')
    with op.batch_alter_table('campus_landmarks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_campus_landmarks_id'))
        batch_op.drop_index(batch_op.f('ix_campus_landmarks_college_id'))

    op.drop_table('campus_landmarks')
    with op.batch_alter_table('tags', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tags_name'))
        batch_op.drop_index(batch_op.f('ix_tags_id'))

    op.drop_table('tags')
    with op.batch_alter_table('colleges', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_colleges_name'))
        batch_op.drop_index(batch_op.f('ix_colleges_id'))

    op.drop_table('colleges')

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for enum_name in _NATIVE_ENUM_TYPES:
            sa.Enum(name=enum_name).drop(bind, checkfirst=True)


# PostgreSQL enum types created by this revision (the pooling and service tables
# use native enums; campus enums are VARCHAR columns).
_NATIVE_ENUM_TYPES = (
    "poolingrequeststatus",
    "poolingconnectionstatus",
    "servicestatus",
    "compensationtype",
    "applicationstatus",
)
