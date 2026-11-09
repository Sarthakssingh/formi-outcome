import sqlite3

from .audit import record_audit
from .detectors import detect_workflow_issues


def run(connection):
    workflow_ids = [
        row["workflow_id"]
        for row in connection.execute(
            "SELECT DISTINCT workflow_id FROM workflow_metrics"
        )
    ]

    for workflow_id in workflow_ids:
        alerts = detect_workflow_issues(connection, workflow_id)

        for alert in alerts:
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

            print(alert)