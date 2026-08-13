-- DATA-101 read-only MySQL 8.4 quality queries.
-- Rejected/duplicate/compensated facts must not enter metric inputs.

-- DQ-S1-01: duplicate event IDs rejected by ingestion (behavior_event itself has a UK).
SELECT event_id, COUNT(*) AS rejected_duplicate_count
FROM event_ingest_rejection
WHERE rejection_code = 'duplicate_event_id'
GROUP BY event_id;

-- DQ-S1-02: required envelope completeness and failed-without-code.
SELECT id, event_id, event_name
FROM behavior_event
WHERE event_id IS NULL OR event_name IS NULL OR schema_version IS NULL
   OR occurred_at IS NULL OR module IS NULL OR result_status IS NULL
   OR source_type IS NULL OR privacy_class IS NULL OR payload_json IS NULL
   OR (result_status = 'failed' AND failure_code IS NULL);

-- DQ-S1-03: orphan Project/Version/User relations for Sprint 1 events.
SELECT e.id, e.event_id, e.event_name
FROM behavior_event AS e
LEFT JOIN user_account AS u ON u.id = e.user_id
LEFT JOIN project AS p ON p.id = e.project_id
LEFT JOIN project_version AS pv ON pv.id = e.project_version_id
WHERE e.event_name REGEXP '^(identity|project|file)\\.'
  AND ((e.user_id IS NOT NULL AND u.id IS NULL)
    OR (e.project_id IS NOT NULL AND p.id IS NULL)
    OR (e.project_version_id IS NOT NULL AND pv.id IS NULL)
    OR (pv.id IS NOT NULL AND e.project_id IS NOT NULL AND pv.project_id <> e.project_id));

-- DQ-S1-04: file events whose payload file_version_id has no authoritative row.
SELECT e.id, e.event_id, JSON_UNQUOTE(JSON_EXTRACT(e.payload_json, '$.file_version_id')) AS file_version_id
FROM behavior_event AS e
LEFT JOIN file_version AS fv
  ON fv.id = CAST(JSON_UNQUOTE(JSON_EXTRACT(e.payload_json, '$.file_version_id')) AS UNSIGNED)
WHERE e.event_name LIKE 'file.%'
  AND (JSON_EXTRACT(e.payload_json, '$.file_version_id') IS NULL OR fv.id IS NULL);

-- DQ-S1-05: invalid compensation references or duplicate compensation event IDs.
SELECT c.id, c.compensation_event_id, c.original_event_id
FROM event_compensation AS c
LEFT JOIN behavior_event AS original ON original.event_id = c.original_event_id
WHERE original.id IS NULL OR c.approved_by IS NULL;

-- DQ-S1-06: events excluded from metrics until relations and compensation are resolved.
SELECT e.event_id, e.event_name, 'compensated_or_rejected' AS quality_status
FROM behavior_event AS e
WHERE EXISTS (SELECT 1 FROM event_compensation AS c WHERE c.original_event_id = e.event_id)
   OR EXISTS (SELECT 1 FROM event_ingest_rejection AS r WHERE r.event_id = e.event_id);

-- DQ-S1-07: incomplete authoritative audit rows (AU is not projected as behavior_event).
SELECT id, operation_name, object_type, trace_id, command_id
FROM operation_audit_log
WHERE operation_name IS NULL OR operation_name = ''
   OR object_type IS NULL OR object_type = ''
   OR trace_id IS NULL OR trace_id = ''
   OR command_id IS NULL OR command_id = ''
   OR result_status IS NULL
   OR (result_status = 'failed' AND failure_code IS NULL);

-- DQ-S1-08: critical AU rows that cannot be correlated to their separate BF event.
SELECT a.id, a.operation_name, a.trace_id, a.command_id
FROM operation_audit_log AS a
LEFT JOIN behavior_event AS e
  ON e.trace_id = a.trace_id AND e.command_id = a.command_id
WHERE a.operation_name REGEXP '^(project|file|identity)\\.'
  AND e.id IS NULL;
