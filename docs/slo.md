# Service level objectives

These are the targets for users' journeys, measured at the load balancer
(what users actually get). An alarm pages when the error budget is burning
too fast. The method is the Google SRE workbook's: SLOs per journey,
multi-window burn-rate alerts, and an error-budget policy.

| Journey | SLI (good events / valid events) | Objective (28 days) | Budget |
|---|---|---|---|
| **Browse and search** | `GET /api/search`, `/api/listings/*`, `/api/browse/*`, `/api/matches` answered with a non-5xx in under 800 ms | 99.5% | 3 h 22 m |
| **Book** | `POST /api/bookings` answered with a non-5xx (a 409 "taken" counts as good) | 99.9% | 40 m |
| **Owner answers** | `POST /api/bookings/*/accept`, `/decline` answered with a non-5xx | 99.9% | 40 m |
| **Money moves** | `booking.status_changed` handled by payments within 15 minutes (queue age), with nothing in its DLQ | 99.95% | 20 m |
| **Mail arrives** | Notifications' queue age under 10 minutes | 99.5% | 3 h 22 m |

## Alerting

For each objective, alarm when the budget burns **14.4× faster than
sustainable over 1 h and 5 min** (2% of the monthly budget in an hour; this
pages), or **6× over 6 h and 30 min** (this opens a ticket). The existing
alarms are the first pieces: 5xx rate, p99 latency, queue age and dead
letters (`infra/platform/observability.tf`). Burn-rate alarms exist for one
API-wide objective (99.5% non-5xx, `observability.tf`); the per-journey
objectives above, with their latency thresholds, are not alarmed separately
yet, and queue-age alarms fire at 5 minutes for every queue (stricter than the
15- and 10-minute SLIs). Per-journey burn alarms: task T-35c.

## Error-budget policy

- **Budget left**: ship as usual.
- **Budget spent for the 28 days**: only reliability fixes and security
  patches ship until it recovers. The postmortem for the incident that spent
  it names the fix.
- **One incident spends more than 20%**: it gets a written postmortem within
  five working days.
