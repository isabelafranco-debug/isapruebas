from alembic import op

revision = "0004_guide_and_soil"
down_revision = "0003_stored_files"


def upgrade():
    op.execute("ALTER TABLE users ADD COLUMN guide_seen boolean NOT NULL DEFAULT false")
    op.execute("""
        CREATE TABLE regional_soil (
            field_id uuid NOT NULL REFERENCES fields ON DELETE CASCADE,
            field_version integer NOT NULL,
            profile jsonb NOT NULL,
            PRIMARY KEY (field_id, field_version)
        )
    """)


def downgrade():
    op.execute("DROP TABLE regional_soil")
    op.execute("ALTER TABLE users DROP COLUMN guide_seen")
