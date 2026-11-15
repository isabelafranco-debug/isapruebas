from alembic import op

revision = "0001_core"
down_revision = None

def upgrade():
    op.execute("""
    CREATE EXTENSION IF NOT EXISTS postgis;
    CREATE TABLE users (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name text NOT NULL,
      email text UNIQUE NOT NULL, password_hash text NOT NULL, created timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE sessions (
      token_hash text PRIMARY KEY, user_id uuid NOT NULL REFERENCES users ON DELETE CASCADE,
      csrf text NOT NULL, expires timestamptz NOT NULL, revoked timestamptz
    );
    CREATE INDEX sessions_user_idx ON sessions(user_id);
    CREATE TABLE auth_limits (scope text PRIMARY KEY, attempts int NOT NULL, resets timestamptz NOT NULL);
    CREATE TABLE farms (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), owner uuid NOT NULL REFERENCES users, name text NOT NULL, UNIQUE(owner,name));
    CREATE TABLE fields (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), owner uuid NOT NULL REFERENCES users,
      farm_id uuid NOT NULL REFERENCES farms, name text NOT NULL, geom geometry(Geometry,4326) NOT NULL,
      point geometry(Point,4326) NOT NULL, area_ha double precision, multicell boolean NOT NULL,
      version int NOT NULL DEFAULT 1, pilot boolean NOT NULL DEFAULT false, source text NOT NULL,
      updated timestamptz NOT NULL DEFAULT now(), UNIQUE(id, owner),
      CHECK (ST_GeometryType(geom) IN ('ST_Point','ST_Polygon','ST_MultiPolygon')),
      CHECK (area_ha > 0 OR area_ha IS NULL)
    );
    CREATE INDEX fields_geom_gist ON fields USING gist(geom);
    CREATE INDEX fields_owner_updated ON fields(owner,updated DESC);
    CREATE UNIQUE INDEX fields_pilot_once ON fields(owner) WHERE pilot;
    CREATE TABLE field_versions (
      field_id uuid NOT NULL REFERENCES fields, version int NOT NULL, snapshot jsonb NOT NULL,
      created timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(field_id,version)
    );
    CREATE TABLE crop_catalog (
      version text NOT NULL, code text NOT NULL, name text NOT NULL, family text NOT NULL, parameters jsonb NOT NULL,
      PRIMARY KEY(version,code)
    );
    CREATE TABLE crop_stages (
      version text NOT NULL, crop_code text NOT NULL, stage int NOT NULL, days int CHECK(days>0) NOT NULL, kc numeric NOT NULL,
      PRIMARY KEY(version,crop_code,stage), FOREIGN KEY(version,crop_code) REFERENCES crop_catalog(version,code)
    );
    CREATE TABLE rotations (version text NOT NULL, code text NOT NULL, crops jsonb NOT NULL, PRIMARY KEY(version,code));
    CREATE TABLE data_files (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), owner uuid NOT NULL REFERENCES users,
      storage_key text NOT NULL, sha256 char(64) NOT NULL, bytes bigint NOT NULL CHECK(bytes>0),
      created timestamptz NOT NULL DEFAULT now(), UNIQUE(owner,sha256)
    );
    CREATE TABLE datasets (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), cache_key text UNIQUE, field_id uuid REFERENCES fields,
      file_id uuid NOT NULL REFERENCES data_files, metadata jsonb NOT NULL, created timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE climate_daily (
      dataset_id uuid NOT NULL REFERENCES datasets, date date NOT NULL, tmean_c real, tmin_c real, tmax_c real,
      rh_pct real, wind2m_ms real, solar_mj_m2_day real, precip_mm_day real, qc_flag text NOT NULL,
      PRIMARY KEY(dataset_id,date)
    );
    CREATE TABLE jobs (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), owner uuid NOT NULL REFERENCES users, kind text NOT NULL,
      target uuid NOT NULL, dedupe text UNIQUE NOT NULL, payload jsonb NOT NULL DEFAULT '{}',
      status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','done','failed','cancelled')),
      attempts int NOT NULL DEFAULT 0, lease uuid, lease_until timestamptz, available timestamptz NOT NULL DEFAULT now(),
      cancel_requested boolean NOT NULL DEFAULT false, progress int NOT NULL DEFAULT 0, error text,
      created timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX jobs_next ON jobs(status,available,created);
    CREATE TABLE imports (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), owner uuid NOT NULL REFERENCES users, field_id uuid NOT NULL REFERENCES fields,
      field_version int NOT NULL, file_id uuid NOT NULL REFERENCES data_files, kind text NOT NULL, contract int NOT NULL DEFAULT 1,
      summary jsonb, created timestamptz NOT NULL DEFAULT now(), UNIQUE(owner,field_id,field_version,file_id,kind,contract)
    );
    CREATE TABLE soil_samples (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), import_id uuid NOT NULL REFERENCES imports,
      field_id uuid NOT NULL REFERENCES fields, sample_code text NOT NULL, sampled_on date NOT NULL,
      depth_from_cm real NOT NULL, depth_to_cm real NOT NULL, CHECK(depth_from_cm>=0 AND depth_to_cm>depth_from_cm),
      UNIQUE(import_id,sample_code,depth_from_cm,depth_to_cm)
    );
    CREATE TABLE soil_results (
      sample_id uuid NOT NULL REFERENCES soil_samples, variable text NOT NULL, value text NOT NULL,
      unit text NOT NULL, method text NOT NULL, PRIMARY KEY(sample_id,variable)
    );
    CREATE TABLE campaigns (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), import_id uuid NOT NULL REFERENCES imports, field_id uuid NOT NULL REFERENCES fields,
      crop_code text NOT NULL, cultivar text NOT NULL, planting_date date NOT NULL, harvest_date date NOT NULL,
      CHECK(harvest_date>planting_date), UNIQUE(import_id,crop_code,cultivar,planting_date,harvest_date)
    );
    CREATE TABLE analysis_runs (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), owner uuid NOT NULL REFERENCES users, field_id uuid NOT NULL REFERENCES fields,
      field_version int NOT NULL, inputs jsonb NOT NULL, field_snapshot jsonb NOT NULL,
      dataset_id uuid REFERENCES datasets, created timestamptz NOT NULL DEFAULT now(),
      FOREIGN KEY(field_id,field_version) REFERENCES field_versions(field_id,version)
    );
    CREATE INDEX analysis_runs_owner ON analysis_runs(owner,created DESC);
    CREATE TABLE results (run_id uuid PRIMARY KEY REFERENCES analysis_runs, model_version text NOT NULL, output jsonb NOT NULL, daily jsonb NOT NULL);
    CREATE TABLE reports (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), owner uuid NOT NULL REFERENCES users, run_id uuid NOT NULL REFERENCES analysis_runs,
      rotation_id text NOT NULL, producer text NOT NULL, template_version int NOT NULL DEFAULT 1,
      artifact_key text, sha_pdf text, sha_csv text, sha_daily text, created timestamptz NOT NULL DEFAULT now(),
      UNIQUE(run_id,rotation_id,template_version)
    );
    """)

def downgrade():
    op.execute("""
    DROP TABLE reports,results,analysis_runs,campaigns,soil_results,soil_samples,imports,jobs,climate_daily,
    datasets,data_files,rotations,crop_stages,crop_catalog,field_versions,fields,farms,auth_limits,sessions,users;
    """)
