# UI judge

Findings from the independent UI judge (`.claude/agents/cappy-ui-judge.md`),
judged against `.claude/skills/cappy-ui/SKILL.md` on the branch. The fixer ticks
items and commits this file.

## Round 2 (2026-09-27 10:27–10:49 CEST, 9871fc1 → 224c000)

**How it was run.** Headless Chromium against http://127.0.0.1:5174, signed in
only with the "Continue as demo …" buttons. Every POST except sign-in, `/api/quote`
and `/api/matches` was aborted, so no data changed (the blocked writes were
`/notifications/read` and `/inbox/{id}/read`). Each run used its own browser
context, and storage events were stopped in the frame. The safe area was
emulated at 47/34 px with `Emulation.setSafeAreaInsetsOverride`, so the real
`env(safe-area-inset-*)` values applied.

**Matrix.** 1,344 runs across 32 screens: explore, results, listing (plate and
photos), booking sheet, bookings (upcoming, past, hosting, hosting past), booking
detail (completed, declined, cancelled, active, expired, owner-completed), inbox
(all, unread), thread, earn, add listing (step 1, form), edit listing, you, the
edit-profile sheet, account deletion, notifications, help, help topic, legal,
staff console, staff case and staff listing. Each screen ran at:
- EN at 390, 375, 360, 430 and 1440, in light and dark, at 100 % and 200 %;
- DE and FR at 360 and 390, in light and dark, at 100 % and 200 %;
- EN at 390 with `data-glass='lite'`, `data-transparency='reduce'` and
  `prefers-contrast: more`, each in light and dark.

**Scan.** Each run did all nine checks at the top and at the end of the scroll.
Contrast was sampled from a screenshot with the text made transparent, so it
measures the colour actually rendered behind the text, glass over photos
included.

**Commits.** The run started at 9871fc1. The fixer landed f8a77a5, 062beb8 (the
dock stays full), 31c29db (the sheet is one scroller) and f640f4a (inbox status
chips) during it. The top findings were re-run at **f640f4a (10:41–10:45)** and
still fail there, unless an item says otherwise. HEAD then moved on (84641cd, 224c000), so J-20, J-24, J-25 and J-39 were measured again at 224c000 (10:47–10:48): J-20 still fails there with clearance −53 at 360, and the rest is recorded on each item.

Screenshots are in
`/private/tmp/claude-501/-Users-seifguerbouj-Documents-personal-R-Management/eef0acf8-baf0-462c-94e8-b0b437fb30fd/scratchpad/judge2/`.
The named failures are `fail-J*.jpg` and `ovf-*.jpg`, and every run is under
`shots/<screen>__<w>-<theme>-<lang>-<scale>[-fallback]-{top,end}.jpg`.

### Round-1 items

- [x] J-1 200 % text doubled the gutters and spacing and ate the width (verified fixed at 9871fc1). Spacing stays in px, and no screen overflowed from spacing. The overflows that remain come from unbreakable strings and are filed as new items (J-19, J-31).
- [x] J-2 Search prompt clipped at 200 % (verified fixed at 9871fc1). The prompt and its examples now wrap as real text at DE/FR 360 200 %.
- [x] J-3 Category tiles overlapped at DE/FR 360 200 % (verified fixed at 9871fc1). No overlap and no clamp; the rail scrolls.
- [x] J-4 Lone dash in the German headline (verified fixed at 9871fc1). "brauchst –" now ends a line with its word. The headline itself is covered, see J-17.
- [x] J-5 Pill covered the category text on no-photo cards (verified fixed at 9871fc1). There is no text under the hour tag.
- [x] J-6 Name ellipsis in Bookings (verified fixed at 9871fc1). Zero ellipsis hits on any name, time or price in 1,344 runs.
- [x] J-7 Fee ellipsis on the listing (verified fixed at 9871fc1).
- [x] J-8 Listing action bar overflowed at 200 % (verified fixed at 9871fc1). The bar stacks and the button is full width.
- [ ] J-9 Targets under 44 px (still failing at f640f4a). Buttons, chips, heart and Back pass. These still fail:
  - sheet Close 40×40;
  - search input 278×26;
  - "Write to Cappy" 106×18;
  - "How results are ordered" 264×30;
  - legal links ×22;
  - "This extends your booking before it." 218×16;
  - "Make cover" 99×24.

  Each has its own task below (J-27 to J-34).
