import json
import uuid
from datetime import datetime, timezone


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_audit(
    connection,
    action: str,
    actor: str = "controller",
    workflow_id: str | None = None,
    subject_type: str | None = None,
    subject_id: str | None = None,
    reason: str = "",
    evidence: dict | None = None,
) -> str:
    audit_id = str(uuid.uuid4())

    connection.execute(
        """
        INSERT INTO audit_events (
            audit_id,
            occurred_at,
            actor,
            action,
            workflow_id,
            subject_type,
            subject_id,
            reason,
            evidence_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            audit_id,
            utc_now(),
            actor,
            action,
            workflow_id,
            subject_type,
            subject_id,
            reason,
            json.dumps(evidence or {}, sort_keys=True),
        ),
    )

    return audit_id