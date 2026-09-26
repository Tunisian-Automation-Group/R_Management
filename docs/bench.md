# Search benchmarks

`make bench` (script: `backend/services/catalog/bench/candidates.py`) builds a
throwaway database on the local Postgres with N synthetic listings, 3 windows
each over the next month, spread over the demo districts. It times each query
as the mean of 10 runs after one warm-up, then drops the database. A laptop is
not Aurora: these numbers compare changes, they don't size production (L-5).

| Date | Commit | Listings | Candidates, 25 km, 7 days | Candidates, 500 km, 30 days | Text "machine 4242" | Text "saw" in Berlin | Conditions |
|---|---|---|---|---|---|---|---|
| 2026-09-25 | T-10 | 100k | 16.8 ms | 21 ms | — | — | nearest-first districts (was 36 / 47 ms) |
| 2026-09-26 | 61b15b8 | 100k | 10.6 ms | 9.8 ms | — | — | reported by the builder; its script was not kept |
| 2026-09-26 | 61b15b8 + working tree | 100k | 14.7 ms | 20.2 ms | 6.1 ms | 1.8 ms | this script, with the full stack and a browser test running on the same laptop |

The two 2026-09-26 rows differ by load on the machine, not by code: same
query, same index. Compare rows only when taken the same way; add a row with
the date, commit and conditions whenever the search code changes.
