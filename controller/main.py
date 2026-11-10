import os
import time
from datetime import timedelta

from .client import SimulatorClient
from .db import connect
from .ingest import load_cursor, parse_events, save_cursor, save_new_events
from .metrics import update_metrics
from .settings import load_settings
from .detectors import detect_workflow_issues, sim_now
from .audit import record_audit
from . import caller_id

LAST_ALERT = {}                  # (workflow, alert type) -> simulated time of last alert
COOLDOWN = timedelta(hours=6)


def ingest_available(client, connection, last_event_id, last_chunk):
    """Read every chunk after our cursor, not just the ones in the advance reply."""
    chunks = sorted(client.event_chunks("events", last_chunk), key=lambda c: c["chunk"])
    for chunk_info in chunks:
        chunk_number = chunk_info["chunk"]
        events = [
            e for e in parse_events(client.event_chunk(chunk_number))
            if e["event_id"] > last_event_id
        ]
        new_events = save_new_events(connection, events)
        update_metrics(connection, new_events)

        for workflow_id in {e["workflow_id"] for e in new_events if e.get("workflow_id")}:
            now = sim_now(connection)
            for alert in detect_workflow_issues(connection, workflow_id):
                key = (workflow_id, alert["type"])
                if key in LAST_ALERT and now - LAST_ALERT[key] < COOLDOWN:
                    continue
                LAST_ALERT[key] = now
                record_audit(
                    connection,
                    action="DETECTION_ALERT",
                    workflow_id=workflow_id,
                    subject_type=alert["type"],
                    subject_id=workflow_id,
                    reason=(
                        f"{alert['type']} detected from "
                        f"{alert.get('dials', alert.get('connected'))} observations"
                    ),
                    evidence=alert,
                )

        if new_events:
            last_event_id = max(last_event_id, max(e["event_id"] for e in new_events))
        last_chunk = max(last_chunk, chunk_number)
        save_cursor(connection, last_event_id, last_chunk)
    return last_event_id, last_chunk


def main() -> None:
    settings = load_settings()
    client = SimulatorClient(settings.simulator_url, settings.request_timeout_seconds)
    workflows = {w["workflow_id"]: w for w in client.workflows()}
    connection = connect(settings.db_path)
    last_event_id, last_chunk = load_cursor(connection)

    state = client.state()
    # The simulator keeps state in memory. If our cursor is ahead of it, it is a new world: start clean.
    if last_event_id > state["last_event_id"]:
        print("New simulator world detected; resetting controller database.")
        connection.close()
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(settings.db_path + suffix):
                os.remove(settings.db_path + suffix)
        connection = connect(settings.db_path)
        last_event_id, last_chunk = load_cursor(connection)

    print(
        f"Controller started. Simulator: {settings.simulator_url}, minute={state['sim_minute']}, "
        f"finished={state['finished']}, last_event_id={last_event_id}, last_chunk={last_chunk}"
    )

    while True:
        # catch up first (covers a crash between advance and ingest, and an already-finished world)
        last_event_id, last_chunk = ingest_available(client, connection, last_event_id, last_chunk)
        caller_id.run(client, connection, workflows)
        if client.state().get("finished"):
            print("Simulation finished.")
            break
        client.advance(settings.advance_minutes)
        time.sleep(0.05)

    connection.close()


if __name__ == "__main__":
    main()
































# from multiprocessing import connection
# import os
# import sys
# import time
# from datetime import timedelta
# from .detectors import detect_workflow_issues, sim_now

# from .client import SimulatorClient
# from .db import connect
# from .ingest import (
#     load_cursor,
#     parse_events,
#     save_cursor,
#     save_new_events,
# )
# from .metrics import update_metrics
# from .settings import load_settings
# from .detectors import detect_workflow_issues
# from .audit import record_audit

# LAST_ALERT = {}                  # (workflow, alert type) -> simulated time of last alert
# COOLDOWN = timedelta(hours=6)


# def main() -> None:
#     settings = load_settings()
#     client = SimulatorClient(
#         settings.simulator_url,
#         settings.request_timeout_seconds,
#     )
#     connection = connect(settings.db_path)

#     last_event_id, last_chunk = load_cursor(connection)

#     print(
#         f"Controller started. Simulator: {settings.simulator_url}, "
#         f"last_event_id={last_event_id}, last_chunk={last_chunk}"
#     )

#     while True:
#         state = client.state()

#         if state.get("finished"):
#             print("Simulation finished.")
#             break

#         result = client.advance(settings.advance_minutes)

#         new_chunks = result.get("new_chunks", [])

#         for chunk_info in new_chunks:
#             chunk_number = chunk_info["chunk"]

#             if chunk_number <= last_chunk:
#                 continue

#             chunk_text = client.event_chunk(chunk_number)
#             events = parse_events(chunk_text)

#             # Filter out anything already processed, just in case.
#             events = [
#                 event
#                 for event in events
#                 if event["event_id"] > last_event_id
#             ]

#             new_events = save_new_events(connection, events)
#             update_metrics(connection, new_events)

#             workflow_ids = {
#                 event["workflow_id"]
#                 for event in new_events
#                 if event.get("workflow_id")
#             }
#             # for workflow_id in workflow_ids:
#             #     alerts = detect_workflow_issues(connection, workflow_id)
#             #     for alert in alerts:
#             for workflow_id in workflow_ids:
#                 now = sim_now(connection)
#                 for alert in detect_workflow_issues(connection, workflow_id):
#                     key = (workflow_id, alert["type"])
#                     if key in LAST_ALERT and now - LAST_ALERT[key] < COOLDOWN:
#                         continue
#                     LAST_ALERT[key] = now
#                     record_audit(
#                         connection,
#                         action="DETECTION_ALERT",
#                         workflow_id=workflow_id,
#                         subject_type=alert["type"],
#                         subject_id=workflow_id,
#                         reason=(
#                             f"{alert['type']} detected from "
#                             f"{alert.get('dials', alert.get('connected'))} observations"
#                         ),
#                         evidence=alert,
#                     )           
            
#             if new_events:
#                 last_event_id = max(
#                     last_event_id,
#                     max(event["event_id"] for event in new_events),
#                 )

#             last_chunk = max(last_chunk, chunk_number)

#             save_cursor(
#                 connection,
#                 last_event_id,
#                 last_chunk,
#             )

#         time.sleep(0.05)

#     connection.close()


# if __name__ == "__main__":
#     main()