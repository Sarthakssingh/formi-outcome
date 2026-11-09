import math
from datetime import datetime, timedelta

MIN_DIALS = 200
MIN_CONNECTED = 50
PICKUP_DROP = 0.05
ENGAGEMENT_DROP = 0.05
HALLUCINATION_RATE = 0.05
Z_MIN = 2.5            # one-sided z; about 0.6% false alarms per check when nothing changed
RECENT_HOURS = 4       # wider window = more power but slower reaction


def sim_now(connection):
    row = connection.execute("SELECT MAX(bucket_start) FROM workflow_metrics").fetchone()
    return datetime.fromisoformat(row[0]) if row and row[0] else None


def _sum_window(connection, workflow_id, after, up_to):
    return connection.execute(
        """
        SELECT SUM(dials) AS dials, SUM(connected) AS connected,
               SUM(engaged) AS engaged, SUM(hallucination_flags) AS hallucination_flags
        FROM workflow_metrics
        WHERE workflow_id = ? AND bucket_start > ? AND bucket_start <= ?
        """,
        (workflow_id, after.isoformat(), up_to.isoformat()),
    ).fetchone()


def recent_metrics(connection, workflow_id, hours=RECENT_HOURS):
    now = sim_now(connection)
    return _sum_window(connection, workflow_id, now - timedelta(hours=hours), now)


def baseline_metrics(connection, workflow_id, hours=24, width=RECENT_HOURS):
    now = sim_now(connection)
    end = now - timedelta(hours=hours)          # same hours of the day, one day earlier
    return _sum_window(connection, workflow_id, end - timedelta(hours=width), end)


def z_gap(good_hits, good_n, bad_hits, bad_n):
    """Two-proportion z: how many standard errors higher the 'good' rate is than the 'bad' rate."""
    if good_n <= 0 or bad_n <= 0:
        return None
    pooled = (good_hits + bad_hits) / (good_n + bad_n)
    se = math.sqrt(pooled * (1 - pooled) * (1 / good_n + 1 / bad_n))
    return None if se == 0 else (good_hits / good_n - bad_hits / bad_n) / se


def detect_workflow_issues(connection, workflow_id):
    if sim_now(connection) is None:
        return []
    r, b = recent_metrics(connection, workflow_id), baseline_metrics(connection, workflow_id)
    rd, rc, re, rh = (r["dials"] or 0), (r["connected"] or 0), (r["engaged"] or 0), (r["hallucination_flags"] or 0)
    bd, bc, be, bh = (b["dials"] or 0), (b["connected"] or 0), (b["engaged"] or 0), (b["hallucination_flags"] or 0)
    alerts = []

    if rd >= MIN_DIALS and bd >= MIN_DIALS:                      # pickup = connected / dials
        z = z_gap(bc, bd, rc, rd)
        if z is not None and z >= Z_MIN and bc / bd - rc / rd >= PICKUP_DROP:
            alerts.append({"type": "pickup_degradation", "workflow_id": workflow_id, "z": round(z, 2),
                           "recent_pickup_rate": rc / rd, "baseline_pickup_rate": bc / bd,
                           "recent_dials": rd, "baseline_dials": bd, "dials": rd})

    if rc >= MIN_CONNECTED and bc >= MIN_CONNECTED:               # engagement = engaged / connected
        z = z_gap(be, bc, re, rc)
        if z is not None and z >= Z_MIN and be / bc - re / rc >= ENGAGEMENT_DROP:
            alerts.append({"type": "engagement_degradation", "workflow_id": workflow_id, "z": round(z, 2),
                           "recent_engagement_rate": re / rc, "baseline_engagement_rate": be / bc,
                           "recent_connected": rc, "baseline_connected": bc, "connected": rc})

        z = z_gap(rh, rc, bh, bc)                                 # positive when the recent rate is higher
        if z is not None and z >= Z_MIN and rh / rc >= HALLUCINATION_RATE:
            alerts.append({"type": "high_hallucination_rate", "workflow_id": workflow_id, "z": round(z, 2),
                           "hallucination_rate": rh / rc, "baseline_rate": bh / bc,
                           "connected": rc, "hallucination_flags": rh})
    return alerts

































# from .audit import record_audit
# from datetime import datetime, timedelta