- [x] J-10 Accent droplet in the dock (verified fixed at 062beb8). The droplet is neutral with an ink icon. The collapsed dock showed two identical magnifiers (Explore tab plus round search) up to 062beb8, and the rulebook now says the dock never collapses. At f640f4a the dock stays full. See J-24 for label contrast.
- [x] J-11 Label/value rows and hyphenated tabs at 200 % (verified fixed at 9871fc1). Rows stack and tabs don't hyphenate. The same failure class came back on Results, see J-19.
- [x] J-12 Listing top row wrapped into the photo counter (verified fixed at 9871fc1).
- [x] J-13 Bookings card at FR 360 200 % (verified fixed at 9871fc1). The title, time and button were cut; now they wrap with no clip.
- [x] J-14 Earn chart day labels collided at DE 360 200 % (verified fixed at 9871fc1). No overlap hits on Earn.
- [x] J-15 Desktop wordmark not in Bodoni, and the CNC photo (verified fixed at 9871fc1). The wordmark is Bodoni at 1440 and the CNC listing shows its plate.
- [x] J-16 Thread title (verified fixed at 9871fc1). The thread is titled with the other person's full name.

### New tasks (most severe first)

- [x] J-17 (fixed in 8bbf364) [explore + results · 390/375/360/430 · light+dark · EN/DE/FR · 100/200 %] h1 "Rent what you need, by the hour": the lower half is painted over at scroll 0 by `.scroll-edge::before` on the sticky search. That pseudo-element sits at top −47 px, 165 px tall, and is page colour to 78 %. Measured: only the top half of line 1 shows, and at 200 % "by the hour" is gone. Rule: no text clipped. (f640f4a, 10:41) — Paint the fade only while the search is stuck (scroll-driven or a stuck class), or start it at the search's own top. See `fail-J17-explore-390-headline-covered.jpg`.
- [x] J-18 (fixed in 8bbf364) [thread · all phones · light+dark · EN/DE/FR · 100/200 %] The composer, the reply chips and the dock stack over the conversation.
  - At 375×667 about 150 px of conversation is visible.
  - The composer floats over the bubbles and cuts the "Keep payments on Cappy" warning.
  - The chips sit half under the composer.
  - At 200 % the placeholder breaks "Schrei b" (DE) and the message pane is about 110 px tall.
  - The textarea reaches 823 px, inside the bottom 34 px (the home-indicator area).

  Rule: the dock is hidden on detail screens, and nothing sits under the home indicator. (f640f4a) — Hide the dock on `/inbox/:id` and in the booking-detail conversation. Pin the composer above the safe area, put the chips in one row above it, and let the thread use the whole height. See `fail-J18-*.jpg`.
