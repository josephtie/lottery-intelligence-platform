CREATE SCHEMA IF NOT EXISTS catalog;
CREATE SCHEMA IF NOT EXISTS ingestion;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS datasets;
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE catalog.games (
    game_id UUID PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    country_code CHAR(2) NOT NULL,
    operator_name TEXT,
    timezone_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (code = lower(code)),
    CHECK (length(trim(display_name)) > 0),
    CHECK (country_code ~ '^[A-Z]{2}$')
);

CREATE TABLE catalog.game_versions (
    game_version_id UUID PRIMARY KEY,
    game_id UUID NOT NULL REFERENCES catalog.games(game_id),
    version TEXT NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE,
    rules JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (game_version_id, game_id),
    UNIQUE (game_id, version),
    CHECK (effective_to IS NULL OR effective_to > effective_from)
);

CREATE TABLE catalog.draw_types (
    draw_type_id UUID PRIMARY KEY,
    game_version_id UUID NOT NULL REFERENCES catalog.game_versions(game_version_id),
    code TEXT NOT NULL,
    display_name TEXT NOT NULL,
    rules JSONB NOT NULL DEFAULT '{}'::JSONB,
    UNIQUE (draw_type_id, game_version_id),
    UNIQUE (game_version_id, code),
    CHECK (length(trim(code)) > 0),
    CHECK (length(trim(display_name)) > 0)
);

CREATE TABLE ingestion.sources (
    source_id UUID PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    base_uri TEXT,
    source_kind TEXT NOT NULL CHECK (source_kind IN ('OFFICIAL', 'SECONDARY', 'FILE', 'MANUAL')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(code)) > 0),
    CHECK (length(trim(display_name)) > 0)
);

CREATE TABLE catalog.payout_rules (
    payout_rule_id UUID PRIMARY KEY,
    game_id UUID NOT NULL REFERENCES catalog.games(game_id),
    code TEXT NOT NULL,
    display_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (payout_rule_id, game_id),
    UNIQUE (game_id, code),
    CHECK (length(trim(code)) > 0)
);

CREATE TABLE catalog.payout_rule_versions (
    payout_rule_version_id UUID PRIMARY KEY,
    payout_rule_id UUID NOT NULL,
    game_id UUID NOT NULL,
    game_version_id UUID NOT NULL,
    version TEXT NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE,
    currency_code CHAR(3) NOT NULL,
    rule_definition JSONB NOT NULL,
    source_id UUID NOT NULL REFERENCES ingestion.sources(source_id),
    source_url TEXT NOT NULL,
    source_observed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (payout_rule_id, version),
    FOREIGN KEY (payout_rule_id, game_id)
        REFERENCES catalog.payout_rules(payout_rule_id, game_id),
    FOREIGN KEY (game_version_id, game_id)
        REFERENCES catalog.game_versions(game_version_id, game_id),
    CHECK (effective_to IS NULL OR effective_to > effective_from),
    CHECK (currency_code ~ '^[A-Z]{3}$'),
    CHECK (length(trim(source_url)) > 0)
);

CREATE TABLE ingestion.collection_runs (
    collection_run_id UUID PRIMARY KEY,
    source_id UUID NOT NULL REFERENCES ingestion.sources(source_id),
    collector_name TEXT NOT NULL,
    collector_version TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('RUNNING', 'SUCCEEDED', 'PARTIAL', 'FAILED')),
    request_metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    error_summary TEXT,
    CHECK (finished_at IS NULL OR finished_at >= started_at),
    CHECK ((status = 'RUNNING' AND finished_at IS NULL) OR (status <> 'RUNNING' AND finished_at IS NOT NULL))
);

CREATE TABLE ingestion.raw_objects (
    raw_object_id UUID PRIMARY KEY,
    sha256 CHAR(64) NOT NULL UNIQUE,
    object_key TEXT NOT NULL UNIQUE,
    byte_size BIGINT NOT NULL CHECK (byte_size >= 0),
    media_type TEXT NOT NULL,
    storage_backend TEXT NOT NULL DEFAULT 'S3',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    CHECK (length(trim(object_key)) > 0),
    CHECK (length(trim(media_type)) > 0)
);

