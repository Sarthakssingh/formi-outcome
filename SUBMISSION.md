# Outcome-First Agent Loop — Submission

**Name:** Sarthak SIkriwal · **Date:** 2026-11-11 · **Hours actually spent (be honest):** 16 · **Language / storage:** Python 3 + SQLite (single file)

---

## 0. TL;DR

- The controller ingests simulator events (idempotent, restartable), keeps pickup / engagement / hallucination metrics, detects problems with significance tests (not raw thresholds), and **automatically fixes a collapsed caller ID** inside the workflow's auto-apply policy, with an audit trail.
- public_02: `ks_cancel` conclusion rate **+8.3%**, pickup **+10.6%** vs. the no-op baseline; all 3 applied changes graded *beneficial*. public_01: **0 changes**, every delta +0.0% (it does nothing when nothing is wrong).
- Kill/restart demonstrated (killed twice mid-run; final state identical to an uninterrupted run).
- **Deliberately not built:** cohorts, experiments/winner promotion/decay, the approval path, the hallucination (bad-prompt) response, supervisor view. The bad supervisor prompt on `ks_cancel` is detected but **not fixed**.

## 1. Assumptions

1. The simulator contract (`docs/SIMULATOR.md`) and the policies returned by `GET /workflows` are the source of truth over any memo.
2. Cadence, dialling windows and capacity are business-owned; the controller never touches them.
3. A caller ID is "bad" if its pickup is materially below the *other caller IDs in the same hours*. Comparing in the same hours removes hour-of-day effects and needs no history.
4. Pickup and engagement are never blended in any output.
5. Evidence is only what actually happened: every metric is built from call events and the variant recorded on each call, never from a proposed or intended config.
6. Starting from the live config on every change is enough to avoid undoing supervisor edits.
7. The hallucination flag is noisy (the contract says it has false positives and negatives), so alerts use a significance test against a baseline, not a fixed cut-off.
8. SQLite is acceptable as the single store for this submission; production would use the Postgres Platform already runs.

## 2. Scope decisions

| # | Capability | Built / Partial / Cut | Why | What it would take to finish |
|---|---|---|---|---|
| C1 | Event ingestion | **Partial** | Chunk cursor + insert keyed by `event_id` (idempotent). Row-by-row writes; load numbers in §8 | Batched inserts, compact columns, parallel workers |
| C2 | Shared cohort object | Cut | Needs experiments to be worth it | Define cohort spec once; use in detection, experiments, view |
| C3 | History bootstrap | Cut | Detection day 1 has no baseline as a result | Ingest history chunks into the same tables |
| C4 | Call-time optimisation | Cut | Needs history + experiments | Per-cohort hour weights from history; per-person later |
| C5 | Caller-ID health | **Built (partial)** | Clearest incident, permitted auto-apply, reversible, measurable | Recovery logic; exploring unused IDs safely; approval path for `nw_kyc` |
| C6 | Welcome/voice experiments | Cut | Largest piece; risky to do tired | Allocation engine + two-proportion tests + multiple-comparison control |
| C7 | Promotion / decay / rollback | Cut | Depends on C6 | Post-promotion monitor against pre-promotion baseline |
| C8 | Hallucination response | **Partial (detect only)** | Detection works; response needs C9 approval path | suggest-fixes → validation → approval with evidence → verify engagement |
| C9 | Governance client | **Partial** | Only the auto-apply path (`PUT /config`) with `base_version`, 409/403 handling | Approval lifecycle, batching, approver-hour timing, expiry/lapse/stale re-proposal |
| C10 | Honest impact scores / dry runs | Cut | No approval requests are sent yet | Compute from per-cohort affected leads + historical replay |
| C11 | Supervisor view | Cut | `SUPERVISOR_NOTICE` audit rows are the seed | One read-only endpoint over the audit table |
| C12 | Audit / "why" store | **Partial** | `audit_events` table with evidence JSON; query in §10 | Link per-call variants to proposal ids in one view |
| C13 | Crash recovery | **Built** | Demonstrated in §9 | Make events + metrics + cursor one transaction |
| C14 | Loop observability | Cut | Not needed to score outcomes | Ingest lag, decisions/hour, credit burn |
| C15 | Fairness across tenants | Cut | No contention at this scale | Per-tenant budgets for credits and approver requests |