- [x] J-19 (fixed in 8bbf364) [results · 430 (and 390/360) · 200 % · EN/DE/FR] The h2 "Results" is squeezed to 20 px wide, one letter per line. The `shrink-0` meta "1 match · How results are ordered" overlaps it and pushes the page to 410 px (EN), 552 px (FR at 390) and 495 px (DE at 360). The mobile viewport then zooms out. Rule: no horizontal scroll, no overlap. (f640f4a) — Let the header row wrap (`flex-wrap`), give the h2 `shrink-0` and let the meta shrink and wrap. See `fail-J19-*.jpg` and `ovf-results-*.jpg`.
- [x] J-20 (fixed in 8bbf364) [listing · all phones · light+dark · EN/DE/FR] At the end of the scroll the last element, "Report", sits under the sticky action bar. Clearance is −28 px at 390, −186 px at 360 200 %, −53 px in DE and −113 px in FR. Rule: the scroll view ends 16 px above the bar. (f640f4a) — Bottom padding = the measured bar height + 16. Measure it with a ResizeObserver, because the bar grows at 200 % and in DE/FR. See `fail-J20-listing-390-report-under-bar.jpg`.
- [x] J-21 (fixed in 8bbf364) [booking detail (active, declined, cancelled, expired, owner-completed), add listing form, edit listing · 375×667, 360/390 DE/FR 200 %] The last line ends 9 px above the sticky bar or under it. Examples: "Includes the service fee of €2.25" at −19 px (375), "Nothing: hold released" at +9 px, "Buchende zahlen per Karte…" at −4 px. Rule: 16 px clear of the bar. (9871fc1–f640f4a) — Apply the J-20 fix to every screen with a sticky action bar, in the shared component.
- [ ] J-22 [desktop header · 1440 · 200 % · EN] The "List something" CTA runs past the right edge of the viewport and the bell's badge is cut by the top of the header. Rule: no clipped text or overflow. (f640f4a, 10:45) — At large text, turn the nav labels into icons with aria-labels, or move them into a menu.
- [ ] J-23 [booking · active · all phones · light+dark · EN/DE/FR] The future timeline step is faded: "Finished" measures 2.44:1 and "Handed back" 1.82:1 in light, "Terminée/Abgeschlossen" 3.49:1 and "Rendu/Zurückgegeben" 2.34:1 in dark. Rule: 4.5:1. (f640f4a) — Keep the text at ink-2/ink-3 with no opacity, and show "not yet" with the step marker (outline number) only.
- [x] J-24 [dock · 360/375 · light · EN/DE · Explore, You] Inactive dock labels measured 3.46–3.93:1 where the glass passed over photo cards (9871fc1). Rule: 4.5:1 (verified fixed at 224c000, 10:47: no dock label under 4.5:1 at 360 and 375 in EN and DE).
- [ ] J-25 [earn · 360–430 · light · all langs] The chart date numbers ("28") are `opacity-80` at 11 px and measured 3.6:1 (f640f4a). After the VD-18 chart they measure 4.24:1 for 28, 29, 30, 1, 2 and 3. Rule: 4.5:1. (still failing at 224c000, 10:48) — Remove the opacity and use ink-3.
- [ ] J-26 [1440 · light+dark · earn, bookings past, booking detail, listing] Two accent-filled controls show in one view: the header "List something" plus the page primary ("List something", "Open booking", "Find something to rent", "Request"). Rule: one accent-filled control per view. (f640f4a) — Make the desktop header CTA outlined or tinted glass, and keep the fill for the page's primary. See `fail-J26-earn-1440-two-accents.jpg`.
- [ ] J-27 [booking sheet, edit-profile sheet · all phones · all] The Close button measures 40×40. Rule: 44. (f640f4a) — `h-11 w-11`; the 36 px visual can stay if the hit area is 44.
- [ ] J-28 [explore, results · all phones · all] The search input's hit area is 278×26 inside the 62 px pill, so taps on the top or bottom 18 px of the pill, or on the icon, do nothing. Rule: 44. (f640f4a) — Stretch the input to the whole pill (`self-stretch`, `min-h-[44px]`), or make the pill a `<label>`.
- [ ] J-29 [help, help topic · all phones] The "Write to Cappy" link measures 106×18 (EN), 120×18 (DE) and 104×18 (FR). Rule: 44. (f640f4a) — `inline-flex min-h-[44px] items-center`.
- [x] J-30 (fixed in 8bbf364) [results · all phones] "How results are ordered" measures 264×30 (EN) and 214×16 (FR). Rule: 44. (f640f4a) — `min-h-[44px]`, fixed together with J-19.
- [ ] J-31 [staff case, staff console, add listing form, edit listing · 360/390 · 200 % · all langs] Horizontal overflow, which zooms the mobile viewport out:
  - `span.tnum "bk_01m3fgxkbhfn18ykd39ct3qxzd"` is 405 px wide (page 425 px at 360/390);
  - the report meta line with `rp_01m3fjgszy…` pushes the page to 445 px;
  - `span.shrink-0 "% from 40 h"` is 157 px wide (page 412 px at 390 EN);
  - "Weiteres hinzufügen" goes 13 px past the edge at DE 360.

  Rule: no horizontal scroll. (f640f4a) — Use `overflow-wrap:anywhere` on ids, drop `shrink-0` from the percentage hint, and give the add-photo tile a min-width that fits the viewport. See `ovf-*.jpg`.