CREATE TABLE ingestion.collection_events (
    collection_event_id UUID PRIMARY KEY,
    collection_run_id UUID NOT NULL REFERENCES ingestion.collection_runs(collection_run_id),
    event_ordinal INTEGER NOT NULL CHECK (event_ordinal > 0),
    raw_object_id UUID REFERENCES ingestion.raw_objects(raw_object_id),
    event_type TEXT NOT NULL CHECK (event_type IN ('PAYLOAD_RECEIVED', 'NO_NEW_DATA', 'HTTP_ERROR', 'PARSE_ERROR')),
    external_identifiers JSONB NOT NULL DEFAULT '{}'::JSONB,
    response_status INTEGER,
    observed_at TIMESTAMPTZ NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::JSONB,
    UNIQUE (collection_run_id, event_ordinal),
    CHECK ((event_type = 'PAYLOAD_RECEIVED' AND raw_object_id IS NOT NULL) OR event_type <> 'PAYLOAD_RECEIVED')
);

CREATE TABLE ingestion.ingestion_events (
    ingestion_event_id UUID PRIMARY KEY,
    collection_event_id UUID NOT NULL REFERENCES ingestion.collection_events(collection_event_id),
    event_type TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id UUID,
    details JSONB NOT NULL DEFAULT '{}'::JSONB,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(event_type)) > 0),
    CHECK (length(trim(subject_type)) > 0)
);

CREATE TABLE core.draws (
    draw_id UUID PRIMARY KEY,
    game_id UUID NOT NULL REFERENCES catalog.games(game_id),
    game_version_id UUID NOT NULL,
    draw_type_id UUID NOT NULL,
    scheduled_date DATE NOT NULL,
    scheduled_sequence INTEGER NOT NULL DEFAULT 1 CHECK (scheduled_sequence > 0),
    status TEXT NOT NULL DEFAULT 'SCHEDULED' CHECK (status IN (
        'SCHEDULED', 'EXPECTED', 'COLLECTING', 'DETECTED', 'VALIDATING', 'VALIDATED',
        'CONFIRMED', 'FROZEN', 'SETTLED', 'MISSING', 'DELAYED', 'INVALID', 'CONFLICT',
        'CORRECTED', 'CANCELLED', 'DISPUTED', 'SUPERSEDED'
    )),
    canonical_draw_version_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (game_version_id, draw_type_id, scheduled_date, scheduled_sequence),
    UNIQUE (draw_id, game_id),
    FOREIGN KEY (game_version_id, game_id)
        REFERENCES catalog.game_versions(game_version_id, game_id),
    FOREIGN KEY (draw_type_id, game_version_id)
        REFERENCES catalog.draw_types(draw_type_id, game_version_id)
);

CREATE TABLE core.draw_external_ids (
    draw_external_id UUID PRIMARY KEY,
    draw_id UUID NOT NULL REFERENCES core.draws(draw_id),
    source_id UUID NOT NULL REFERENCES ingestion.sources(source_id),
    external_draw_id TEXT NOT NULL,
    external_event_id TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    UNIQUE (source_id, external_draw_id),
    CHECK (length(trim(external_draw_id)) > 0),
    CHECK (last_seen_at >= first_seen_at)
);

CREATE TABLE core.draw_schedule_versions (
    draw_schedule_version_id UUID PRIMARY KEY,
    draw_id UUID NOT NULL REFERENCES core.draws(draw_id),
    version_number INTEGER NOT NULL CHECK (version_number > 0),
    source_id UUID NOT NULL REFERENCES ingestion.sources(source_id),
    raw_object_id UUID NOT NULL REFERENCES ingestion.raw_objects(raw_object_id),
    source_datetime TEXT NOT NULL,
    source_timezone TEXT NOT NULL,
    scheduled_at TIMESTAMPTZ NOT NULL,
    payload_sha256 CHAR(64) NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    schedule_data JSONB NOT NULL,
    UNIQUE (draw_id, version_number),
    UNIQUE (draw_id, payload_sha256),
    CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    CHECK (length(trim(source_timezone)) > 0)
);

