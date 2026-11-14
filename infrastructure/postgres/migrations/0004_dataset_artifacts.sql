CREATE UNIQUE INDEX dataset_versions_dataset_manifest_sha_uidx
    ON datasets.dataset_versions (dataset_id, manifest_sha256);

CREATE TABLE datasets.dataset_artifacts (
    dataset_artifact_id UUID PRIMARY KEY,
    dataset_version_id UUID NOT NULL REFERENCES datasets.dataset_versions(dataset_version_id),
    artifact_type TEXT NOT NULL CHECK (artifact_type IN ('DRAW_NUMBERS_PARQUET', 'MANIFEST_JSON')),
    storage_backend TEXT NOT NULL CHECK (storage_backend IN ('S3')),
    object_key TEXT NOT NULL UNIQUE,
    sha256 CHAR(64) NOT NULL,
    byte_size BIGINT NOT NULL CHECK (byte_size >= 0),
    row_count BIGINT NOT NULL CHECK (row_count >= 0),
    media_type TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (dataset_version_id, artifact_type, sha256),
    CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    CHECK (length(trim(object_key)) > 0),
    CHECK (length(trim(media_type)) > 0),
    CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX dataset_artifacts_version_idx
    ON datasets.dataset_artifacts (dataset_version_id, artifact_type);

CREATE TRIGGER dataset_artifacts_append_only
BEFORE UPDATE OR DELETE ON datasets.dataset_artifacts
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();
