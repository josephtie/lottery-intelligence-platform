ALTER TABLE ingestion.collection_events
    DROP CONSTRAINT collection_events_event_type_check;

ALTER TABLE ingestion.collection_events
    ADD CONSTRAINT collection_events_event_type_check
    CHECK (event_type IN (
        'PAYLOAD_RECEIVED',
        'NO_NEW_DATA',
        'HTTP_ERROR',
        'PARSE_ERROR',
        'RAW_STORAGE_ERROR',
        'REGISTRATION_ERROR'
    ));