CREATE TABLE core.draw_versions (
    draw_version_id UUID PRIMARY KEY,
    draw_id UUID NOT NULL REFERENCES core.draws(draw_id),
    version_number INTEGER NOT NULL CHECK (version_number > 0),
    source_id UUID NOT NULL REFERENCES ingestion.sources(source_id),
    raw_object_id UUID NOT NULL REFERENCES ingestion.raw_objects(raw_object_id),
    payload_sha256 CHAR(64) NOT NULL,
    result_observed_at TIMESTAMPTZ NOT NULL,
    validated_at TIMESTAMPTZ,
    confirmed_at TIMESTAMPTZ,
    validation_status TEXT NOT NULL CHECK (validation_status IN ('PENDING', 'VALID', 'INVALID', 'CONFLICT')),
    correction_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (draw_id, version_number),
    UNIQUE (draw_id, draw_version_id),
    CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    CHECK (validated_at IS NULL OR validated_at >= result_observed_at),
    CHECK (confirmed_at IS NULL OR validated_at IS NOT NULL AND confirmed_at >= validated_at)
);

ALTER TABLE core.draws
    ADD CONSTRAINT draws_canonical_version_same_draw_fk
    FOREIGN KEY (draw_id, canonical_draw_version_id)
    REFERENCES core.draw_versions(draw_id, draw_version_id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE core.draw_numbers (
    draw_version_id UUID NOT NULL REFERENCES core.draw_versions(draw_version_id),
    number_role TEXT NOT NULL,
    position INTEGER NOT NULL CHECK (position > 0),
    number INTEGER NOT NULL CHECK (number > 0),
    PRIMARY KEY (draw_version_id, number_role, position),
    CHECK (length(trim(number_role)) > 0)
);

CREATE TABLE core.draw_corrections (
    draw_correction_id UUID PRIMARY KEY,
    draw_id UUID NOT NULL REFERENCES core.draws(draw_id),
    old_draw_version_id UUID NOT NULL,
    new_draw_version_id UUID NOT NULL,
    reason TEXT NOT NULL,
    source_id UUID NOT NULL REFERENCES ingestion.sources(source_id),
    detected_at TIMESTAMPTZ NOT NULL,
    approved_at TIMESTAMPTZ,
    approved_by TEXT,
    UNIQUE (new_draw_version_id),
    FOREIGN KEY (draw_id, old_draw_version_id)
        REFERENCES core.draw_versions(draw_id, draw_version_id),
    FOREIGN KEY (draw_id, new_draw_version_id)
        REFERENCES core.draw_versions(draw_id, draw_version_id),
    CHECK (old_draw_version_id <> new_draw_version_id),
    CHECK (length(trim(reason)) > 0),
    CHECK (approved_at IS NULL OR approved_at >= detected_at)
);

CREATE TABLE core.draw_state_events (
    draw_state_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    draw_id UUID NOT NULL REFERENCES core.draws(draw_id),
    previous_status TEXT,
    new_status TEXT NOT NULL,
    reason TEXT,
    actor TEXT NOT NULL DEFAULT 'system',
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE ingestion.validation_events (
    validation_event_id UUID PRIMARY KEY,
    collection_run_id UUID NOT NULL REFERENCES ingestion.collection_runs(collection_run_id),
    raw_object_id UUID NOT NULL REFERENCES ingestion.raw_objects(raw_object_id),
    draw_version_id UUID REFERENCES core.draw_versions(draw_version_id),
    validator_name TEXT NOT NULL,
    validator_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PASSED', 'WARNING', 'FAILED', 'CONFLICT')),
    issues JSONB NOT NULL DEFAULT '[]'::JSONB,
    validated_at TIMESTAMPTZ NOT NULL,
    CHECK (jsonb_typeof(issues) = 'array')
);

CREATE TABLE datasets.datasets (
    dataset_id UUID PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(code)) > 0),
    CHECK (length(trim(display_name)) > 0)
);

