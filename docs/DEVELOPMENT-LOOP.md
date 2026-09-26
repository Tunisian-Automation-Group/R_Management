# How we keep developing Cappy with agents

This is the playbook. A new session reads `CLAUDE.md`, then `docs/PLAN.md`
"Resume here", then this file, and starts the next round. The goal stays in
[`GOAL.md`](GOAL.md) (items 1–19). The loop stops when
[`READINESS.md`](READINESS.md) says GO for the first market (DE/AT/CH) and the
only open blockers are the owner's.

## 1. One round

Each round runs these steps in order. The steps inside each numbered line run in
parallel.

1. **Find:**
   - a **verifier** walks every tester script in [`GUIDE.md`](GUIDE.md) Part A,
     on the web version (desktop) and the app version (390 px), in EN/DE/FR,
     light and dark, and writes `## Verification round N (VN)` into
     [`TASKS.md`](TASKS.md);
   - a **UX reviewer** scores the app against best-in-class apps and the
     `cappy-ui` rulebook and adds UX-n tasks;
   - when needed, a **research** agent (law, markets, security, stores) adds tasks
     with sources in `docs/research/`.
2. **Build:** one **backend** fork and one **web** fork, each on its own
   files. Big visual work goes in a **worktree** fork (its own dev server on
   :5174), and is merged when done.
3. **Commit** (the coordinator only), each time gated on green:
   `make test > log && … && git commit`. Never `;`. Every web `check:*` must
   pass too.
4. **Docs sync:** an agent brings the five living docs (FEATURES, INFRA,
   FLOWS, DATA, GUIDE) up to date from `git log -p <last sync>..HEAD`.
5. **Deploy locally and prove:** `make clean && make up && make e2e`, then
   restart the web dev server (`npm run dev -- --port 5173`) so it reads the
   new local ids.
6. **Re-score:** a readiness reviewer updates `READINESS.md` (GO/NO-GO,
   counts, blockers) and adds R2-n tasks.

## 2. The agents and their rules

| Agent | Writes | Never |
|---|---|---|
| Verifier | only its new section at the end of TASKS.md | edits code, types passwords or cards, confirms deletions |
| UX reviewer / visual lead | `docs/research/*ui-ux*` / `*visual-direction*`, UX-n or VD-n in TASKS | builds |
| Backend fork | `backend/`, `infra/`, `local/`, `.github/`, docs other than the living ones | touches `web/src`, restarts containers while a browser round runs |
| Web fork | `web/`, ticks in TASKS | touches the backend |
| Worktree fork | its own worktree branch, commits there | touches :5173 or the main tree |
| Docs sync | the five living docs | describes uncommitted work |
| Readiness reviewer | READINESS.md, R2-n tasks | writes to the running stack |

For every agent:
- Don't commit (except in a worktree), never `git stash`, and don't use git
  commands that change the tree.
- Sign in only with the **"Continue as demo …" buttons**.
- Never touch real AWS. Stripe stays in test mode, and the fake provider is the
  default.
- End each report with "Living-docs changes", so the docs sync knows what moved.
- UI work loads `frontend-design` and the **`cappy-ui` skill**
  (`.claude/skills/cappy-ui/SKILL.md`), and runs its §7 checklist at 390, 375,
  360 and 430 px, light and dark, 100 % and 200 % text, EN/DE/FR.
- Browser agents that run at the same time use **different origins**, because
  sign-in follows tabs of the same origin: the verifier uses `localhost:5173`,
  the UX reviewer `127.0.0.1:5173`, and worktree builds `127.0.0.1:5174`.

## 3. Writing a good agent prompt

Every prompt covers the same seven points:
1. **Who you are**, and the files you own.
2. **What to read first:** the relevant TASKS section, the research doc and the rulebook.
3. **The exact items**, with their ids, in order.
4. **The contracts** the other fork expects: shapes, codes and field names.
5. **The checks** that must pass, and what to verify in the browser.
6. **What to report:** contracts, test counts, what's left, living-docs changes.
7. **The limits:** no commits, no real AWS, demo buttons only.

When a fork's work changes a contract, pass it straight to the other fork with
SendMessage. If an agent stops (turn limit or usage limit), resume it with
SendMessage. Don't start a new one, because the stopped agent keeps its context.

## 4. Pacing and quota

A round with four parallel agents uses a lot of the plan's session quota. When
the limit is near:
- run one builder at a time;
- skip the UX reviewer for a round;
- keep the verifier.

After a limit hit:
- check `git status`;
- keep a partial docs edit only if it's accurate;
- merge a worktree branch only if it has commits and passes the checks.

## 5. Where things are

- **Tasks:** `docs/TASKS.md`, grouped by source (V, U, S, P, M, D, F, FL, H,
  GD, R2, UX, VD).
- **Readiness:** `docs/READINESS.md`.
- **Decisions:** `docs/adr/`. A new ADR is written whenever a decision changes.
  ADR 0014 is the visual system.
- **UI rules:** `.claude/skills/cappy-ui/SKILL.md`.
- **Art direction:** `docs/research/2026-10-visual-direction.md`.
- **How to run and test by hand:** `docs/GUIDE.md`.

## 6. Where we stopped (2026-09-27)

The app runs end to end locally:
- `make test`: 653 passed;
- every web check passes;
- `make e2e` passes on a rebuilt stack.

The readiness verdict at the last score was NO-GO:
- 48 met, 35 partial, 12 not met and 13 on the owner (at `0a74b1c`);
- since then R2-19..R2-24 are fixed (`bed48cd`), and the dock and dark-mode
  rework plus the V9 fixes are in.

**Next round, in order:**
1. **The visual build (VD-3 to VD-12):**
   - start it again in a worktree from `prod-readiness` HEAD;
   - the last attempt stopped at the usage limit before committing, and its
     unfinished files are in `.claude/worktrees/agent-ad5efd16e36389410`: reuse
     them only if they pass the checks;
   - show the owner before and after screenshots.
2. **The docs sync:**
   - it covers `e2f6bea..HEAD`;
   - INFRA.md already covers `bed48cd`;
   - FEATURES, FLOWS, DATA and GUIDE still need `bed48cd..969bef8`, plus the
     GUIDE items in V9-22.
3. **Verification round 10 and UX review round 3,** on the visual build.
4. **A readiness re-score.**
5. **R2-2:**
   - walk the Stripe card, 3DS and wallets in the browser in test mode;
   - it needs the owner's go-ahead, because it contacts Stripe's sandbox.

**Waiting on the owner** (details in READINESS.md "Blockers for GO"):
- operator details;
- insurance;
- counsel;
- DPAs and DPIA;
- DAC7;
- the AWS account, domain and first apply;
- a pager and on-call;
- Stripe live;
- store accounts;
- the axe and Capacitor plugin installs (need network);
- rotating the tokens pasted in chat, purging the old decks from git history,
  and making the repository private.
