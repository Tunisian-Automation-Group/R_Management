# 0014. Visual system: glass chrome, photographic content

Status: accepted (2026-09-27)

## Context

The owner's brief (GOAL 19): the app "looks functional but does not attract";
it must be as beautiful as Instagram, Uber, Airbnb or X, with Apple's new
Liquid Glass look (iOS 26). The first UX rounds (UX-46, UX-60) made the dock
and sheets opaque to fix legibility and a weak dark mode. The visual design
lead's research (`docs/research/2026-10-visual-direction.md`) shows how the
best apps get both beauty and legibility: real photographs are the content,
and a thin, lit glass layer carries only the navigation and controls.

## Decision

- **Four planes.** Ground (page, media, the brand's lit green plate), content
  (opaque surfaces), glass (chrome only: dock, top bars, floating buttons,
  sheet chrome, segmented controls, map controls, the hour tag, toasts, menus),
  lift (pressed glass, menus, the booking ticket). Content is never glass.
- **Glass limits.** At most three glass surfaces on screen at once; never
  glass on glass; text on glass only in `ink`/`ink-2` at readable sizes, with
  fills chosen so text keeps at least 7.9:1 (light) and 5.4:1 (dark) over any
  photo (§3.4 of the research).
- **One set of fallbacks** in `theme.css`: no `backdrop-filter`, Reduce
  Transparency (passed in by the shells, since WKWebView does not expose it),
  Increase Contrast, and a low-power `data-glass='lite'` mode. Components never
  branch on them.
- **Budget.** At most 20 % of the phone screen is glass, blur ≤ 20 px on phones,
  and only `transform`/`opacity` animate.
- **Supersedes** UX-46's opaque dock (now a floating glass capsule) and UX-60's
  opaque sheets (glass chrome, opaque body). Light stays the default theme;
  dark is designed as its own theme ("night in the workshop").
- The rules are in the cappy-ui rulebook (`.claude/skills/cappy-ui/SKILL.md`).

## Consequences

- A distinctive, current look that matches the platform (iOS 26) without
  sacrificing legibility or accessibility.
- GPU cost on mid-range Android: the `lite` mode and a device pass (VD-31)
  keep scrolling smooth; true refraction is a desktop-Chromium extra only.
- Every new screen must be checked against the glass rules in the rulebook's
  review checklist, in light and dark and with the fallbacks toggled.