# MIN_DIALS = 200
# MIN_CONNECTED = 50
# PICKUP_DROP = 0.05
# ENGAGEMENT_DROP = 0.05
# HALLUCINATION_RATE = 0.05


# def sim_now(connection):
#     row = connection.execute("SELECT MAX(bucket_start) FROM workflow_metrics").fetchone()
#     return datetime.fromisoformat(row[0]) if row and row[0] else None


# def _sum_window(connection, workflow_id, after, up_to):
#     return connection.execute(
#         """
#         SELECT SUM(dials) AS dials, SUM(connected) AS connected,
#                SUM(engaged) AS engaged, SUM(hallucination_flags) AS hallucination_flags
#         FROM workflow_metrics
#         WHERE workflow_id = ? AND bucket_start > ? AND bucket_start <= ?
#         """,
#         (workflow_id, after.isoformat(), up_to.isoformat()),
#     ).fetchone()



# def recent_metrics(connection, workflow_id: str, hours: int = 2):
#     now = sim_now(connection)
#     return _sum_window(connection, workflow_id, now - timedelta(hours=hours), now)


# def baseline_metrics(connection, workflow_id: str, hours: int = 24):
#     now = sim_now(connection)
#     end = now - timedelta(hours=hours)          # the same two hours, one day earlier
#     return _sum_window(connection, workflow_id, end - timedelta(hours=2), end)


# def safe_rate(numerator: int, denominator: int) -> float | None:
#     if denominator <= 0:
#         return None

#     return numerator / denominator


# def detect_workflow_issues(connection, workflow_id: str) -> list[dict]:
#     if sim_now(connection) is None:
#         return []
    
#     alerts = []

#     recent = recent_metrics(connection, workflow_id)
#     baseline = baseline_metrics(connection, workflow_id)

#     recent_dials = recent["dials"] or 0
#     recent_connected = recent["connected"] or 0
#     recent_engaged = recent["engaged"] or 0
#     recent_hallucinations = recent["hallucination_flags"] or 0

#     baseline_dials = baseline["dials"] or 0
#     baseline_connected = baseline["connected"] or 0
#     baseline_engaged = baseline["engaged"] or 0
#     baseline_hallucinations = baseline["hallucination_flags"] or 0

#     recent_pickup = safe_rate(recent_connected, recent_dials)
#     baseline_pickup = safe_rate(baseline_connected, baseline_dials)

#     if (
#         recent_dials >= MIN_DIALS
#         and baseline_dials >= MIN_DIALS
#         and recent_pickup is not None
#         and baseline_pickup is not None
#         and baseline_pickup - recent_pickup >= PICKUP_DROP
#     ):
#         alerts.append(
#             {
#                 "type": "pickup_degradation",
#                 "workflow_id": workflow_id,
#                 "recent_pickup_rate": recent_pickup,
#                 "baseline_pickup_rate": baseline_pickup,
#                 "recent_dials": recent_dials,
#                 "baseline_dials": baseline_dials,
#             }
#         )

#     recent_engagement = safe_rate(recent_engaged, recent_connected)
#     baseline_engagement = safe_rate(baseline_engaged, baseline_connected)

#     if (
#         recent_connected >= MIN_CONNECTED
#         and baseline_connected >= MIN_CONNECTED
#         and recent_engagement is not None
#         and baseline_engagement is not None
#         and baseline_engagement - recent_engagement >= ENGAGEMENT_DROP
#     ):
#         alerts.append(
#             {
#                 "type": "engagement_degradation",
#                 "workflow_id": workflow_id,
#                 "recent_engagement_rate": recent_engagement,
#                 "baseline_engagement_rate": baseline_engagement,
#                 "recent_connected": recent_connected,
#                 "baseline_connected": baseline_connected,
#             }
#         )

#     recent_hallucination_rate = safe_rate(
#         recent_hallucinations,
#         recent_connected,
#     )

#     if (
#         recent_connected >= MIN_CONNECTED
#         and recent_hallucination_rate is not None
#         and recent_hallucination_rate >= HALLUCINATION_RATE
#     ):
#         alerts.append(
#             {
#                 "type": "high_hallucination_rate",
#                 "workflow_id": workflow_id,
#                 "hallucination_rate": recent_hallucination_rate,
#                 "connected": recent_connected,
#                 "hallucination_flags": recent_hallucinations,
#             }
#         )

#     return alerts