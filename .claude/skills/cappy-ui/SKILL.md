---
name: cappy-ui
description: Cappy's UI rulebook — exact spacing, type, colour pairing (light and dark), component specs (dock, buttons, sheets, cards, inputs, badges), motion, and the phone-size review checklist. Load before building or reviewing any Cappy screen, together with the frontend-design skill.
---

# Cappy UI rules

Every pixel is intentional. These rules are the contract; `web/src/app/theme.css`
holds the tokens that implement them. Use a token, never a literal
(`npm run check:tokens` fails on literals). If a rule needs a value that has no
token, add the token to `theme.css` (light and dark) first.

Sources: Apple HIG (iOS 26), Material 3, WCAG 2.2 AA, and the research in
`docs/research/2026-09-ui-ux-review.md`.

## 1. Spacing: one 4 px grid

The scale is 4 · 8 · 12 · 16 · 20 · 24 · 32 · 40 · 48 · 64. Nothing off it.

| Use | Value |
|---|---|
| Icon to its label, inside a chip | 4–8 |
| Between related lines (title → meta) | 4 |
| Between items in a list or form fields | 12–16 |
| Card inner padding | 16 (phone), 20–24 (desktop) |
| Between sections of a screen | 32 (phone), 48 (desktop) |
| Screen side gutter | 16 (phone < 600), 24 (tablet), 32 (desktop), content max 1200 |
| Space between two tap targets | at least 8 |

Rules:
- Related things sit closer than unrelated ones (proximity). A section gap is
  always at least twice the item gap inside it.
- Align to a single left edge per column; no element 2 px off its neighbours.
- Vertical rhythm: text blocks sit on multiples of 4 from their container.

## 2. Type

The scale tokens are `text-caption` 11/14 · `text-label` 13/18 · `text-body`
15/22 · `text-body-l` 17/24 · `text-title-s` 20/26 · `text-title-m` 22/28 ·
`text-title-l` 28/32 · `text-headline` 34/38 · `text-display` 44/46.

- **Phone body is `text-body-l` (17)**, as iOS; secondary text is `text-body` (15).
  Nothing below 11 px ever, and 11 px only for captions and badges.
- Display serif (Bodoni) only at 28 px and up. Everything that is a number
  (prices, times, counts, ratings) is Archivo with tabular figures (`t-figure`).
- At most 3 sizes and 2 weights on one screen section. Weight contrast before
  size contrast.
- Line length 45–75 characters. Never all caps for labels. No single accent word
  in a headline.
