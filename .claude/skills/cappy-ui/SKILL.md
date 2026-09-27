---
name: cappy-ui
description: Cappy's UI rulebook — exact spacing, type, colour pairing (light and dark), component specs (dock, buttons, sheets, cards, inputs, badges), motion, and the phone-size review checklist. Load before building or reviewing any Cappy screen, together with the frontend-design skill.
---

# Cappy UI rules

Every pixel is intentional. These rules are the contract; `web/src/app/theme.css`
holds the tokens that implement them. Use a token, never a literal
(`npm run check:tokens` fails on literals). If a rule needs a value that has no
token, add the token to `theme.css` (light and dark) first.

Sources: Apple HIG (iOS 26, Liquid Glass), Material 3, WCAG 2.2 AA, the research in
`docs/research/2026-09-ui-ux-review.md`, and the art direction in
`docs/research/2026-10-visual-direction.md` (ADR 0014: glass chrome, photographic
content). The look is meant to attract, not only work: when a rule here and the
art direction disagree, the art direction wins and this file is corrected.

## 1. Spacing: one 4 px grid

The scale is 4 · 8 · 12 · 16 · 20 · 24 · 32 · 40 · 48 · 64. Nothing off it.

| Use | Value |
|---|---|
| Icon to its label, inside a chip | 4–8 |
| Between related lines (title → meta) | 4 |
| Between items in a list or form fields | 12–16 |
| Card inner padding | 16 (phone), 20–24 (desktop) |
| Between sections of a screen | 32 (phone), 48 (desktop) |
| Screen side gutter | 16 below 375, 20 from 375 (phones), 24 (tablet), 32 (desktop), content max 1200 |
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
- Bodoni is for moments only: Welcome, the Explore greeting, the booking ticket, the
  Earn hero word and empty states, at 34 px and up (44 in dark). Screen titles are
  `text-large-title`: Archivo 700 at width 112, 34/40, left-aligned. One hero figure
  per screen may use `text-figure-hero` (Archivo 800, width 125, tabular, cents at 60 %).
  Every other number (prices, times, counts, ratings) is Archivo with tabular figures
  (`t-figure`).
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
- The accent is #b0182e (light) / #f2606d (dark). In dark the one primary may carry
  `--accent-glow`. Symbols on glass are monochrome `ink`; only the primary action is
  tinted, and it is tinted on its background, never on its label.

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
- Dividers and card edges must still be visible (`line` at least 1.5:1 against the surface: 18 % ink in dark, 22 % in light meet it).
- Dark surface steps (lightest last): page #121813 · sunken #161c17 · surface #1a211b · elevated #232b24 · overlay #2c352d · pill #38443a. `sunken` is never darker than the page.
- In dark, Bodoni only from 44 px (its hairlines break up below).
- Glass is chrome only (§4 Materials). Sheet bodies are opaque in both themes; their
  header and action row are glass. The top of Explore, Earn and You carries
  `--ambient-night`.