CREATE TABLE datasets.dataset_versions (
    dataset_version_id UUID PRIMARY KEY,
    dataset_id UUID NOT NULL REFERENCES datasets.datasets(dataset_id),
    version_number INTEGER NOT NULL CHECK (version_number > 0),
    cutoff_at TIMESTAMPTZ NOT NULL,
    schema_version TEXT NOT NULL,
    code_version TEXT NOT NULL,
    manifest JSONB NOT NULL,
    manifest_sha256 CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (dataset_id, version_number),
    CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
    CHECK (jsonb_typeof(manifest) = 'object'),
    CHECK (length(trim(schema_version)) > 0),
    CHECK (length(trim(code_version)) > 0)
);

CREATE TABLE datasets.dataset_members (
    dataset_version_id UUID NOT NULL REFERENCES datasets.dataset_versions(dataset_version_id),
    draw_version_id UUID NOT NULL REFERENCES core.draw_versions(draw_version_id),
    ordinal BIGINT NOT NULL CHECK (ordinal > 0),
    PRIMARY KEY (dataset_version_id, draw_version_id),
    UNIQUE (dataset_version_id, ordinal)
);

CREATE TABLE ops.schema_migrations (
    version TEXT PRIMARY KEY,
    checksum_sha256 CHAR(64) NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$')
);

CREATE TABLE ops.outbox_events (
    outbox_event_id UUID PRIMARY KEY,
    aggregate_type TEXT NOT NULL,
    aggregate_id UUID NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_error TEXT,
    CHECK (length(trim(aggregate_type)) > 0),
    CHECK (length(trim(event_type)) > 0)
);

CREATE INDEX collection_runs_source_started_idx
    ON ingestion.collection_runs (source_id, started_at DESC);
CREATE INDEX collection_events_raw_object_idx
    ON ingestion.collection_events (raw_object_id) WHERE raw_object_id IS NOT NULL;
CREATE INDEX draws_schedule_lookup_idx
    ON core.draws (game_id, scheduled_date, status);
CREATE INDEX draw_versions_draw_created_idx
    ON core.draw_versions (draw_id, version_number DESC);
CREATE INDEX dataset_members_draw_version_idx
    ON datasets.dataset_members (draw_version_id);
CREATE INDEX outbox_events_pending_idx
    ON ops.outbox_events (available_at, occurred_at) WHERE published_at IS NULL;

CREATE OR REPLACE FUNCTION ops.reject_append_only_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION '% is append-only', TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME
        USING ERRCODE = '55000';
END;
$$;

