# Product analytics

Every business event the services publish (the same ones they use to talk
to each other) also flows SNS → Kinesis Firehose → S3, partitioned by day,
and is queryable in Athena as `cappy_events`
(`infra/platform/analytics.tf`).

- Events carry ids, never names or emails, so no client SDK and no
  consent banner are needed.
- They are kept for two years and move to cold storage after 90 days.

`data` is the event's JSON. Examples:

```sql
-- The booking funnel, last 7 days
SELECT json_extract_scalar(data, '$.to') AS status, count(*) AS n
FROM cappy_events
WHERE type = 'booking.status_changed' AND dt >= cast(current_date - interval '7' day AS varchar)
GROUP BY 1 ORDER BY n DESC;

-- Owner response: how many requests were accepted, declined or lapsed
SELECT json_extract_scalar(data, '$.to') AS outcome, count(*) AS n
FROM cappy_events
WHERE type = 'booking.status_changed' AND json_extract_scalar(data, '$.from') = 'requested'
GROUP BY 1;

-- Money: captured and paid out per day (cents)
SELECT dt, type, sum(cast(json_extract_scalar(data, '$.amount') AS bigint)) AS cents
FROM cappy_events
WHERE type IN ('payment.captured', 'payment.payout_sent', 'payment.refunded')
GROUP BY 1, 2 ORDER BY 1, 2;

-- Trust and safety: reports and decisions per week
SELECT date_trunc('week', date(dt)) AS week, type, count(*) AS n
FROM cappy_events
WHERE type IN ('moderation.report_received', 'moderation.decision')
GROUP BY 1, 2 ORDER BY 1;

-- DSA Art. 24(2): average monthly active recipients (anyone whose id appears
-- in an event of the month, on either side). /admin/dsa-stats gives a lower
-- bound from bookings alone; this is the number for the report.
SELECT substr(dt, 1, 7) AS month, count(DISTINCT person) AS active
FROM (
  SELECT dt, json_extract_scalar(data, '$.requesterId') AS person FROM cappy_events
  UNION ALL SELECT dt, json_extract_scalar(data, '$.ownerId') FROM cappy_events
  UNION ALL SELECT dt, json_extract_scalar(data, '$.reporterId') FROM cappy_events
)
WHERE person IS NOT NULL
GROUP BY 1 ORDER BY 1;
```

Marketplace health to watch every week:
- **Liquidity**: share of requests accepted.
- **Time to accept**: how long owners take.
- **Cancellation rate** on each side.
- **Dispute rate**: keep it under 0.75% of charges (Stripe's threshold).
- **Repeat renters.**
