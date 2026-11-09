import json
from datetime import datetime, timezone


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_events(chunk_text: str) -> list[dict]:
    events = []

    for line in chunk_text.splitlines():
        if line.strip():
            events.append(json.loads(line))

    return events


def save_new_events(connection, events: list[dict]) -> list[dict]:
    new_events = []

    with connection:
        for event in events:
            event_id = event["event_id"]

            already_exists = connection.execute(
                "SELECT 1 FROM raw_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()

            if already_exists:
                continue

            connection.execute(
                """
                INSERT INTO raw_events (
                    event_id,
                    event_type,
                    occurred_at,
                    workflow_id,
                    campaign_id,
                    payload_json,
                    ingested_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    event.get("type", "unknown"),
                    event.get("ts", ""),
                    event.get("workflow_id"),
                    event.get("campaign_id"),
                    json.dumps(event, sort_keys=True),
                    utc_now(),
                ),
            )

            new_events.append(event)

    return new_events


def save_cursor(
    connection,
    last_event_id: int,
    last_chunk: int,
) -> None:
    with connection:
        connection.execute(
            """
            INSERT INTO ingest_state (
                id, last_event_id, last_chunk, updated_at
            )
            VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                last_event_id = excluded.last_event_id,
                last_chunk = excluded.last_chunk,
                updated_at = excluded.updated_at
            """,
            (
                last_event_id,
                last_chunk,
                utc_now(),
            ),
        )


def load_cursor(connection) -> tuple[int, int]:
    row = connection.execute(
        "SELECT last_event_id, last_chunk FROM ingest_state WHERE id = 1"
    ).fetchone()

    if row is None:
        return -1, -1

    return row["last_event_id"], row["last_chunk"]