"""initial catalog schema

Revision ID: 0001
Revises:
Create Date: 2026-09-25 18:56:38.954425
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "districts",
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("city", sa.String(length=80), nullable=False),
        sa.Column("metro", sa.String(length=80), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("name", name=op.f("pk_districts")),
    )
    op.create_index("ix_districts_lat_lng", "districts", ["lat", "lng"], unique=False)
    op.create_index(op.f("ix_districts_metro"), "districts", ["metro"], unique=False)
    op.create_table(
        "media",
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("name", name=op.f("pk_media")),
    )
    op.create_index(op.f("ix_media_owner_id"), "media", ["owner_id"], unique=False)
    op.create_table(
        "outbox",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("type", sa.String(length=80), nullable=False),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox")),
    )
    op.create_index(
        "ix_outbox_unsent", "outbox", ["created_at"], unique=False, postgresql_where=sa.text("sent_at IS NULL")
    )
    op.create_table(
        "processed_events",
        sa.Column("event_id", sa.String(length=40), nullable=False),
        sa.Column("type", sa.String(length=80), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_processed_events")),
    )
    op.create_table(
        "owners",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("initials", sa.String(length=4), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("district", sa.String(length=80), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("rating_sum", sa.Integer(), nullable=False),
        sa.Column("jobs_done", sa.Integer(), nullable=False),
        sa.Column("on_time_jobs", sa.Integer(), nullable=False),
        sa.Column("joined_year", sa.Integer(), nullable=False),
        sa.Column("response_mins", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["district"], ["districts.name"], name=op.f("fk_owners_district_districts")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_owners")),
    )
    op.create_table(
        "listings",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("mode", sa.String(length=10), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("blurb", sa.String(length=500), nullable=False),
        sa.Column("district", sa.String(length=80), nullable=False),
        sa.Column("instructions", sa.String(length=2000), nullable=False),
        sa.Column("rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("photos", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("spec", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["district"], ["districts.name"], name=op.f("fk_listings_district_districts")),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"], name=op.f("fk_listings_owner_id_owners")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_listings")),
    )
    op.create_index("ix_listings_owner_created", "listings", ["owner_id", "created_at"], unique=False)
    op.create_index(op.f("ix_listings_owner_id"), "listings", ["owner_id"], unique=False)
    op.create_index("ix_listings_search", "listings", ["category", "active", "district"], unique=False)
    op.create_table(
        "reviews",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("listing_id", sa.String(length=40), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("author", sa.String(length=120), nullable=False),
        sa.Column("initials", sa.String(length=4), nullable=False),
        sa.Column("author_id", sa.String(length=64), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("on_time", sa.Boolean(), nullable=False),
        sa.Column("text", sa.String(length=1000), nullable=False),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["listing_id"], ["listings.id"], name=op.f("fk_reviews_listing_id_listings"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"], name=op.f("fk_reviews_owner_id_owners")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reviews")),
    )
    op.create_index("ix_reviews_listing_at", "reviews", ["listing_id", "at"], unique=False)
    op.create_index(op.f("ix_reviews_owner_id"), "reviews", ["owner_id"], unique=False)
    op.create_table(
        "saved_listings",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("listing_id", sa.String(length=40), nullable=False),
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["listing_id"], ["listings.id"], name=op.f("fk_saved_listings_listing_id_listings"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "listing_id", name=op.f("pk_saved_listings")),
    )
    op.create_index("ix_saved_user_at", "saved_listings", ["user_id", "saved_at"], unique=False)
    op.create_table(
        "slots",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("listing_id", sa.String(length=40), nullable=False),
        sa.Column("start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hours_usable", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["listing_id"], ["listings.id"], name=op.f("fk_slots_listing_id_listings"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_slots")),
    )
    op.create_index("ix_slots_listing_end", "slots", ["listing_id", "end"], unique=False)

    op.execute("CREATE INDEX ix_listings_title_trgm ON listings USING gin (lower(title) gin_trgm_ops)")
    op.execute("CREATE INDEX ix_listings_blurb_trgm ON listings USING gin (lower(blurb) gin_trgm_ops)")
    op.create_index(
        "ix_listings_live",
        "listings",
        ["category", "district"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL AND active"),
    )


def downgrade() -> None:
    op.drop_index("ix_listings_live", table_name="listings", postgresql_where=sa.text("deleted_at IS NULL AND active"))
    op.execute("DROP INDEX IF EXISTS ix_listings_blurb_trgm")
    op.execute("DROP INDEX IF EXISTS ix_listings_title_trgm")
    op.drop_index("ix_slots_listing_end", table_name="slots")
    op.drop_table("slots")
    op.drop_index("ix_saved_user_at", table_name="saved_listings")
    op.drop_table("saved_listings")
    op.drop_index(op.f("ix_reviews_owner_id"), table_name="reviews")
    op.drop_index("ix_reviews_listing_at", table_name="reviews")
    op.drop_table("reviews")
    op.drop_index("ix_listings_search", table_name="listings")
    op.drop_index(op.f("ix_listings_owner_id"), table_name="listings")
    op.drop_index("ix_listings_owner_created", table_name="listings")
    op.drop_table("listings")
    op.drop_table("owners")
    op.drop_table("processed_events")
    op.drop_index("ix_outbox_unsent", table_name="outbox", postgresql_where=sa.text("sent_at IS NULL"))
    op.drop_table("outbox")
    op.drop_index(op.f("ix_media_owner_id"), table_name="media")
    op.drop_table("media")
    op.drop_index(op.f("ix_districts_metro"), table_name="districts")
    op.drop_index("ix_districts_lat_lng", table_name="districts")
    op.drop_table("districts")