- [ ] J-32 [legal · all phones · EN/DE/FR] The legal nav links are 22 px tall ("Impressum" 80×22, "AGB" 31×22). Rule: 44 tall and 8 apart. (f640f4a) — `min-h-[44px]` with a `gap-x-2`.
- [ ] J-33 [booking detail, all states · all phones · EN/DE/FR] "Report" and "Block" are 4 px apart. "Help" and "Get help with this booking" are under 8 px apart and say the same thing twice. Rule: 8 px between targets. (f640f4a) — Keep one "Get help with this booking" and set a 16 px gap between Report and Block.
- [ ] J-34 [booking · cancelled · all phones] The link "This extends your booking before it." measures 218×16 and its copy is unclear. Rule: 44, plain words. (f640f4a) — "Extends your booking of Sat, Sep 26 →" with a 44 px row.
- [ ] J-35 [edit listing · all phones · EN/DE/FR] On the photo tiles:
  - "Make cover" is an overlay button of 99×24;
  - its hit area is under 8 px from "Remove photo";
  - FR "Mettre en couverture" is 9 px wider than its button at 200 %;
  - the "Couverture" badge is cut by the tile.

  Rule: 44 targets, no clipped text. (f640f4a) — Put "Make cover" under the tile as a 44 px text button, or in a long-press or overflow menu.
