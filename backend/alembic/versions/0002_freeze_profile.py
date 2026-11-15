from alembic import op

revision = "0002_freeze_profile"
down_revision = "0001_core"

def upgrade():
    op.execute("ALTER TABLE analysis_runs ADD COLUMN input_cutoff timestamptz")

def downgrade():
    op.execute("ALTER TABLE analysis_runs DROP COLUMN input_cutoff")
