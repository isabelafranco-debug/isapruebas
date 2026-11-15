from alembic import op

revision = "0003_stored_files"
down_revision = "0002_freeze_profile"


def upgrade():
    op.execute("""
        CREATE TABLE stored_files (
            storage_key text PRIMARY KEY,
            owner uuid NOT NULL REFERENCES users,
            content bytea NOT NULL,
            sha256 char(64) NOT NULL,
            created timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX stored_files_owner ON stored_files(owner);
    """)


def downgrade():
    op.execute("DROP TABLE stored_files")