**Principle:** one change that is permitted, reversible, evidenced and measurable beats several half-working ones. I first made detection trustworthy (491 → 9 alerts on public_02), then acted only where policy allows acting without a human, and cut everything that would need an approver round-trip I couldn't test properly.

## 3. Stakeholders

### 01 — Nikhil Rao, VP Sales
- **Accepted:** speed matters. The caller-ID incident is fixed within about two simulated hours of onset by auto-apply where the policy allows it.
- **Declined:** a single blended score. Pickup and engagement are reported separately (Product's definition, and the objective/guardrail structure in the contract).
- **Wrong against the policy:**
  - *"Kestrel has auto-apply for everything"* — `ks_cancel` auto-apply covers only schedule, caller_id, welcome_message and voice, with `max_shift` 0.2. Prompt changes and cohorts are excluded.
  - *"Northwind is fine with auto-apply on KYC"* — `nw_kyc` has auto-apply **disabled** (`enabled: false`, no allowed dims). `nw_renewal` allows only schedule and caller_id.
  - *"Persuasive prompt wherever available"* — P4 ("freer objection handling") exists only in `nw_renewal` and `ks_cancel`; prompt changes always need approval plus a validation run with pass rate ≥ 0.97.
- **Reply:** "Nikhil — the summit number will be two lifts per client, pickup and engagement, never blended; that's how the product defines them. On public_02 Kestrel's conversion rate is up 8.3% from an automatic caller-ID fix within about two hours. Auto-apply is narrower than you've been told: not for KYC at all, and never for prompts. I'm not rolling out the persuasive prompt: it loosens objection handling, which is the hallucination risk, and it needs validation and a named approval. Happy to show you the audit trail on stage instead."

### 02 — Meera Iyer, Head of Compliance (Northwind)
- **Accepted:** nothing a customer hears (opening line, voice, script) changes without a human approval — the controller never auto-applies welcome/voice/prompt on Northwind; script changes need validation evidence; every call event records `config_version`, `cohort_id` and `variant`, and the controller stores them (`raw_events`), so "what did this customer hear and why" is answerable from our store; operational changes are logged for the weekly summary (`SUPERVISOR_NOTICE` rows).
- **Not delivered:** the approval path itself (C9). Until built, the controller takes **no** action on Northwind except caller-ID rotation on `nw_renewal`.
- **Wrong / imprecise against the policy:** she says timing and caller-ID rotation are covered for renewal *and* KYC. Only `nw_renewal` has that permission; `nw_kyc` has auto-apply off, so any KYC change needs approval. KYC approvers also work 10:00–18:00 with latency up to 8 hours, and its agent-facing config applies only to the *next* campaign (`next_campaign_only`).
- **Reply:** "Meera — agreed on all five conditions. Customer-facing changes (voice, opening line, script) will only ever go through a named approval with validation evidence attached; the controller cannot apply them itself. Caller-ID and timing changes are limited to the renewal workflow, where your policy allows it; KYC needs approval for everything. Every call records the config version and variant it used, so we can answer an IRDAI question within a day. You'll get a weekly list of operational changes."

### 03 — Kabir Menon, Platform & SRE
- **Accepted:** kill/restart test (done, §9); idempotency (ingest keyed by `event_id`; deterministic proposal ids); no new stateful infrastructure (one SQLite file; production would use the existing Postgres).
- **Not delivered:** loop health metrics (C14); paging rules. No alert currently pages anyone — alerts go to the audit table only.
- **Wrong claims:** none found.
- **Reply:** "Kabir — kill/restart is demonstrated: killed twice mid-run, the final state matched an uninterrupted run exactly. Ingest is idempotent by event id and changes use deterministic proposal ids, so a restart can't apply anything twice. State is a single SQLite file, no new infrastructure; I'd move it to your Postgres. Load: about 56 seconds per simulated day on public_03 (8 CPUs, 8 GB), against your 10-minute target; the database grew to 2.5 GB over 5 days. Known gap: events, metrics and cursor are written in separate transactions; I'd merge them first. No alert should page yet."

### 04 — Anita Desai, Operations Supervisor (Kestrel)
- **Accepted:** her prompt edits are never undone — the controller never changes `prompt_version` itself and always builds a change from the *live* config with `base_version`. Her "one screen" is not built; `SUPERVISOR_NOTICE` rows are what it would show. Her lesson (a "safe" prompt that kills engagement) is why validation, which only measures safety, must be followed by an engagement check after any prompt change.
- **Limited:** she asked to be told *before* anything changes. Auto-apply cannot notify beforehand, so for caller-ID rotation (operational, permitted, customer hears no difference) I notify at the moment of change. Voice and welcome changes at Kestrel are also auto-appliable by policy; I would still route them through approval voluntarily. Her limit of 2 requests/day and none before 11:00 is stricter than the policy's 4 per 24h; I'd honour hers.
- **Wrong claims:** none.
- **Reply:** "Anita — your prompt changes stay yours: the controller never edits prompts on its own and always works from your current config. Right now it changes only which caller ID Formi dials from; if one number dies it moves traffic away within an hour or two and logs a note for you. Customers hear nothing different. Anything customers do hear (voice, opening line, script) would come as one batched request, after 11:00, at most twice a day. Your P2 edit is being flagged for hallucinations; I'll bring you evidence, not an override."

### 05 — Tara Kulkarni, Head of Product
- **Accepted:** pickup and engagement are never blended; only what actually happened counts as evidence; an expired proposal is a rejection and gets re-queued with fresh data under a new id (the contract rejects a reused id); a winner would update only its own workflow.
- **Not delivered:** the shared cohort object (C2), impact scores (C10), per-person call time, the consolidated supervisor view. Of her three "P0" items I chose **caller-ID health** (built, partial) because it was the only one that is both permitted for auto-apply and supported by a visible incident in public_02.
- **Open questions she asked:** minimum sample and window. Caller-ID: ≥150 dials per ID in a 4-hour window, z ≥ 3 against the other IDs, ≥ 6 points lower, confirmed on 2 consecutive checks. Cost: slower reaction (about 30–60 minutes after enough data) in exchange for roughly 0.1% false alarms per check.
- **Wrong claims:** none; the contradiction is that three items cannot all be P0.
- **Reply:** "Tara — pickup and engagement are separate everywhere, and only calls that happened count as evidence. I couldn't do all three P0 items. I built caller-ID health because it is permitted for auto-apply and public_02 shows the incident. Per-person call time and the supervisor view are not built; the audit notes that would feed the view exist. Caller-ID rule: at least 150 dials per ID, 4-hour window, significantly lower than the other IDs, confirmed twice. That trades about 30–60 minutes of reaction time for very few false alarms."

### 06 — Aryamann, CTO
- **Accepted:** outcomes that can be explained over bigger ones that can't; trust the contract over memos (done — see claims corrected above); choose and say no.
- **Said no to:** experiments, winner promotion/decay, the approval path, per-person timing, the supervisor view. Reason: each needs more testing than I could give it without risking harm to a cohort; "an improvement that hurts a cohort is worth less than nothing".
- **Reply:** "I built one thing end to end and kept it safe: detect a failing caller ID with a significance test, shift traffic within policy, log why, survive a restart. I did not build the learning loop, the approval path or the supervisor view, and the bad supervisor prompt on Kestrel is detected but not fixed. First two weeks in production: approval path and prompt-fix flow, then experiments."

## 4. Architecture

```
Simulator (HTTP)
   │  /events/chunks (listed after our cursor)  /workflows  /workflows/{id}/config
   ▼
Client ──► ingest ──► raw_events (PK event_id, skip if present)
              │            + ingest cursor (last_event_id, last_chunk)
              ▼
        metrics: workflow_metrics, variant_metrics   (hourly buckets, simulated time)
              ▼
        detectors (z-test vs same hours yesterday)  ──► audit_events (DETECTION_ALERT, 6h cooldown)
              ▼
        caller_id.run: per-caller-ID pickup vs sibling IDs, same hours
              ▼  confirmed on 2 consecutive 15-minute checks
        PUT /workflows/{id}/config  (live config + base_version, step ≤ 0.95 × max_shift)
              ▼
        audit_events (CONFIG_AUTO_APPLIED, SUPERVISOR_NOTICE, AUTO_APPLY_REFUSED)
```

- **State** lives in one SQLite file: `raw_events`, `workflow_metrics`, `variant_metrics`, `audit_events`, the ingest cursor.
- **On restart:** read the cursor, list every chunk after it from the simulator (not just those in an `advance` reply), ingest, continue. Only the 2-check confirmation counters and the alert cooldown are in memory and reset on restart.

## 5. The learning loop

**Not built.** What exists is detection and one corrective action.

- **Cohorts:** none. Metrics are per workflow and per variant. No fragmentation risk, but no segment-level learning.
- **Experiment design / winners / decay:** not built (C6, C7).
- **Detection windows:** current 4 hours vs the same 4 hours the previous day; one-sided two-proportion z ≥ 2.5 and a minimum effect of 5 points (pickup, engagement) or ≥ 5% rate (hallucination); minimum 200 dials / 50 connected.
- **Expected false-alarm rate:** on synthetic data with no real change, the earlier fixed-threshold rule fired on about 19–23% of checks; the z-gated rule gave 2 alerts over 84 checks (about 2%). On public_02 the real run went from 491 alerts to 9. These are my synthetic estimates, not measured on the hidden scenarios.
- **Caller ID:** comparison against sibling IDs in the same hours. The flagged ID keeps a 5% probe share so recovery stays visible. Not done: restoring an ID that recovers; exploring unused IDs (e.g. D3 on `ks_cancel`).
- **Guardrail KPI:** the caller-ID shift protects pickup (the guardrail of both Kestrel and Northwind-renewal). No check yet that engagement does not fall afterwards; the grader shows `ks_cancel` engagement −3.0% vs baseline, which I have not investigated and may be noise.

## 6. Governance

- **Implemented:** auto-apply only, only where `governance.auto_apply.enabled` and `caller_id` ∈ `allowed_dims`, never moving more than `max_shift` (uses 95%). Always reads the live config and sends `base_version`. HTTP 409 (stale base or duplicate id) → re-evaluated next tick; 403 → logged as `AUTO_APPLY_REFUSED` once per config version.
- **Supervisor edits mid-run:** never overwritten, because changes start from the live config. A supervisor edit between read and write returns 409 and is retried against the new version.
- **Not implemented:** the approval state machine (`pending → approved/rejected/expired → applied/lapsed`), batching under approver fatigue, timing against approver hours (10–19; KYC 10–18), the 2-hour apply window, impact score / affected leads / dry run. Design intent: poll approvals each tick, apply within the window, treat expiry as rejection and re-propose with fresh data under a new id.
- **Voluntary restraint:** even where policy permits (`ks_cancel` welcome/voice), customer-facing changes would go via approval.

## 7. Incidents (public_02)

Timeline (simulated time):

| When | What | Controller |
|---|---|---|
| D2 10:00 | `ks_cancel` caller ID D2 flagged: pickup ~25% → ~10% | Detected; 3 auto-applied steps (D2 share 50% → ~31% → ~12% → 5%) All three applied in the 11:00 hour on D2 (see §10). |
| D2–D9 | D2 share of calls | 14.9% on D2, then 5% every day after |
| D3 11:30 | Supervisor edits `ks_cancel` prompt to P2 ("adds payment-urgency language and benefit claims") | Hallucination alerts fire; **no fix applied** (`mttr_minutes: null`) |
| D5 15:00 | Supervisor edit on `nw_renewal` | Not handled |

- **Why 3 steps:** Kestrel's `max_shift` is 0.2, so one change can move at most 20 points of traffic.
- **Credits used:** 0 (no LLM or validation calls).
- **Intended prompt-fix flow (not built):** `suggest-fixes` (3 credits) → pick a candidate (some are worse than the problem; P5 "strict verbatim script" is the kind of fix that reduces hallucination but kills engagement) → validation run (n ≈ 1000, ≥ 0.97 pass, ⌈n/100⌉ credits) → approval request with `validation_run_id` as evidence → apply within 2 hours → verify engagement afterwards and roll back if it falls.
- **Hallucinated calls** are 365 vs 330 (+10.6%), matching the pickup increase — more answered calls, not a higher rate per call.

## 8. Scale

- **Measured on public_03_load** (5 simulated days; 8 logical CPUs, 8 GB RAM; the simulator ran on the same machine; the controller is a single process, so it uses about one core): total wall time **280 s**, about **56 s per simulated day** against the 10-minute target. Events ingested: **4,200,060** (about 15,000 events/sec). The SQLite file grew to **2.55 GB** (about 510 MB per simulated day, about 600 bytes per event). Peak memory: not measured. Under load the controller made **0** config changes and wrote **2** detection alerts.
- The wall time includes the simulator generating each tick, so the controller's own cost is lower.
- **What breaks first at 10×:** storage and write time. By linear extrapolation (not measured) a day would take about 9–10 minutes and grow the file by about 5 GB, because every event is written one row at a time as full JSON.
- **How I'd scale it:** batched inserts and compact columns first; then one worker process per workflow or tenant, each with its own cursor; Postgres in place of SQLite.

## 9. Reliability

- **Test:** public_02 with the controller killed twice mid-run (hard kill via `Stop-Process -Force`, at about simulated minutes 6,435 and 8,970), restarted each time, then run to completion.
- **Result:** `raw_events` = 137,035, identical to an uninterrupted run with the same 3 fixes (the earlier no-fix run had 137,032: the 3 extra events are the controller's own config changes). Call events = metrics dials (104,000 = 104,000). Exactly 3 `CONFIG_AUTO_APPLIED` rows, so a restart did not repeat any fix.
- **What can still be lost:** events, metrics and the cursor are written in separate transactions. A kill between saving events and updating metrics would lose those metrics (events already saved are skipped on restart). The two kills did not hit that window, so this is **not proven fixed** — it is a known weakness.
- **Idempotency:** ingest skips known `event_id`s; proposal ids are a hash of (workflow, base version, change), so a retry cannot double-apply; each change reads the live config first.
- **Simulator errors:** 4xx on config changes are handled (409 retried next tick; 403 logged). Network errors and 5xx are not retried — the process fails and a restart resumes from the cursor.

## 10. Audit & observability

"Why did `ks_cancel` change, what did we see, and what happened after?"

```sql
SELECT occurred_at, action, subject_type, reason,
       json_extract(evidence_json,'$.sim_time') AS sim_time,
       json_extract(evidence_json,'$.flagged')  AS flagged,
       json_extract(evidence_json,'$.changes')  AS changes
FROM audit_events
WHERE workflow_id = 'ks_cancel'
  AND action IN ('DETECTION_ALERT','CONFIG_AUTO_APPLIED','SUPERVISOR_NOTICE')
ORDER BY occurred_at;
```

Output on public_02 (`sim_time` is the simulated hour of the latest data when the change was applied; alert rows carry no simulated time, only wall-clock order):

```
(None, 'DETECTION_ALERT', 'pickup_degradation', None, None)
('2027-01-06T11:00:00+05:30', 'CONFIG_AUTO_APPLIED', 'caller_id', '{"D2":{"dials":472,"pickup":0.1589,"siblings_dials":428,"siblings_pickup":0.2617,"z":3.8}}', '{"D1":0.69,"D2":0.31}')
(None, 'SUPERVISOR_NOTICE', 'caller_id', None, None)
('2027-01-06T11:00:00+05:30', 'CONFIG_AUTO_APPLIED', 'caller_id', '{"D2":{"dials":499,"pickup":0.1563,"siblings_dials":501,"siblings_pickup":0.2595,"z":4.02}}', '{"D1":0.88,"D2":0.12}')
(None, 'SUPERVISOR_NOTICE', 'caller_id', None, None)
('2027-01-06T11:00:00+05:30', 'CONFIG_AUTO_APPLIED', 'caller_id', '{"D2":{"dials":511,"pickup":0.1546,"siblings_dials":589,"siblings_pickup":0.2581,"z":4.2}}', '{"D1":0.95,"D2":0.05}')
(None, 'SUPERVISOR_NOTICE', 'caller_id', None, None)
(None, 'DETECTION_ALERT', 'high_hallucination_rate', None, None)
(None, 'DETECTION_ALERT', 'pickup_degradation', None, None)
(None, 'DETECTION_ALERT', 'engagement_degradation', None, None)
```

Reading it: caller ID D2 had about 16% pickup against about 26% for the other ID (z between 3.8 and 4.2), so its share of traffic was cut 50% → 31% → 12% → 5% in three steps of at most 20 points each (Kestrel's `max_shift`). The alerts after the fixes were recorded but not acted on. Gap: detection alerts are not stamped with simulated time.

- Each applied change records the before/after weights, the evidence (pickup of the bad ID vs the others, z, dials) and the proposal id. The simulator's `config_changed` event in `raw_events` carries the same proposal id, which links the change to its reason.
- **IRDAI question (what did a given customer hear?):** each call event stores `config_version`, `cohort_id` and the variant; join to the config history for the version. Not built as a single query.
- **Alerts I would page on:** none currently page. Would page: ingest stopped advancing, repeated auto-apply refusals, credits near zero. Would not page: a single detection alert.

## 11. Results

**public_02**

| workflow | conclusion rate | Δ | pickup | Δ | engagement | Δ |
|---|---|---|---|---|---|---|
| ks_cancel | 0.268 | +8.3% | 0.203 | +10.6% | 0.462 | −3.0% |
| nw_kyc | 0.374 | −0.3% | 0.242 | −0.1% | 0.591 | −0.2% |
| nw_renewal | 0.435 | +2.0% | 0.264 | +1.0% | 0.553 | +0.8% |
| ALL | 0.346 | +3.6% | 0.232 | +4.5% | 0.524 | −1.2% |

3 changes applied, all *beneficial*. 0 approval requests, 0 refusals, 0 credits.

**public_01** — 0 changes applied; every delta +0.0%.

**Interpretation:**
- The gain is entirely from removing the dead caller ID. The `nw_kyc` / `nw_renewal` deltas are small and those workflows had no changes, so they are noise.
- No change was graded harmful.
- `ks_cancel` engagement is −3.0%. I have not explained it. If real, the likely cause is the bad P2 prompt left in place (engagement is that workflow's primary KPI), which is what the unbuilt prompt-fix flow would address.
- Engagement headroom captured is 0–5%: I did not attempt the learning loop.

## 12. Trade-offs & rejected alternatives

| Option | Why considered | Why rejected / what instead |
|---|---|---|
| Fixed thresholds on rate drops | Simple | 491 alerts on public_02; the rule fires by chance on ~20% of checks at these sample sizes. Replaced by z-tests. |
| Compare each ID against yesterday | Natural baseline | Needs history and is confounded by hour of day. Compare against sibling IDs in the same hours. |
| Switch off the bad ID in one step | Fastest | Policy `max_shift` (0.2 at Kestrel) forbids it; phased in steps instead. |
| Keep a 5% probe on the bad ID | Learn if it recovers | Costs ~5% × bad pickup of dials; kept, but restoring logic is not built. |
| Approval request for caller-ID change | Safer notice | Slower; policy permits auto-apply for this operational dimension. |
| SQLite vs Postgres | SRE prefers no new infrastructure | SQLite: zero setup, adequate at this scale; Postgres in production. |

## 13. Known weaknesses

- No learning loop: no experiments, winners, decay detection, cohorts or call-time optimisation.
- The bad supervisor prompt on `ks_cancel` is detected but not fixed (`mttr: null`); hallucinated calls are not reduced.
- No approval path, so nothing is done for `nw_kyc` or for any customer-facing dimension.
- A caller ID flagged once stays at 5% forever; no recovery logic; no exploration of unused IDs.
- Events, metrics and cursor are not one transaction; a kill in that window would lose metrics.
- History is not ingested, so workflow-level detectors have no baseline on day 1.
- 2-check confirmation counters and alert cooldown are in memory and reset on a restart.
- One global "latest simulated bucket" is used as "now" for all workflows; a workflow with a short last bucket may under-report.
- Per-event writes will not scale past about 6× the load scenario.
- `ks_cancel` engagement −3.0% unexplained.
- Few automated tests; most evidence comes from end-to-end runs.

## 14. If this went to production at Formi next month

1. Wrap events, metrics and cursor in one transaction; add batched writes; run the load test on production-like hardware.
2. Build the approval client (lifecycle, batching, approver hours, apply window, stale re-proposal) with Anita's two-per-day, after-11:00 rule as a per-tenant setting.
3. Build the hallucination response: suggest → validate → request approval with evidence → verify engagement → roll back.
4. Add the supervisor read-only view and the weekly operational-changes summary Northwind asked for.
5. Add loop health metrics and the three alerts worth paging on.
6. Ingest history and add recovery for flagged caller IDs.
7. Only then: experiments on welcome message and voice with sample-size rules and multiple-comparison control.