- [ ] J-36 [staff console · 360/375 · 200 % · EN/DE/FR] Listing names are wider than their text box by up to 35 px ("Refrigerated van, Randstad": line 207 px, box 172 px), and the meta line runs 126 px wider than its box. Rule: text wraps inside its box. (f640f4a) — `min-w-0` on the flex text column plus `overflow-wrap:anywhere`. See `fail-J35-admin-360-200.jpg`.
- [ ] J-37 [staff console, staff case · all] Raw ids appear inside running text: "report rp_01m3fjgszy5mgvzz3yhq3g338x" and "Finished · … · bk_01m3fgxkbhfn18ykd39ct3qxzd". Rule: no raw ids. (f640f4a) — Staff need them, so move them to a labelled "Reference" row, shortened to …3qxzd, with a copy button.
- [ ] J-38 [thread, owner-completed booking · 375/390/430 · 200 % and 375 100 %] The message bubble text is wider than the bubble ("Thanks for returning it clean!…": line 293 px, bubble 287 px). Rule: text inside its box. (f640f4a) — `min-w-0` plus `overflow-wrap:anywhere` on the bubble.
- [ ] J-39 [earn "Your record", declined booking · 360 · 200 % · EN/DE/FR] "20 réservations · 95 % à l'heure" is up to 36 px wider than its box. Rule: wrap. (still failing at 224c000) — Let the meta wrap and drop `whitespace-nowrap` or `shrink-0`.
- [ ] J-40 [bookings · past (renter) · all · EN/DE/FR] A card in the Past tab is labelled "Next up" ("Ensuite", "Als Nächstes") on a finished booking that asks "Rate how it went". The label contradicts the tab. (f640f4a) — Label it "To rate", or move the card to the top of Upcoming as "Needs you". See `fail-J39-past-next-up.jpg`.
- [ ] J-41 [bookings · upcoming (renter) · all phones] Upcoming says "Nothing upcoming" while the dock badge says "2 need your attention". Those 2 are in Past, so the badge leads to an empty screen. (f640f4a) — Land on the tab that holds the attention items, or show them in Upcoming.
- [ ] J-42 [listing, freight · all · EN] The quantity preselects the largest batch (13 pallets, €281.56). The sticky meta then wraps "…service / fee" and "3:43 / PM" as orphans at 390. (f640f4a) — Preselect the smallest or last-used quantity, and cut the bar meta to two lines ("€281.56 total · Tomorrow 8:00 AM–3:43 PM").
- [ ] J-43 [listing · when `/api/quote` fails] The page shows the empty state "Nothing free that long — 1 pallets needs more time… Try a smaller batch". The plural is wrong, the advice is impossible at 1, and a failed request is not "nothing free". The card also draws a double line (the card border plus the empty state's `border-t`). (9871fc1, seen with the quote blocked) — Show an error state with Retry, pluralise with `plural()`, and remove the inner border.
- [ ] J-44 [booking sheet, edit-profile sheet · phones] The sheets run edge to edge with only the top corners rounded. Rule §4: at the medium detent, inset 8 with radius 32 on all corners. (31c29db) — Implement the medium detent, or amend the rulebook if VD-12 dropped it.
- [ ] J-45 [back chevron · help, notifications, thread, add listing · phones] The chevron glyph sits about 12 px right of the title's left edge (glyph x≈32, title x=20). (f640f4a) — Shift the 44 px hit area left by 12 so the glyph lines up with the gutter, as iOS does.
- [ ] J-46 [notifications · phones] "Mark all as read" is indented 16 px from the title and list edge (828 vs 812). At DE 200 % it becomes a centred two-line block. (f640f4a) — Align it to the gutter, or move it to the top bar as a text button.
- [x] J-47 (owner, not a bug: shown until the owner provides LEGAL_*) [legal · all] "Operator details to be completed before launch" is visible to every user. Unfinished content. (f640f4a) — Fill it in, or keep it out of anything shown to users. See `fail-J47-legal-placeholder.jpg`.
- [ ] J-48 [explore cards · phones and 1440] The gap from title to meta is about 40 px when the title is one line, because the title's min-height reserves two lines. Rule §1: 4 px between related lines. (f640f4a) — Remove the reserved height and align the grid rows with `grid-template-rows: subgrid`, or let each card size itself.
- [ ] J-49 [explore · 1440] The location chip's text starts at x=205 and the header wordmark at x=163, while the content column starts at x=192. Rule: one left edge. (f640f4a) — Put the header inside the same 1200 container, and bring the chip's icon to the edge.
- [ ] J-50 [spacing grid · explore cards and other cards] These values are off the 4 px grid:
  - card meta `mt-1.5` (6 px);
  - hour tag padding 6/6;
  - location chip gap 6.

  Rule §1: 4 or 8. (f640f4a) — 4 for the meta and 8 for the chip gap.
- [ ] J-51 [1440 · every screen] The footer links are 18 px tall ("Impressum" 67×18, "Help" 32×18). WCAG 2.5.8 sets a 24 px minimum; the rulebook says 44. This one item makes every 1440 row FAIL. (f640f4a) — `min-h-[44px] inline-flex items-center` (or at least 24 on desktop).
- [ ] J-52 [listing · 1440] The first gallery tile is the no-photo plate, next to a real truck photo. This looks unfinished. (f640f4a) — When a listing has photos, show only the photos; the plate is for listings without any.
- [ ] J-53 [desktop · bookings, inbox] Bookings and Inbox sit in a 560 px column under a 1200 px header, leaving half the screen empty. (f640f4a) — Use a two-pane layout on desktop (list and detail, or list and thread), as Airbnb Trips and Messages do.
- [ ] J-54 [thread · 1440] The reply-chip rail is cut at the card edge ("Thanks, see you then!") with no fade or scroll affordance. (f640f4a) — Wrap the chips, or add a scroll-edge fade.

**Glass and fallbacks.** At 390 in light and dark, `data-glass='lite'`,
`data-transparency='reduce'` and `prefers-contrast: more` raised no failure of
their own. Glass text over the seed photos stayed at 4.5:1 or better: the hour
tags, the category chip, 1/2 and the listing header. Dark surfaces, badges and
active states are visible.

### PASS / FAIL per route and size

A cell's count is the findings summed across the configurations run at that
width: themes, languages, text sizes and fallbacks. `/n` is the number of runs.
Every 1440 row fails on the footer-link targets alone (J-51), and most also on
J-26.

| Route | 390 | 375 | 360 | 430 | 1440 |
|---|---|---|---|---|---|
| Explore | FAIL 14 /18 | FAIL 10 /4 | FAIL 15 /12 | FAIL 6 /4 | FAIL 32 /4 |
| Results | FAIL 37 /18 | FAIL 10 /4 | FAIL 26 /12 | FAIL 11 /4 | FAIL 34 /4 |
| Listing | FAIL 26 /18 | FAIL 4 /4 | FAIL 12 /12 | FAIL 6 /4 | FAIL 36 /4 |
| Listing (own, photos) | FAIL 5 /18 | PASS /4 | PASS /12 | PASS /4 | FAIL 32 /4 |
| Booking sheet | FAIL 15 /18 | FAIL 4 /4 | FAIL 12 /12 | FAIL 4 /4 | PASS /4 |
| Bookings · upcoming | FAIL 2 /18 | FAIL 2 /4 | FAIL 2 /12 | PASS /4 | FAIL 36 /4 |
| Bookings · past | PASS /18 | PASS /4 | PASS /12 | PASS /4 | FAIL 36 /4 |
| Bookings · hosting | PASS /18 | PASS /4 | PASS /12 | PASS /4 | FAIL 36 /4 |
| Bookings · hosting past | FAIL 2 /18 | PASS /4 | PASS /12 | PASS /4 | FAIL 32 /4 |
| Booking · completed | FAIL 18 /18 | FAIL 2 /4 | FAIL 8 /12 | FAIL 6 /4 | FAIL 36 /4 |
| Booking · declined | FAIL 32 /18 | FAIL 4 /4 | FAIL 26 /12 | FAIL 6 /4 | FAIL 32 /4 |
| Booking · cancelled | FAIL 38 /18 | FAIL 8 /4 | FAIL 26 /12 | FAIL 8 /4 | FAIL 34 /4 |
| Booking · active | FAIL 50 /18 | FAIL 4 /4 | FAIL 32 /12 | FAIL 13 /4 | FAIL 40 /4 |
| Booking · expired | FAIL 22 /18 | FAIL 3 /4 | FAIL 18 /12 | FAIL 7 /4 | FAIL 32 /4 |
| Booking · owner completed | FAIL 34 /18 | FAIL 2 /4 | FAIL 12 /12 | FAIL 8 /4 | FAIL 32 /4 |
| Inbox | PASS /18 | PASS /4 | PASS /12 | PASS /4 | FAIL 32 /4 |
| Inbox · unread | PASS /18 | PASS /4 | PASS /12 | PASS /4 | FAIL 32 /4 |
| Thread | FAIL 28 /18 | FAIL 2 /4 | FAIL 20 /12 | FAIL 10 /4 | FAIL 32 /4 |
| Earn | FAIL 10 /18 | FAIL 5 /4 | FAIL 13 /12 | FAIL 2 /4 | FAIL 39 /4 |
| Add listing · step 1 | PASS /18 | PASS /4 | PASS /12 | PASS /4 | FAIL 32 /4 |
| Add listing · form | FAIL 4 /18 | FAIL 2 /4 | FAIL 7 /12 | PASS /4 | FAIL 36 /4 |
| Edit listing | FAIL 25 /18 | FAIL 6 /4 | FAIL 24 /12 | FAIL 4 /4 | FAIL 36 /4 |
| You | FAIL 2 /18 | FAIL 4 /4 | FAIL 4 /12 | FAIL 1 /4 | FAIL 32 /4 |
| You · edit profile sheet | FAIL 20 /18 | FAIL 6 /4 | FAIL 14 /12 | FAIL 4 /4 | PASS /4 |
| Account deletion | PASS /18 | PASS /4 | PASS /12 | PASS /4 | FAIL 32 /4 |
| Notifications | PASS /18 | PASS /4 | PASS /12 | PASS /4 | FAIL 32 /4 |
| Help | FAIL 18 /18 | FAIL 4 /4 | FAIL 12 /12 | FAIL 4 /4 | FAIL 34 /4 |
| Help topic | FAIL 18 /18 | FAIL 4 /4 | FAIL 12 /12 | FAIL 4 /4 | FAIL 34 /4 |
| Legal | FAIL 84 /18 | FAIL 14 /4 | FAIL 42 /12 | FAIL 14 /4 | FAIL 46 /4 |
| Staff console | FAIL 41 /18 | FAIL 16 /4 | FAIL 52 /12 | FAIL 8 /4 | FAIL 38 /4 |
| Staff · case | FAIL 24 /18 | FAIL 6 /4 | FAIL 18 /12 | FAIL 4 /4 | FAIL 38 /4 |
| Staff · listing | PASS /18 | PASS /4 | PASS /12 | PASS /4 | FAIL 34 /4 |

Round 1: 15 of 16 verified fixed, 1 still failing (J-9). Round 2: 38 new tasks (J-17 to J-54), 1 of them already verified fixed at 224c000 (J-24), so 37 are open. After the 8 below, do the target and contrast batch (J-25 to J-35).

Verdict: fix these 8 first: J-17, J-18, J-19, J-20, J-21, J-22, J-23, J-31.