- The theme switch is one tap (sun/moon) in the You header and the desktop header;
  Appearance is the first section of You. **Light is the default** until dark mode
  passes this rulebook on every screen (owner's call, 2026-09-27); then System.

## 4. Components

**Materials.** Four planes: ground (page, media, plate), content (opaque surfaces),
glass (chrome), lift (pressed glass, menus, the ticket). Content is never glass: no
cards, rows, text areas, message bubbles or sheet bodies on glass. At most three
glass surfaces are visible at once; group more into one capsule. Glass never sits on
glass. Text on glass is `ink` or `ink-2` only, ≥ 13 px semibold or ≥ 15 px regular.
Over photos use `glass-media` (icons) or `glass-media-text` (text). Every glass rule
has one fallback in `theme.css`: no `backdrop-filter`, Reduce Transparency, Increase
Contrast, and `data-glass='lite'`. Components never branch on them.

**Tap targets:** at least 44×44 (iOS) / 48×48 dp (Android) hit area, even when the visual is smaller.

- **Buttons:** heights 48 (primary, full width on the phone), 40 (secondary), 32 (compact,
  desktop only). Primary and secondary buttons are capsules. Over media or inside a glass
  action row the primary is tinted glass (accent at 88 % over `glass-frost-thin` with the
  rim); on paper it is solid. Label `text-label` or `text-body` semibold.
  Pressed state: scale .97 plus a darker shade within `dur-instant`. Disabled: a `sunken` fill with `ink-4` text (never
  opacity alone, which fails in dark), with the reason nearby. Loading keeps the width (spinner replaces the label).
- **Inputs:** height 48, label above (never placeholder-only), 8 between label and field,
  helper or error below in `text-label`. The error uses `danger` plus an icon plus text.
  Focus ring 2 px `focus` with a 2 px offset.
- **Cards:** padding 16, radius `radius-card`, one hairline `line` or `shadow-1`,
  never both. The image sits on top at a fixed aspect ratio (4:3 listings) with
  width and height set (no layout shift).
- **Chips:** height 32 (36 on touch), horizontal padding 12. Filter and category chips
  radius full; choice chips inside forms `radius-s`. Selected =
  filled `ink` with inverse text, plus a check icon.
- **Badges:** min 16×16, `text-caption` bold, on the icon's top-right corner at
  (−4, −4), never clipped by its container, a 2 px ring in the bar colour.
- **Sheets (phone):** grabber 36×4, detents medium (about 50 %) and large (about 92 %), scrim
  at 40 % ink. At the medium detent a sheet is inset 8 from the sides with radius
  `radius-sheet` (32) on all corners; at the large detent it is edge to edge and fully
  opaque. Its grabber row, header and action row are glass; its body is opaque
  `elevated`. No dividers: a 24 px scroll-edge fade under the header. Desktop (≥ 768): a
  centred dialog, max 560.
- **Dock (phone tab bar):**
  - at most 5 destinations (Explore · Bookings · Inbox · Earn · You), with no floating
    create button in the bar (creation lives on Earn and in headers);
  - a floating glass capsule, 64 tall, inset 16 from the sides and
    `max(8, safe-bottom − 12)` from the bottom; icon 24, label `text-caption` 11–12
    medium, 4 between;
  - the active item sits on a 64×52 droplet of `glass-tint-strong` that slides on
    `spring-snappy`; the icon is filled and in `ink`. Inactive icons and labels are
    `ink-2` (`--dock-ink`), never below 4.5:1 on the glass over black or white;
  - the dock never collapses or hides on scroll (owner's call, 2026-09-27): always the
    full five tabs with labels; content scrolls under the glass and ends 16 px above it.
    Under Reduce Transparency it is opaque `elevated` with a `line-strong` edge;
  - every scroll view gets bottom padding = dock height + its bottom inset + 16 so
    content never sits under it;
  - hidden on detail screens; at 200 % text it goes icons-only with aria-labels.
- **Sticky action bar (phone):** one primary action plus at most one secondary, 16 padding,
  above the safe area; it replaces the dock on detail screens, never stacks on it.
- **Toasts:** top of the screen when a sheet or the keyboard is open, else above the
  dock; `role="status"`; 4 s, longer for errors.
- **Route change:** focus moves to the new screen's `h1`; announce via a live region.
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
- Springs: `spring-spatial` (sheets, routes), `spring-snappy` (droplets, chips, menus),
  `spring-bouncy` (the ticket, the category objects, the heart). Glass is pressed by
  scale .96 plus `glass-glow` at the touch point. Glass materialises (scale .6 → 1 from
  its origin, a blur that clears), never a bare fade. The one choreographed moment is
  the booking ticket (and its small version on publish). Scroll-linked effects use
  `animation-timeline: scroll()`, with a class-toggle fallback.

## 6. Imagery and icons

- One icon set, 24 px grid, 1.5–2 px stroke, same corner style. Icons
  with meaning have text or an aria-label.
- Listing photos: the owner's own; fallback is the designed category plate, never
  unrelated stock. Colour placeholder from `photoMeta.color`, `srcset` from renditions.
- Category objects are the nine 3D renders in `web/public/objects/`, 135° key light, the
  brand palette only, used in the category row, on the no-photo plate and in empty
  states. With no photo a listing shows its category object on the lit plate, never a
  grey box. Placeholders are the photo's stored colour or its blurred thumbnail.

## 7. Review checklist: run it on every screen you touch

Sizes: **390×844, 375×667, 360×800, 430×932** (iframes if resizing does not
apply), plus desktop 1440. The safe area cannot be seen in an iframe: add top 47 /
bottom 34 px padding to the frame's root to simulate it, and check `env(safe-area-inset-*)` in code. Each in **light and dark**, **100 % and 200 % text**,
**EN, DE and FR**.

For each screen check:
- every value on the 4 px grid; gutters and section gaps as in §1;
- one primary accent action; every text pair passes §3;
- no text clipped, truncated without ellipsis or overlapping; no horizontal scroll;
- nothing under the dock or the home indicator; sticky bars clear of the keyboard;
- every target ≥ 44 and ≥ 8 apart; focus visible and in order;
- loading, empty, error and offline states exist and match the layout;
- no layout shift when images or data arrive;
- dark mode: surfaces distinct, no glare, badges and active states visible;
- glass: count the glass surfaces (≤ 3); check text on glass over the brightest and
  darkest photo in the seed; toggle `data-glass='lite'`, `data-transparency='reduce'`
  and `prefers-contrast: more`; record a 10 s scroll on a mid-range Android (VD-31) in
  `full`.

Screenshot before and after at 390 in both themes and attach them to the report.
