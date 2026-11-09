import json
from datetime import datetime


def bucket_start(timestamp: str) -> str:
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return parsed.replace(
        minute=0,
        second=0,
        microsecond=0,
    ).isoformat()


def update_metrics(connection, events: list[dict]) -> None:
    with connection:
        for event in events:
            if event.get("type") != "call":
                continue

            workflow_id = event["workflow_id"]
            cohort_id = event.get("cohort_id", "default")
            bucket = bucket_start(event["ts"])

            connected = bool(event.get("connected", False))
            engaged = bool(event.get("engaged", False))

            qa = event.get("qa") or {}
            hallucinated = bool(qa.get("hallucination_flag", False))

            variant = event.get("variant") or {}
            variant_key = json.dumps(variant, sort_keys=True)

            caller_id = variant.get("caller_id")

            connection.execute(
                """
                INSERT INTO workflow_metrics (
                    workflow_id,
                    bucket_start,
                    dials,
                    connected,
                    engaged,
                    hallucination_flags
                )
                VALUES (?, ?, 1, ?, ?, ?)
                ON CONFLICT(workflow_id, bucket_start) DO UPDATE SET
                    dials = dials + 1,
                    connected = connected + ?,
                    engaged = engaged + ?,
                    hallucination_flags = hallucination_flags + ?
                """,
                (
                    workflow_id,
                    bucket,
                    int(connected),
                    int(connected and engaged),
                    int(hallucinated),
                    int(connected),
                    int(connected and engaged),
                    int(hallucinated),
                ),
            )

            connection.execute(
                """
                INSERT INTO variant_metrics (
                    workflow_id,
                    variant_key,
                    bucket_start,
                    dials,
                    connected,
                    engaged
                )
                VALUES (?, ?, ?, 1, ?, ?)
                ON CONFLICT(
                    workflow_id,
                    variant_key,
                    bucket_start
                ) DO UPDATE SET
                    dials = dials + 1,
                    connected = connected + ?,
                    engaged = engaged + ?
                """,
                (
                    workflow_id,
                    variant_key,
                    bucket,
                    int(connected),
                    int(connected and engaged),
                    int(connected),
                    int(connected and engaged),
                ),
            )

            connection.execute(
                """
                INSERT INTO cohort_metrics (
                    workflow_id,
                    cohort_id,
                    bucket_start,
                    dials,
                    connected,
                    engaged
                )
                VALUES (?, ?, ?, 1, ?, ?)
                ON CONFLICT(
                    workflow_id,
                    cohort_id,
                    bucket_start
                ) DO UPDATE SET
                    dials = dials + 1,
                    connected = connected + ?,
                    engaged = engaged + ?
                """,
                (
                    workflow_id,
                    cohort_id,
                    bucket,
                    int(connected),
                    int(connected and engaged),
                    int(connected),
                    int(connected and engaged),
                ),
            )

            if caller_id:
                connection.execute(
                    """
                    INSERT INTO caller_id_metrics (
                        workflow_id,
                        caller_id,
                        bucket_start,
                        dials,
                        connected
                    )
                    VALUES (?, ?, ?, 1, ?)
                    ON CONFLICT(
                        workflow_id,
                        caller_id,
                        bucket_start
                    ) DO UPDATE SET
                        dials = dials + 1,
                        connected = connected + ?
                    """,
                    (
                        workflow_id,
                        caller_id,
                        bucket,
                        int(connected),
                        int(connected),
                    ),
                )