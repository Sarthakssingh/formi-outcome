import copy
import hashlib
import json
from collections import defaultdict
from datetime import timedelta
from .audit import record_audit
from .detectors import sim_now, z_gap
WINDOW_HOURS = 4        # compare in the last 4 simulated hours
MIN_ID_DIALS = 150      # a caller ID needs this many dials in the window to be judged
Z_ID = 3.0              # one-sided z against the other caller IDs in the same hours
MIN_GAP = 0.06          # and at least 6 points lower pickup in absolute terms
CONFIRM_TICKS = 2       # flagged on this many consecutive checks before acting
FLOOR = 0.05            # keep a small probe share on a bad ID so a recovery stays visible
SAFETY = 0.95           # use 95% of max_shift so rounding never trips the policy check
_streak = defaultdict(int)   # (workflow, caller_id) -> consecutive flagged checks
_refused = set()             # (workflow, version) already reported, to avoid log spam
def caller_id_stats(connection, workflow_id, now):
    after = (now - timedelta(hours=WINDOW_HOURS)).isoformat()
    stats = defaultdict(lambda: [0, 0])
    rows = connection.execute(
        "SELECT variant_key, dials, connected FROM variant_metrics "
        "WHERE workflow_id = ? AND bucket_start > ? AND bucket_start <= ?",
        (workflow_id, after, now.isoformat()),
    )
    for variant_key, dials, connected in rows:
        cid = json.loads(variant_key).get("caller_id")
        if cid:
            stats[cid][0] += dials
            stats[cid][1] += connected
    return stats
def find_bad_ids(stats):
    bad = {}
    for cid, (dials, conn) in stats.items():
        if dials < MIN_ID_DIALS:
            continue
        sib_dials = sum(d for k, (d, c) in stats.items() if k != cid)
        sib_conn = sum(c for k, (d, c) in stats.items() if k != cid)
        if sib_dials < MIN_ID_DIALS:
            continue
        z = z_gap(sib_conn, sib_dials, conn, dials)
        gap = sib_conn / sib_dials - conn / dials
        if z is not None and z >= Z_ID and gap >= MIN_GAP:
            bad[cid] = {"z": round(z, 2), "pickup": round(conn / dials, 4), "dials": dials,
                        "siblings_pickup": round(sib_conn / sib_dials, 4), "siblings_dials": sib_dials}
    return bad
def shift_away(dist, bad_ids, step):
    total = sum(dist.values())
    dist = {k: v / total for k, v in dist.items()}
    healthy = {k: v for k, v in dist.items() if k not in bad_ids and v > 0}
    candidates = [k for k in bad_ids if dist.get(k, 0) > FLOOR + 1e-9]
    if not healthy or not candidates:
        return None
    worst = max(candidates, key=lambda k: dist[k])
    take = min(dist[worst] - FLOOR, step)
    if take <= 1e-9:
        return None
    new = dict(dist)
    new[worst] -= take
    hsum = sum(healthy.values())
    for k, v in healthy.items():
        new[k] += take * v / hsum
    return {k: round(v, 4) for k, v in new.items()}
def tv_distance(a, b):
    keys = set(a) | set(b)
    return 0.5 * sum(abs(a.get(k, 0) - b.get(k, 0)) for k in keys)
def run(client, connection, workflows):
    now = sim_now(connection)
    if now is None:
        return
    for wid, wf in workflows.items():
        policy = wf.get("governance", {}).get("auto_apply", {})
        if not policy.get("enabled") or "caller_id" not in policy.get("allowed_dims", []):
            continue                      # needs the approval path (not built yet)
        stats = caller_id_stats(connection, wid, now)
        bad = find_bad_ids(stats)
        for key in list(_streak):
            if key[0] == wid and key[1] not in bad:
                _streak[key] = 0
        confirmed = {}
        for cid, ev in bad.items():
            _streak[(wid, cid)] += 1
            if _streak[(wid, cid)] >= CONFIRM_TICKS:
                confirmed[cid] = ev
        if not confirmed:
            continue
        live = client.workflow_config(wid)          # always start from the LIVE config
        cfg, version = live["config"], live["version"]
        new_cfg = copy.deepcopy(cfg)
        step = max(policy.get("max_shift", 0) * SAFETY, 0)
        changed = {}
        for key, alloc in new_cfg.get("allocations", {}).items():
            dist = alloc.get("caller_id")
            if not dist:
                continue
            new_dist = shift_away(dist, set(confirmed), step)
            if new_dist and tv_distance(dist, new_dist) <= policy.get("max_shift", 0):
                alloc["caller_id"] = new_dist
                changed[key] = {"before": dist, "after": new_dist}
        if not changed:
            continue
        proposal_id = "cid-" + hashlib.sha1(
            json.dumps([wid, version, changed], sort_keys=True).encode()).hexdigest()[:16]
        evidence = {"flagged": confirmed, "window_hours": WINDOW_HOURS, "changes": changed,
                    "base_version": version, "sim_time": now.isoformat()}
        status, body = client.put_config(wid, {
            "proposal_id": proposal_id, "base_version": version, "proposed_config": new_cfg,
            "rationale": "Caller ID pickup is significantly below the other caller IDs in the same hours: "
                         + ", ".join(f"{c} {e['pickup']:.0%} vs {e['siblings_pickup']:.0%}" for c, e in confirmed.items()),
            "evidence": evidence,
        })
        with connection:
            if status == 200:
                record_audit(connection, "CONFIG_AUTO_APPLIED", workflow_id=wid, subject_type="caller_id",
                             subject_id=proposal_id, reason="caller ID collapse: traffic shifted within policy",
                             evidence={**evidence, "response": body})
                record_audit(connection, "SUPERVISOR_NOTICE", workflow_id=wid, subject_type="caller_id",
                             subject_id=proposal_id,
                             reason="Caller ID traffic reduced on " + ", ".join(sorted(confirmed))
                                    + " (pickup far below the other IDs). Customers hear no change.",
                             evidence={"proposal_id": proposal_id})
            elif status == 409:
                pass                       # stale base (a supervisor edit) or duplicate id: retry next tick
            elif (wid, version) not in _refused:
                _refused.add((wid, version))
                record_audit(connection, "AUTO_APPLY_REFUSED", workflow_id=wid, subject_type="caller_id",
                             subject_id=proposal_id, reason=f"HTTP {status}", evidence={"response": body, **evidence})