CREATE TRIGGER raw_objects_append_only
BEFORE UPDATE OR DELETE ON ingestion.raw_objects
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER ingestion_events_append_only
BEFORE UPDATE OR DELETE ON ingestion.ingestion_events
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER validation_events_append_only
BEFORE UPDATE OR DELETE ON ingestion.validation_events
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER draw_schedule_versions_append_only
BEFORE UPDATE OR DELETE ON core.draw_schedule_versions
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER draw_versions_append_only
BEFORE UPDATE OR DELETE ON core.draw_versions
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER draw_numbers_append_only
BEFORE UPDATE OR DELETE ON core.draw_numbers
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER draw_corrections_append_only
BEFORE UPDATE OR DELETE ON core.draw_corrections
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER dataset_versions_append_only
BEFORE UPDATE OR DELETE ON datasets.dataset_versions
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER dataset_members_append_only
BEFORE UPDATE OR DELETE ON datasets.dataset_members
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER collection_events_append_only
BEFORE UPDATE OR DELETE ON ingestion.collection_events
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER draw_state_events_append_only
BEFORE UPDATE OR DELETE ON core.draw_state_events
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER game_versions_append_only
BEFORE UPDATE OR DELETE ON catalog.game_versions
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER draw_types_append_only
BEFORE UPDATE OR DELETE ON catalog.draw_types
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER payout_rule_versions_append_only
BEFORE UPDATE OR DELETE ON catalog.payout_rule_versions
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE FUNCTION core.validate_draw_state_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT (
        (OLD.status = 'SCHEDULED' AND NEW.status IN ('EXPECTED', 'COLLECTING', 'DETECTED', 'DELAYED', 'MISSING', 'CANCELLED')) OR
        (OLD.status = 'EXPECTED' AND NEW.status IN ('COLLECTING', 'DETECTED', 'DELAYED', 'MISSING', 'CANCELLED')) OR
        (OLD.status = 'COLLECTING' AND NEW.status IN ('DETECTED', 'DELAYED', 'MISSING', 'INVALID', 'CONFLICT')) OR
        (OLD.status = 'DETECTED' AND NEW.status IN ('VALIDATING', 'INVALID', 'CONFLICT')) OR
        (OLD.status = 'VALIDATING' AND NEW.status IN ('DETECTED', 'VALIDATED', 'INVALID', 'CONFLICT')) OR
        (OLD.status = 'VALIDATED' AND NEW.status IN ('CONFIRMED', 'CONFLICT', 'CORRECTED')) OR
        (OLD.status = 'CONFIRMED' AND NEW.status IN ('FROZEN', 'CONFLICT', 'CORRECTED')) OR
        (OLD.status = 'FROZEN' AND NEW.status IN ('SETTLED', 'CORRECTED', 'DISPUTED', 'SUPERSEDED')) OR
        (OLD.status = 'SETTLED' AND NEW.status IN ('CORRECTED', 'DISPUTED', 'SUPERSEDED')) OR
        (OLD.status = 'MISSING' AND NEW.status IN ('COLLECTING', 'DETECTED', 'CANCELLED')) OR
        (OLD.status = 'DELAYED' AND NEW.status IN ('COLLECTING', 'DETECTED', 'MISSING', 'CANCELLED')) OR
        (OLD.status = 'INVALID' AND NEW.status IN ('COLLECTING', 'DETECTED', 'VALIDATING')) OR
        (OLD.status = 'CONFLICT' AND NEW.status IN ('VALIDATING', 'VALIDATED', 'CONFIRMED', 'CORRECTED', 'DISPUTED')) OR
        (OLD.status = 'CORRECTED' AND NEW.status IN ('VALIDATING', 'VALIDATED', 'CONFIRMED', 'FROZEN', 'SETTLED', 'DISPUTED')) OR
        (OLD.status = 'DISPUTED' AND NEW.status IN ('VALIDATING', 'CONFIRMED', 'FROZEN', 'SETTLED', 'CORRECTED'))
    ) THEN
        RAISE EXCEPTION 'invalid draw status transition: % -> %', OLD.status, NEW.status
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION core.record_draw_state_event()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    previous_status TEXT;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF NEW.status IS NOT DISTINCT FROM OLD.status THEN
            RETURN NEW;
        END IF;
        previous_status := OLD.status;
    END IF;

    INSERT INTO core.draw_state_events (
        draw_id, previous_status, new_status, reason, actor
    ) VALUES (
        NEW.draw_id,
        previous_status,
        NEW.status,
        NULLIF(current_setting('app.draw_state_reason', TRUE), ''),
        COALESCE(NULLIF(current_setting('app.actor', TRUE), ''), 'system')
    );
    RETURN NEW;
END;
$$;

CREATE TRIGGER draws_state_transition_guard
BEFORE UPDATE OF status ON core.draws
FOR EACH ROW EXECUTE FUNCTION core.validate_draw_state_transition();

CREATE TRIGGER draws_state_event_log
AFTER INSERT OR UPDATE OF status ON core.draws
FOR EACH ROW EXECUTE FUNCTION core.record_draw_state_event();
