# UI rounds: how we got here, and what is open

This is the record of the UI and UX work on branch `wip/visual-build`
(2026-09-27): how it was done, where it stands, and the open points for the
next UI rounds. The general agent loop is in
[`DEVELOPMENT-LOOP.md`](DEVELOPMENT-LOOP.md). The rules the UI follows are in
`.claude/skills/cappy-ui/SKILL.md` and [ADR 0014](adr/0014-visual-system.md).

## 1. How we worked

1. **The owner's brief.** "Every little detail in the UI needs to be perfect."
   It had to be "super beautiful … with the effect and new Apple mirror screen
   UI (Liquid Glass) … now it looks functional but does not attract", inspired
   by Instagram, Uber, Airbnb and X (GOAL 18, 19).
2. **Rules before pixels.**
   - The `cappy-ui` skill is the rulebook: the 4 px grid, the type scale, colour
     roles and contrast in light and dark, component specs, motion, and a
     review checklist at 390, 375, 360 and 430 px, light and dark, 100 % and
     200 % text, EN/DE/FR.
   - Every UI agent loads it together with the `frontend-design` plugin.
3. **Research, then an art direction.**
   - A visual design lead studied Apple's Liquid Glass (WWDC25, HIG),
     Airbnb 2025, Uber Base, Instagram, X/Threads, Revolut, Vinted, Spotify,
     Linear and Apple Maps and Photos. It used real screenshots (the links are
     in `research/visual-refs.json`).
   - It wrote `research/2026-10-visual-direction.md`: the concept "glass over
     the workshop", the Liquid Glass recipe and its fallbacks, a redesign per
     screen, and VD-1..VD-31.
   - ADR 0014 records the decision. Glass is on chrome only, never on content.
4. **A builder in a worktree.** The UI builder works on its own branch and
   dev server (`127.0.0.1:5174`), so the rest of the app and other agents are
   never disturbed. The owner can see it live on a phone on the same Wi-Fi,
   at `http://<mac-ip>:5174`, through the `/cognito` dev proxy and a
   `randomUUID` fallback.
5. **A judge and a fixer.**
   - An independent UI judge (`.claude/agents/cappy-ui-judge.md`) runs
     scripted scans on every screen (overflow, clipping, overlap, dock and
     safe area, targets, grid, contrast on the real background including glass,
     consistency) plus a designer's eye.
   - It writes numbered tasks into [`UI-JUDGE.md`](UI-JUDGE.md). The fixer
     takes open J-tasks first, ticks each with its commit, and builds design
     items only while the queue is empty.
   - A UI change merges only when the judge says "ship".
6. **The owner's feedback goes in first.** Each piece was folded in straight
   away and written into the rulebook:
   - the weak dark mode and the dock (at most five tabs; light is the default,
     with a one-tap switch);
   - the heavy Explore hero and jargon copy (content first, plain words in
     EN/DE/FR);
   - "the dock is better full": it never collapses or hides on scroll.
7. **Measured, not guessed.**
   - Every claim comes with a number (for example "label 3.09:1 vs 4.5:1",
     "page 443 px at 360 px").
   - Web checks guard the rules in CI: `check:tokens`, `check:contrast`
     (73 pairs including the glass worst cases), `check:i18n`, `check:size`
     and the rest.

## 2. Where it stands

**Built** (VD-1 to VD-19, UX-46 to UX-49 and more; ticks in `TASKS.md`):
- **Chrome and theme:** glass tokens with every fallback (no `backdrop-filter`,
  Reduce Transparency, Increase Contrast, a low-power mode, a "Glass effects"
  setting); the full floating glass dock; light by default with dark as a
  designed theme.
- **Screens:**
  - Explore, content first: the search as the hero, the category objects,
    photo rails with hour tags;
  - the listing: a photo-colour wash, glass controls, a hero price, a glass
    title bar on scroll, a floating glass booking bar;
  - sheets: glass header and action row;
  - Earn as a hero;
  - Inbox and thread: messenger bubbles, day lines, a pinned booking chip,
    quick replies, a composer above the keyboard.
- **Moments:** the booking-confirmed ticket, and the hour tag morphing from
  card to listing.
- **Motion and imagery:** glass motion (touch glow, springs, odometer
  digits); nine SVG category objects.
- **Layout at large text:** spacing in px so text can grow (iOS-style); names,
  times and prices wrap instead of being cut; 44 px targets.

**The judge:**
- **Round 1:** 16 findings. 15 verified fixed.
- **Round 2:** 38 more. J-17 to J-21, J-24 and J-30 are fixed and J-47 is the
  owner's.
- **Open:** 31, listed in `UI-JUDGE.md`.
- The last verdict was "fix these 8 first". Five of those eight are fixed
  since, and the full scan hasn't run again.

## 3. Open points for the next UI rounds

In order:
1. **The judge's queue** (`UI-JUDGE.md`):
   - J-22, desktop header at 200 %;
   - J-23, faint future timeline steps;
   - J-31, raw ids widening staff and form screens at 200 %;
   - J-9 / J-27–J-35, the remaining small targets;
   - J-26, two accent fills on desktop;
   - J-25, Earn chart date contrast;
   - J-40–J-46, J-48–J-54: Past "Next up", the dock badge to an empty tab, the
     freight default batch, a failed quote's text, footer links, the narrow
     desktop columns.

   Then **re-run the judge** until it says "ship".
2. **Design items not started:**
   - VD-22, dark as its own theme (ambient night, accent glow, a dark pass on
     every screen);
   - VD-24, Welcome with the floating objects;
   - VD-28, the You screen;
   - VD-23, adaptive ink over photos;
   - VD-25, results and map;
   - VD-26, the add-listing wizard visuals;
   - the compact ticket on booking detail (VD-15);
   - VD-29 and VD-30, the tilt highlight and refraction extras.
3. **Needs the backend:** "delivered / read" in chat. The backend has
   `message_reads`; expose the other side's last read time on the thread.
4. **Needs a person or a device:**
   - real category photos for the demo listings (14 of 26 stock photos were
     wrong and now show plates);
   - real 3D renders of the category objects (today's are stylised SVG, not
     Airbnb-level);
   - a layered iOS 26 app icon (VD-27);
   - haptics and the shells passing Reduce Transparency (VD-20, VD-21, which
     need Capacitor plugins installed with network access);
   - a device performance pass of the glass on a mid-range Android and an
     iPhone (VD-31).
5. **Score it again:** run UX review round 3 (`cappy-ux-reviewer`) against the
   big apps. The last score was 2.8/5, taken before this branch. Also run a
   verification round (`cappy-verifier`) over the GUIDE scripts on this branch
   before merging.

## 4. How to continue

- **Worktree:** start a worktree from this branch (or check it out) and run
  `npm run dev -- --host 0.0.0.0 --port 5174` in `web/`. Copy
  `.local/web.env` to `web/.env.development.local`, and set
  `VITE_COGNITO_ENDPOINT=/cognito` for phone testing.
- **Agents:** run `cappy-ui-judge` → `cappy-web-builder` (it takes open J-tasks
  first) → `cappy-ui-judge`, until "ship". Then run `cappy-ux-reviewer` and
  `cappy-verifier`, and merge.
- **Owner feedback:** new feedback goes in first and into the rulebook, with its
  date.
