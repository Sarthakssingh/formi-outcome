# Grade report — public_02_incidents

## Outcomes vs baseline (no-op controller)

| workflow | conclusion rate | Δ | pickup | Δ | engagement | Δ | engagement gap captured | hallucinated calls (base) |
|---|---|---|---|---|---|---|---|---|
| ks_cancel | 0.268 | +8.3% | 0.203 | +10.6% | 0.462 | -3.0% | 0% | 365 (330) |
| nw_kyc | 0.374 | -0.3% | 0.242 | -0.1% | 0.591 | -0.2% | 0% | 29 (31) |
| nw_renewal | 0.435 | +2.0% | 0.264 | +1.0% | 0.553 | +0.8% | 5% | 59 (55) |
| ALL | 0.346 | +3.6% | 0.232 | +4.5% | 0.524 | -1.2% | 2% | 453 (416) |

## Changes applied by the controller

3 applied — beneficial: 3

- ks_cancel v2 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.183 → **beneficial**
- ks_cancel v3 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.155 → **beneficial**
- ks_cancel v4 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.049 → **beneficial**

## Governance

```
{
  "approval_requests": 0,
  "decisions": {
    "expired": 0
  },
  "rejection_reasons": {},
  "applied_via_approval": 0,
  "auto_applied": 3,
  "auto_apply_rejected": 0,
  "apply_conflicts": 0,
  "lapsed": 0,
  "peak_requests_per_24h": {}
}
```

## Incidents

```
[
  {
    "type": "did_flagged",
    "workflow": "ks_cancel",
    "at": "D2 10:00",
    "flagged_did_share_by_day": {
      "2": 0.149,
      "3": 0.05,
      "4": 0.047,
      "5": 0.052,
      "6": 0.053,
      "7": 0.048,
      "8": 0.049,
      "9": 0.049
    }
  },
  {
    "type": "supervisor_edit",
    "workflow": "ks_cancel",
    "at": "D3 11:30",
    "mttr_minutes": null,
    "fixed_by": null
  },
  {
    "type": "supervisor_edit",
    "workflow": "nw_renewal",
    "at": "D5 15:00"
  }
]
```

## Decaying variants — share of in-population calls still on the variant, by day after onset

```
{}
```

Credits used: 0 · validation runs: 0 · LLM fix calls: 0