- German and French run 30–40 % longer: every label must wrap or fit at 200 %
  text on 360 px (use `hyphens: auto` with the element's `lang`).

## 3. Colour: roles, never raw colours

The roles are `ink` (text, 4 levels) · `surface` / `sunken` / `elevated` (backgrounds)
· `line` / `line-strong` · `accent` (the ONE action colour, crimson) · `danger`
(errors only, not crimson) · `money` · `focus` (blue ink) · `badge`.

- 60 · 30 · 10: surfaces about 60 %, ink and imagery about 30 %, accent at most about 10 %.
  **One accent-filled control per view**: the primary action. Secondary
  actions are outlined or text. Crimson is never decoration.
- Contrast minimums, checked by `npm run check:contrast` (add every new pair):
  - body text at least 7:1 on its surface (target; AA floor 4.5:1);
  - secondary text at least 4.5:1;
  - large text (at least 24 px, or 19 px bold) at least 3:1;
  - UI parts (borders of inputs, icons that carry meaning, focus rings) at least 3:1.
- State colours always come with text or an icon; never colour alone (WCAG 1.4.1).

### Dark mode (opt-in; light is the default)

- **No pure black**: the base is about #121412 to #171d18. Elevation goes *lighter*
  per level (base → raised → overlay, about 4–6 % more lightness each), not
  with shadows. Each level must be visibly distinct from the one below.
- Text is never pure white on large areas: `ink` is about #eef0ea, secondary
  levels step down but keep 4.5:1.
- The accent is desaturated and lightened for dark (no neon pink blob). Filled
  accent buttons carry dark text if white fails 4.5:1.
- Photos and plates are dimmed about 8–12 % (`filter: brightness(.9)`) so they don't
  glare; illustrations get dark variants.
- Dividers and card edges must still be visible (`line` at least 1.5:1 against the surface).
- The theme switch is one tap (sun/moon) in the You header and the desktop header.

## 4. Components

**Tap targets:** at least 44×44 (iOS) / 48×48 dp (Android) hit area, even when the visual is smaller.

- **Buttons:** heights 48 (primary, full width on the phone), 40 (secondary), 32 (compact,
  desktop only). Radius `radius-control`. Label `text-label` or `text-body` semibold.
  Pressed state: scale .97 plus a darker shade within `dur-instant`. Disabled at 40 % opacity
  with the reason nearby. Loading keeps the width (spinner replaces the label).
- **Inputs:** height 48, label above (never placeholder-only), 8 between label and field,
  helper or error below in `text-label`. The error uses `danger` plus an icon plus text.
  Focus ring 2 px `focus` with a 2 px offset.
- **Cards:** padding 16, radius `radius-card`, one hairline `line` or `shadow-1`,
  never both. The image sits on top at a fixed aspect ratio (4:3 listings) with
  width and height set (no layout shift).
- **Chips:** height 32 (36 on touch), horizontal padding 12, radius full. Selected =
  filled `ink` with inverse text, plus a check icon.
- **Badges:** min 16×16, `text-caption` bold, on the icon's top-right corner at
  (−4, −4), never clipped by its container, a 2 px ring in the bar colour.
- **Sheets (phone):** grabber 36×4, detents medium (about 50 %) and large (about 92 %), top
  radius `radius-sheet`, scrim at 40 % ink. Desktop (≥ 768): a centred dialog, max 560.
- **Dock (phone tab bar):**
  - at most 5 destinations (Explore · Bookings · Inbox · Earn · You), with no floating
    create button in the bar (creation lives on Earn and in headers);
  - height 56 + the bottom safe area; icon 24, label `text-caption` 11–12 medium, 4 between;
  - active: an indicator pill 56×32 behind the icon (Material 3) in `accent-subtle`
    (light) or a raised surface (dark), the icon and label in `ink` or `accent-text`.
    Inactive icons are `ink-3`, never below 4.5:1;
  - background: opaque `elevated` (or 85 % plus 20 px blur), a hairline top border;
    every scroll view gets bottom padding = dock height + 16 so content never
    sits under it;
  - hidden on detail screens; at 200 % text it goes icons-only with aria-labels.
- **Top bars:** height 44–56, title `text-title-s`, back chevron 44 hit area.
- **Lists:** row min 56 (one line) / 72 (two lines), 16 side padding, dividers
  inset to the text edge.

## 5. Motion

The tokens are `dur-instant` 100 · `dur-short` 150 · `dur-medium` 250 · `dur-long`
350 · `dur-xlong` 500, with the easings `ease-standard`, `ease-decelerate`
(entering), `ease-accelerate` (leaving) and `ease-spring-spatial` (sheets).

- Press feedback within 100 ms. Small elements 150, sheets and routes 250–350.
  Exits at two thirds of the entry.
- Only animate `transform` and `opacity`. Nothing moves on its own except one
  deliberate moment (a confirmed booking).
- `prefers-reduced-motion`: replace movement with 100 ms fades.
- Skeletons only after 300 ms of waiting; they match the final layout exactly.

## 6. Imagery and icons

- One icon set, 24 px grid, 1.5–2 px stroke, same corner style. Icons
  with meaning have text or an aria-label.
- Listing photos: the owner's own; fallback is the designed category plate, never
  unrelated stock. Colour placeholder from `photoMeta.color`, `srcset` from renditions.

## 7. Review checklist: run it on every screen you touch

Sizes: **390×844, 375×667, 360×800, 430×932** (iframes if resizing does not
apply), plus desktop 1440. Each in **light and dark**, **100 % and 200 % text**,
**EN, DE and FR**. Simulate the safe area (top 47, bottom 34).

For each screen check:
- every value on the 4 px grid; gutters and section gaps as in §1;
- one primary accent action; every text pair passes §3;
- no text clipped, truncated without ellipsis or overlapping; no horizontal scroll;
- nothing under the dock or the home indicator; sticky bars clear of the keyboard;
- every target ≥ 44 and ≥ 8 apart; focus visible and in order;
- loading, empty, error and offline states exist and match the layout;
- no layout shift when images or data arrive;
- dark mode: surfaces distinct, no glare, badges and active states visible.

Screenshot before and after at 390 in both themes and attach them to the report.
