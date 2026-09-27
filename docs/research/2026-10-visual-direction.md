# Cappy visual direction: glass over the workshop (2026-10)

The visual design lead's art direction for Cappy. It follows the two UI/UX
review rounds in [`2026-09-ui-ux-review.md`](2026-09-ui-ux-review.md). Those
rounds were about craft and conformance. This one is about **attraction**. In
the owner's words, "now it looks functional but does not attract". They want
Apple's Liquid Glass ("the new apple mirror screen ui") and the pull of
Instagram, Uber, Airbnb and X.

This document proposes. It changes no code. The VD-n checklist at the end is
copied into [`../TASKS.md`](../TASKS.md). Phase 2, the build, starts separately.

**How the app was seen (2026-09-26, at `e50a24a` plus the uncommitted web round):**
- Chrome on `http://127.0.0.1:5173`, signed in as Demo Host Two. No data was changed.
- Desktop: a 1440 × 1000 same-origin iframe, and the 900 px window itself.
- Phone: 390 × 844 iframes in light and dark. Dark was set on each frame's `<html data-theme>`, not saved as a preference.
- Screenshots of the current state, in the session scratchpad (`$SP` below):
  - `vd-before/desktop-explore-light.jpg`
  - `vd-before/desktop1440-explore-listing.jpg`
  - `vd-before/phone-explore-listing-bookings-earn-light.jpg`
  - `vd-before/phone-explore-inbox-earn-you-dark-and-light.jpg`

`$SP` = `/private/tmp/claude-501/-Users-seifguerbouj-Documents-personal-R-Management/eef0acf8-baf0-462c-94e8-b0b437fb30fd/scratchpad`.
The scratchpad belongs to this session. The images are copyrighted
press and App Store material, so they are **not** committed. Every one of them
has a public URL below and can be downloaded again.

### What the app looks like today, in one paragraph

The system is careful and correct: a real type ramp, tabular figures, measured
contrast, one accent, a surface ladder in dark. It is also **flat**. Pages are
paper and hairlines, and cards are grey boxes until a photo lands. When a photo
lands it is often the wrong one: smokestacks for a 3D printer, still first on
Explore and on the listing. There is nothing behind the chrome for glass to
bend. The dock is an opaque bar (UX-46), the sheets are opaque, and the one
glass surface (the sticky price bar) floats over paper, where glass reads as a
grey box with a shadow. Nothing moves except the transitions between screens.
The green plate, the identity's best idea, appears only as an empty "clock"
placeholder. The Earn hero "€8,628.75 of time nobody is paying you for" is the
most striking figure in the app, and it scolds. The app is legible, but it has
no light, no depth and no moment you would show a friend.

---

## 1. Moodboard

Local paths are under `$SP/refs/`. The App Store images are the 600 × 1300
renditions of each app's current US listing (fetched through the iTunes
lookup API, 2026-09-26).

### 1.1 Liquid Glass: the material itself

| Ref | Source | What to take |
|---|---|---|
| Liquid Glass across devices | https://www.apple.com/newsroom/images/2025/06/apple-introduces-a-delightful-and-elegant-new-software-design/article/Apple-WWDC25-Liquid-Glass-hero-250609_big.jpg.large.jpg · `refs/apple-lg-hero.jpg` | Glass controls always sit over **rich content** (a film poster, a wallpaper). It is never glass on white. |
| Home Screen, clear look | https://www.apple.com/newsroom/images/2025/06/apple-introduces-a-delightful-and-elegant-new-software-design/article/Apple-WWDC25-Liquid-Glass-Home-Screen-clear-look-250609_big.jpg.large.jpg · `refs/apple-lg-clear.jpg` | The "clear" variant: almost no fill, a bright lit rim, and the content carries the colour. |
| Dark tint | https://www.apple.com/newsroom/images/2025/06/apple-introduces-a-delightful-and-elegant-new-software-design/article/Apple-WWDC25-Liquid-Glass-Home-Screen-dark-tint-250609_big.jpg.large.jpg · `refs/apple-lg-darktint.jpg` | Dark glass is smoked, not black: the rim stays visible and the fill is about 60–70 %. |
| iOS 26 hero | https://www.apple.com/newsroom/images/2025/06/apple-elevates-the-iphone-experience-with-ios-26/article/Apple-WWDC25-iOS-26-hero-250609_big.jpg.large.jpg · `refs/apple-ios26-hero.jpg` | A floating capsule tab bar inset from the edges; toolbar groups as separate glass capsules. |
| iOS 26 Home Screen (light, dark, clear) | https://www.apple.com/newsroom/images/2025/06/apple-elevates-the-iphone-experience-with-ios-26/article/Apple-WWDC25-iOS-26-Home-Screen-customization-250609_big.jpg.large.jpg · `refs/apple-ios26-home.jpg` | The same layout in three appearances. Widgets are glass panes with a specular top edge; the dock is one capsule. |
| Icon Composer | https://www.apple.com/newsroom/images/2025/06/apple-introduces-a-delightful-and-elegant-new-software-design/article/Apple-WWDC25-Liquid-Glass-Icon-Composer-250609_big.jpg.large.jpg (not downloaded) | Layered icons: a flat foreground over a lit glass layer. This is for the app icon, VD-27. |
| Apple Maps on iOS 26 | https://is1-ssl.mzstatic.com/image/thumb/PurpleSource221/v4/db/9e/0a/db9e0ae3-a3e5-8a6a-1616-a5f35aed16d5/Maps-iPhone6p9-RaveA-USEN-Wrapper1.png/600x1300bb.jpg · `refs/apple-maps-1.jpg` | Glass controls float on the map in one vertical capsule; the guidance card is glass with bold white type. |
| Apple Maps place card | https://is1-ssl.mzstatic.com/image/thumb/PurpleSource221/v4/01/1b/c7/011bc737-5b1c-3eba-c26a-70596e0839bc/Maps-iPhone6p9-RaveA-USEN-Wrapper2.png/600x1300bb.jpg · `refs/apple-maps-2.jpg` | A full-bleed photo with glass buttons over it, then an opaque content card. **Media under clear glass, text on opaque.** |
| Wikipedia, Liquid Glass | https://en.wikipedia.org/wiki/Liquid_Glass | Reception was mixed on legibility. Apple raised navigation-bar opacity during the betas and later added a clear-to-tinted slider. Legibility cannot be an afterthought. |

**What Apple actually specifies.** The quotes are from the WWDC25 session
"Meet Liquid Glass" (https://developer.apple.com/videos/play/wwdc2025/219/),
"Get to know the new design system"
(https://developer.apple.com/videos/play/wwdc2025/356/), the HIG
Materials and Color pages, and "Adopting Liquid Glass".

- **Layers.** Glass is "a distinct functional layer for controls and navigation … that floats above the content layer". The rule is "Don't use Liquid Glass in the content layer." The exceptions are transient controls, such as sliders and toggles while they are being dragged. Avoid glass on glass.
- **Lensing and refraction.** The material "bends, shapes, and concentrates light". Larger pieces simulate "a thicker, more substantial material": deeper shadows, more lensing, softer scattering.
- **Specular highlights.** Light "travel[s] around the material, defining its silhouette" and responds to device motion.
- **Adaptive shadow.** The shadow gets stronger over text and weaker over a plain light background.
- **Adaptive tint.** Small elements (tab bars, toolbars) flip between light and dark with the content under them. Their symbols go dark over light content and light over dark content. Big elements (menus, sidebars) adapt but don't flip, and are "more opaque".
- **Regular and clear.** Regular is the default, legible over anything. Clear has no adaptive behaviour and is used only over media. It needs a dimming layer: "consider adding a dark dimming layer of 35% opacity". The two "should never be mixed".
- **Colour.** "Liquid Glass has no inherent color." Tint only the primary action, "apply color to the background rather than to symbols or text", and "Avoid tinting all your elements". Put colour in the content layer instead.
- **Motion.** Glass "materialize[s] in and out by … modulating the light bending", rather than fading. It "illuminates from within" under the fingertip, and the glow spreads to nearby glass. It is "gel-like", and controls "lift up into Liquid Glass temporarily" when touched. Menus "pop open" from the button. Controls morph between states as "a singular floating plane".
- **Scrolling.** Tab bars "shrink … when scrolling, then fluidly expand" (`tabBarMinimizeBehavior(.onScrollDown)`). The **scroll edge effect** replaces dividers with a soft blur and fade of the content under a bar. Over dark content it switches to a dimming.
- **Sheets.** Half sheets are "inset from the edge of the display" with "an increased corner radius". At full height a sheet becomes "more opaque", and the glass "subtly recedes … gently growing in size". A task that interrupts the flow pairs glass with a dimming layer.
- **Shapes.** Concentric corners mean child radius = parent radius − padding. Capsules for bars, buttons and switches.
- **Type.** "Bolder and left-aligned". Hierarchy comes "through layout and grouping", not decoration, and toolbar items are grouped by function.
- **Accessibility.** Reduce Transparency makes glass "frostier". Increase Contrast makes elements "predominantly black or white … with a contrasting border". Reduce Motion "disables any elastic properties".
- **Performance.** "Combine them using a `GlassEffectContainer`". The web equivalent: few glass surfaces, grouped.

### 1.2 Airbnb (2025 Summer release)

| Ref | Source | What to take |
|---|---|---|
| New tab row with 3D icons | https://news-assets.withairbnb.com/wp-content/uploads/sites/21/2025/05/All-new-app-US.jpg · `refs/airbnb-news-all-new-app.jpg` | **The single most useful reference.** Homes, Experiences and Services are rendered 3D objects (a house, a hot-air balloon, a service bell), about 56 px, over a white capsule search. The active one has an underline and bold label, and a "NEW" badge in glossy navy. The objects carry the delight while the chrome stays quiet. |
| App Store carousel 1–4 | https://is1-ssl.mzstatic.com/image/thumb/PurpleSource211/v4/f0/ac/bc/f0acbcae-22dd-00fd-4b92-ef19cd02a991/250509_AppStore_Mobile_Airbnb_Carousel_01_en-US.jpg/600x1300bb.jpg (and `_02` … `_04` in `refs/index.json`) · `refs/airbnb-1.jpg` … `airbnb-4.jpg` | Warm cream marketing ground with one 3D object per screen. Photo-first cards at a 20 px-ish radius with a "Guest favorite" pill and a heart **on the photo**. Titles in 15–17 px semibold, price in bold. |
| Services detail | https://news-assets.withairbnb.com/wp-content/uploads/sites/21/2025/05/Services-flow-PDP-US.jpg · `refs/airbnb-news-services-pdp.jpg` | The service's own photography, with the host's face. The offering is the hero, not the UI. |
| Trips | https://news-assets.withairbnb.com/wp-content/uploads/sites/21/2025/05/Trips-tab-US.jpg · `refs/airbnb-news-trips.jpg` | Bookings as a day-by-day story, each with a photo. This is the model for Cappy's Bookings. |
| Newsroom | https://news.airbnb.com/airbnb-2025-summer-release/ | "a design system with a dimensional and beautifully animated interface". |

**Why it attracts:**
- Warmth: people, rooms and food in available light.
- **Dimensional icons** that are fun without being childish.
- Generous white and large radii.
- One bright colour (Rausch), spent on the search button and the reserve button.
- Motion: the 3D icons bounce on selection, and the search capsule expands into a full-screen step sheet.

### 1.3 Uber (Base)

| Ref | Source | What to take |
|---|---|---|
| Pickup map | https://is1-ssl.mzstatic.com/image/thumb/Purple211/v4/9c/b7/e7/9cb7e71e-7241-121f-3f24-ecb74cce25ce/6cf2abb7-d8c1-49e0-96f5-88dc3b1bdc20_SS01.png/600x1300bb.jpg · `refs/uber-1.jpg` | The map is the content. Floating round controls and callout capsules ("Pickup spot · Change", "2 min") sit on it, and a bottom sheet holds the one decision. |
| "GO ANYWHERE" | https://is1-ssl.mzstatic.com/image/thumb/Purple211/v4/1d/06/9f/1d069f7e-0ae3-0f1a-d6e1-507fa9498599/5921dcb5-b558-4369-b72c-85c22f89742d_SS02.png/600x1300bb.jpg · `refs/uber-2.jpg` | Brand confidence from **type alone**: black ground, huge Uber Move, one product silhouette. |
| Destination entry | https://is1-ssl.mzstatic.com/image/thumb/Purple221/v4/d4/8f/69/d48f69f2-ce36-3b66-2cc3-39e32fd0ce78/ca2de83c-8c8e-4887-94f4-3ae11c83d7cc_SS03.png/600x1300bb.jpg · `refs/uber-3.jpg` | Density done right: 56 px rows, a leading icon, two lines, no ornament. |
| Base | https://base.uber.com/ (the site is script-rendered; its text could not be fetched) | The system as known: black and white first, colour only for state, Uber Move / Move Text, a 4/8 grid, and motion that follows the vehicle. |

**Why it attracts:** radical restraint, so that the one thing (your car, your
time) is loud. For Cappy this is the model for the map, the booking detail and
Inbox rows.

### 1.4 Instagram (2025)

| Ref | Source | What to take |
|---|---|---|
| Reels | https://is1-ssl.mzstatic.com/image/thumb/PurpleSource221/v4/50/e2/8b/50e28b44-daa5-7101-6fb6-2d0e10fc72f3/1_iOS_5.5.jpg/600x1300bb.jpg · `refs/instagram-1.jpg` | Full-bleed media. The chrome is white glyphs with a soft shadow, with no bars. The 2025 tab order is Home · Reels · DMs · Search · Profile. |
| Comments sheet | https://is1-ssl.mzstatic.com/image/thumb/PurpleSource211/v4/10/38/e1/1038e1c7-751f-c4ea-39b9-d9f4d08fc08d/2_iOS_5.5.jpg/600x1300bb.jpg · `refs/instagram-3.jpg` | A medium-detent sheet over media; the media stays visible above it, and there is an emoji rail. |
| Share | https://is1-ssl.mzstatic.com/image/thumb/PurpleSource211/v4/d4/d0/6d/d4d06d20-f442-2b7c-8a4e-24d427542910/3_iOS_5.5.jpg/600x1300bb.jpg · `refs/instagram-4.jpg` | Capsule controls over the photo; the send arrow is the one blue fill. |

**Why it attracts:**
- Media edge to edge.
- Micro-interactions people remember: the double-tap heart burst, story rings, the like-count roll.
- The brand gradient is kept for rare moments.

The first two come to Cappy as the listing photo and the heart. The third comes
as the booking-confirmed ticket, the one moment.

### 1.5 X and Threads

| Ref | Source | What to take |
|---|---|---|
| X timeline | https://is1-ssl.mzstatic.com/image/thumb/PurpleSource211/v4/ba/d3/7a/bad37ad7-811c-7dda-9916-1ee121d459eb/X_SS1__U0028App_Store_U0029.jpg/600x1300bb.jpg · `refs/x-1.jpg` | True black and thin separators, with a big bold marketing headline. Density and speed. |
| X feed close-up | https://is1-ssl.mzstatic.com/image/thumb/PurpleSource211/v4/14/40/2e/14402eb4-b3eb-ef64-fb88-5975c8908deb/X_SS2__U0028App_Store_U0029.jpg/600x1300bb.jpg · `refs/x-2.jpg` | Tabular counts under each post, and a monochrome icon row. |
| Threads | https://is1-ssl.mzstatic.com/image/thumb/PurpleSource211/v4/d5/49/26/d5492635-4b10-1582-0b1d-289386503854/01_iOS-1242x2688-Join-the-conversation_en_US.png/600x1300bb.jpg · `refs/threads-1.jpg` | Monochrome UI, with the brand only in a highlighter-yellow marker on the headline word. |
| Threads thread | https://is1-ssl.mzstatic.com/image/thumb/PurpleSource221/v4/08/e2/38/08e238a3-fb2f-83fa-17b1-85f1a82f48ff/02_iOS-1242x2688-Discover-new-takes_en_US.png/600x1300bb.jpg · `refs/threads-2.jpg` | The poll is a filled bar with its percent right-aligned. It is the model for Cappy's capacity bars in the Inbox and Earn. |

**Why they attract:**
- Speed and legibility.
- A dark mode that is the brand, not an afterthought: X's "Lights out" is true black.

**What Cappy takes:** the Inbox and thread density, and a dark theme designed
on its own terms. Cappy does not take pure black: its dark is green-black, the
night version of the plate.

### 1.6 Revolut

| Ref | Source | What to take |
|---|---|---|
| Metal card | https://is1-ssl.mzstatic.com/image/thumb/PurpleSource211/v4/3e/60/43/3e604383-973c-bcc4-d838-a0264860b4ee/Screen_1_1242x2208.jpg/600x1300bb.jpg · `refs/revolut-1.jpg` | A **rendered physical object** under studio light. The product is made to look precious. |
| Savings | https://is1-ssl.mzstatic.com/image/thumb/PurpleSource221/v4/7b/10/8e/7b108e10-1439-6762-215f-4d2f18494702/Screen_2_1242x2208.jpg/600x1300bb.jpg · `refs/revolut-2.jpg` | A huge balance figure ("$5,325.80", with the cents smaller) over a **photo wallpaper**, and glass cards over the photo holding small figures. **This is Earn.** |
| Payments chat | https://is1-ssl.mzstatic.com/image/thumb/PurpleSource221/v4/ed/f0/f4/edf0f424-5f32-514c-4e6d-3df77a421617/Screen_3_1242x2208.jpg/600x1300bb.jpg · `refs/revolut-3.jpg` | Money inside a conversation as glass bubbles with big figures. This is the model for Cappy's system messages ("€16.00 held"). |

**Why it attracts:**
- Numbers set as display type.
- Dark photographic backgrounds with glass panes: glass has something to refract.
- Rendered 3D objects.

### 1.7 Vinted, Spotify, Linear

| Ref | Source | What to take |
|---|---|---|
| Vinted "Sell with no fees" | https://is1-ssl.mzstatic.com/image/thumb/PurpleSource211/v4/2e/e0/46/2ee0465a-3721-3631-14f5-d42b7b998ee3/1_-_App_store_-_USA_-_6_U002c5_inch.png/600x1300bb.jpg · `refs/vinted-1.jpg` | A **serif display on a deep brand colour** (teal) with real people's photos. This is the closest living cousin of Cappy's Bodoni on the green plate, and proof that the editorial look sells in a marketplace. |
| Vinted sell flow | https://is1-ssl.mzstatic.com/image/thumb/PurpleSource221/v4/bc/38/45/bc384593-d57b-76e5-7e27-c6d130dd5ff1/2_-_App_store_-_USA_-_6_U002c5_inch.png/600x1300bb.jpg · `refs/vinted-2.jpg` | Photos first, then the title, then the description: a listing in three fields. The model for Add listing. |
| Spotify home | https://is1-ssl.mzstatic.com/image/thumb/PurpleSource211/v4/f3/ce/05/f3ce0547-690a-b355-b1dd-6b6e91808279/IOS_-_5.5_-_S01_-_EN_-_CA_U005bEnglish__U0028Canada_U0029_U005d.png/600x1300bb.jpg · `refs/spotify-1.jpg` | Colour pulled from artwork into the page (the header wash), with dense tiles. |
| Spotify now playing | https://is1-ssl.mzstatic.com/image/thumb/PurpleSource211/v4/78/81/ca/7881ca10-b441-1a6c-e030-92e08dd76144/IOS_-_5.5_-_S02_-_EN_-_CA_U005bEnglish__U0028Canada_U0029_U005d.png/600x1300bb.jpg · `refs/spotify-2.jpg` | The media's colour floods the screen behind the controls. The source of Cappy's **ambient photo tint** (§2.6). |
| Linear redesign | https://linear.app/now/how-we-redesigned-the-linear-ui · https://webassets.linear.app/images/ornj730p/production/d4d07b82ac6aca081b58ebaada78c0d99858beb5-4112x1888.png · `refs/linear-redesign-1.png` | Themes generated in LCH, so light, dark and high contrast come from one set of inputs. Less chrome and more contrast. Inter Display for headings over Inter. The model for how Cappy's dark and Increase Contrast tokens are derived. |

### 1.8 Web implementation references

| Ref | What to take |
|---|---|
| https://kube.io/blog/liquid-glass-css-svg/ | Real refraction on the web: an SVG `feDisplacementMap` fed by a precomputed map from a convex-squircle profile, a specular rim through `feBlend`. **"Only Chrome currently supports using SVG filters as backdrop-filter".** So it is useless in the iOS shell (WKWebView) and Safari. Changing the shape means rebuilding the map. |
| https://www.joshwcomeau.com/css/backdrop-filter/ | `backdrop-filter` only sees the pixels directly behind the element. Extend the backdrop layer (`height: 200%`) and `mask-image` it back, so nearby colour bleeds in. `pointer-events: none` on the layer. A second thin layer with `blur(8px) brightness(120%)` fakes thickness on the edge. |
| https://css-tricks.com/getting-clarity-on-apples-liquid-glass/ | Apple's three layers are highlight, shadow and illumination; nested elements mimic them. The warning: translucency creates "variable contrast ratios", so a design that passes over one background fails over "a bright photo of the sunset". |
| https://blog.master.dev/liquid-glass-on-the-web/ | The survey of approaches (displacement, SVG filters, `liquid-glass-react`), and the contrast criticism. |
| https://developer.mozilla.org/en-US/docs/Web/CSS/backdrop-filter | Baseline 2024, and Safari still wants `-webkit-`. **Backdrop roots:** an ancestor with `opacity < 1`, `filter`, `mask`, `clip-path`, `mix-blend-mode` or its own `backdrop-filter` cuts the blur off. The existing `.glass` comment in `theme.css` already knows this. |
| https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-transparency | Not Baseline. Chromium supports it; Safari and WKWebView don't expose it yet. The iOS shell has to pass Reduce Transparency in itself (VD-21). |

---

## 2. Art direction for Cappy

### 2.1 Concept: glass over the workshop

Cappy is a window onto real workshops, vans, studios and machines at the
hours they stand free. **The content is warm, true photography of the actual
thing in its actual place**, the way Airbnb shows rooms and Vinted shows
people. **The chrome is a thin sheet of lit glass floating above it**, and it
only exists where you touch. Between the two sits the brand's deep material,
the **green plate**. It is the dark, polished surface where time becomes
yours: the Welcome, the hour you just booked, the money you just earned. The
product is the hour, so the signature element is **the hour tag**. It is a small
glass lozenge ("Free 14:00–18:00") that rides on every photo. It travels, as
one shared element, from the card to the listing, into the booking sheet, and
finally becomes the ticket you keep. There is one bold thing, the hour tag and
its ticket. Everything around it stays quiet, precise and tabular, as the
departure-board idea always intended.

### 2.2 How the identity evolves

| Today | Keep, change or drop | Why |
|---|---|---|
| Bodoni Moda display | **Keep, but rarer and bigger.** Bodoni only for *moments*: Welcome, the Explore greeting, the booking ticket, the Earn hero word, empty states. It always runs at ≥ 34 px (≥ 44 in dark), set tight (−0.03 em) at optical size 96. Screen titles (Bookings, Inbox, Earn, You) move to **Archivo at width 112, weight 700, 34/40**, left-aligned: the iOS 26 large title, bolder. | Vinted proves a serif on a deep colour sells. But today Bodoni labels *every* screen, so nothing is special. Uber, Revolut and Airbnb all use a confident grotesque for titles. Archivo's width axis (62–125) is already shipped (`@fontsource-variable/archivo` covers `font-stretch: 62% 125%`), so this costs no new font. |
| Archivo body, tabular figures | **Keep.** Add a wide display figure style: Archivo width 125, weight 800, 56–64 px, cents at 60 %. It is used for the one hero number per screen (the listing price, Earn, the ticket time). | Revolut's balance figure is the most desirable number on a phone. Figures are Cappy's content. |
| Green plate `--field` #20311e | **Keep; give it light.** The plate becomes a lit material: a radial light from the top left (the same 135° light as the glass rim), a 2 % film grain, and a 1 px lit top edge. It is used for the Welcome, the Explore greeting band, the ticket, the Earn hero and the host's own listing cards. It is no longer the "no photo" placeholder (that becomes the category's 3D object on the plate, §2.5). | Glass needs something rich beneath it. On flat paper it is a grey box. The plate is the one brand surface that can carry glass beautifully. |
| Crimson accent #8b0d1a | **Keep the hue, raise the light:** #b0182e in light (white on it 6.96:1, on page 6.67:1) and #f2606d in dark (dark ink on it 6.24:1, up from 5.19). Still exactly one filled control per view. The primary button becomes a **capsule tinted glass** on media (Apple's "glassProminent") and a solid capsule on paper. | #8b0d1a reads as maroon, heavy and dim beside Airbnb's Rausch or Instagram's blue. #b0182e is still crimson (not pink, not the danger red #c4312b) and is visibly alive. Apple: tint the primary action's background, nothing else. |
| Ice #d0e0e3 on the plate | **Keep** as the colour of free time on the plate: the hour tag's text on the plate, and idle bars. | 10.2:1 on the plate. It is the second brand colour and it is earned. |
| Hairlines and ruled rows | **Keep in lists, drop as section decoration.** Section tops lose the 1 px black rule and gain space plus the scroll edge effect. | Apple: "Scroll edge effects replace hard dividers". The heavy rule above every section is the most "broadsheet template" part of today's screens. |
| Radii 8 / 14 / 22 | **Rounder and concentric:** control capsule, field 12, card 20, plate 24, sheet 32, with image radius = card radius − inset. | iOS 26 and Airbnb 2025 both went rounder. Concentric radii are what make glass read as machined rather than stuck on. |
| Opaque dock bar (UX-46) | **Replace with a floating glass capsule** (§3.2). It has a lensed "droplet" indicator. *(2026-09-27, owner: dropped. The dock never collapses or hides on scroll; always the full five tabs with labels, content scrolls under the glass and ends 16 px above it.)* | The owner asked for this by name. It is also the platform's own tab bar now. UX-46's reasons (safe area, 5 tabs, badges, 200 % text) all still hold and are kept. |
| Opaque sheets | **Glass chrome, opaque body** (§3.2). | Apple: half sheets inset and glass; full height goes more opaque. Text areas never on glass. |

### 2.3 Hero moments

1. **Explore:** "what is free near you right now". A lit green greeting band carries the Bodoni greeting ("Free near you") and the glass search capsule. Under it sit the **3D category objects**, then a horizontal rail of full-bleed photo cards, each wearing its hour tag.
2. **The listing:** a full-bleed photo to the top edge, under a status bar. Clear-glass back, share and heart float on it. The page wears the photo's own colour (ambient tint). The price is a wide display figure. The sticky bar is a glass capsule with the hour tag and "Request".
3. **Booking confirmed:** the only choreographed moment in the app (§2.8). The hour tag lifts out of the sheet, flies to the centre and becomes a **ticket on the green plate**. The time rolls in, a light sweeps once, and one success haptic plays.
4. **Earn:** a Revolut-style hero. Not guilt ("nobody is paying you") but what you have and what's next: a large figure ("€28.05 earned this week"), and under it a glass capacity strip of the week over the plate. The idle hours become an invitation ("136 free hours this week. Open some?").

### 2.4 Imagery

- **What:** the actual thing, in its actual place, in use or ready to use. A Bambu H2D on a bench with a print on the bed, not smokestacks. A van with its doors open at a kerb. A studio with its lights on.
- **Light:** available or soft window light, slightly warm (about 4500–5200 K). No flash, no HDR, no stock blue-teal grade.
- **Framing:** the listing cover is 4:3, with the subject centred in the middle 60 %, because the hour tag and heart take the corners. Include a hand or a person for scale in one of the first three photos when the owner has one. The rail cards on Explore crop to 4:5.
- **Colour placeholder:** every photo has a stored dominant colour (`photoMeta.color`, UX-69). The grey `--sunken` box goes away everywhere; the placeholder is that colour with a 12 px blurred thumbnail (LQIP) when one exists.
- **Ambient tint:** the listing page and the booking sheet take `--ambient` from the cover photo's colour. The top 320 px of the page is a wash of it (§5), and glass over it picks it up, as Spotify and Apple Music do.
- **No photo:** the category's 3D object sitting on a lit plate, with the listing title in white. It never falls back to unrelated stock, and never to a grey box.
- **Seed and demo:** UX-53 stands and is now P0 for the visual work. The visual direction fails with wrong photos however good the glass is.
- **Host guidance** (Add listing): a three-shot recipe shown with illustrations. The whole thing in context, a detail, and it in use.

### 2.5 Iconography

- **Category objects, 3D (new).** Nine rendered objects, one per category, in the Airbnb 2025 manner but Cappy's own material:
  - Fabrication: a milling head. 3D printing: a small printer with a print. Finishing: a spray gun. Print & signage: a roll of vinyl. Freight: a small van. Warehousing: a pallet with boxes. Workshop & tools: a plunge saw. Event & AV: a speaker. Creator kit: a camera on a tripod.
  - Style: matte clay-and-metal, a soft top-left key light (the same 135° as the glass rim), a contact shadow. Palette limited to paper, ink, plate green, ice and one crimson detail per object.
  - Rendered at a consistent 30° camera. Shipped as 96 and 192 px WebP/AVIF with alpha (under about 12 KB each), plus a 24 px line fallback.
  - Used in the Explore category row (56 px), the no-photo plate (120 px), empty states (96 px) and the Welcome examples.
  - On selection the object springs (scale 1 → 1.12 → 1, `--spring-bouncy`) and gets a soft floor shadow. There is no idle animation.
- **UI icons stay line icons** (`Icon.tsx`, 24 grid, 1.75 stroke), plus a **filled variant** for the active dock item and the saved heart. Symbols on glass are monochrome (Apple); only the primary action is tinted.
- **App icon.** A layered icon for iOS 26: the "C" hour-hand mark in ink on a glass layer over the plate green. It is built in Icon Composer with light, dark and clear variants (VD-27).

### 2.6 Depth and elevation with glass

Four planes, back to front:

| Plane | What lives there | Material |
|---|---|---|
| 0 Ground | the page, full-bleed photos, the map, the plate | paper (`--page`), media, `--plate` |
| 1 Content | cards, lists, text, forms, the opaque body of sheets | opaque `--surface` / `--elevated`, a hairline or `--shadow-1`, never both. **Never glass.** |
| 2 Glass | dock, top bars (once content scrolls under), floating buttons, sheet chrome (grabber row, header, action row), segmented controls, map controls, the hour tag, toasts | Liquid Glass tokens (§3.3) |
| 3 Lift | a glass control being pressed, a menu popping from a button, the ticket | glass with `--glass-shadow-raised` plus the press glow |

Rules:
- Glass never sits on glass. Where a sheet's glass header meets the dock, the dock hides, as it already does on detail screens.
- In a steady state nothing overlaps glass (Apple). On load, content starts below the top bar. Glass only floats over content once you scroll.
- Elevation in dark is **lighter surface plus a rim**, never a heavier shadow alone.

### 2.7 Motion language

Everything moves on **springs**, sampled into `linear()` tokens (§5), and only
`transform` and `opacity` animate (the rulebook §5 still holds). Three springs:
- `--spring-spatial` (exists): sheets and routes.
- `--spring-snappy` (new, 320 ms, damping 0.82): the dock droplet, segmented controls and chips.
- `--spring-bouncy` (new, 700 ms, damping 0.55): the ticket, the 3D category objects, the heart.

| Moment | Motion |
|---|---|
| Tap any glass control | Press: scale 0.96 and the **press glow** (a radial light at the touch point, `--glass-glow`) within 100 ms. Release: spring back with a slight overshoot (`--spring-snappy`). This is Apple's "illuminates from within". |
| Dock tab change | The droplet indicator slides to the new tab on `--spring-snappy`, stretching 12 % horizontally mid-flight and settling ("gel-like"). The new icon swaps to its filled variant at the midpoint. |
| Scroll down on a tab screen | The dock **shrinks**: the capsule scales to a compact capsule showing only the active icon plus a separate round search button, scroll-linked for the first 64 px and then snapping. Scroll up or tap it to expand. It replaces today's hide-on-scroll. *(2026-09-27, owner: dropped. The dock never collapses or hides on scroll; always the full five tabs with labels, content scrolls under the glass and ends 16 px above it.)* |
| Card → listing | Shared elements through the View Transitions API (UX-59): the photo, the title and **the hour tag** morph. The hour tag is named only on the tapped card. The rest of the listing rises 16 px and fades in on `--ease-decelerate`. |
| Listing scroll | Scroll-linked (`animation-timeline: scroll()`). The hero photo translates at 0.5× (parallax) and scales 1 → 1.06 on overscroll. The top bar's glass fill goes from 0 to full while the photo leaves (the scroll edge effect), and the title fades into the bar. The fallback is an IntersectionObserver that toggles a class. |
| Sheet open | Rises from the sticky bar's capsule: the capsule's glass **morphs** into the sheet's header (a shared element), and the body fades in underneath. Dragging up makes the glass recede to opaque (Apple). |
| Menus (⋯) | Pop from the button: scale from the button's origin 0.6 → 1 on `--spring-snappy`, with a blur that clears as it opens ("materialises"). |
| Heart | Bouncy scale 1 → 1.25 → 1, the fill wipes in, a light impact haptic. |
| Prices and counts that change | Digits roll vertically, like an odometer (tabular figures make this clean), 250 ms. |
| Skeletons | Only after 300 ms (rule stands). They shimmer once along the light direction, never looping. |
| Reduce Motion | Every movement becomes a 100 ms fade. No parallax, no droplet stretch, no springs overshoot; the ticket appears in place. |

### 2.8 The booking-confirmed moment

This is the one choreographed moment in the app. It runs when a request is
sent or an instant booking is paid, and lasts 1.4 s in total. Every step is a
transform or an opacity.

1. **0 ms:** the confirm button contracts into a spinner capsule while waiting. On success it flashes the ink check.
2. **120 ms:** the hour tag in the sheet lifts: `--glass-shadow-raised`, scale 1.08. The sheet body fades out behind it and the scrim deepens to the plate.
3. **200–700 ms:** the tag flies to the upper third on `--spring-bouncy` and unfolds into the **ticket**. It is a plate-green card with:
   - a perforated edge between its stub and its body;
   - the listing photo as a round thumbnail;
   - the day in Bodoni ("Saturday");
   - the time as a wide display figure ("14:00–18:00"), whose digits roll in;
   - the place and the host's first name.
4. **700 ms:** one `notification(success)` haptic. A specular sweep crosses the ticket once, top-left to bottom-right, 500 ms.
5. **900–1400 ms:** under the ticket, three glass actions materialise in sequence, 60 ms apart: "Message Nadia", "Add to calendar", "Directions" (after acceptance). "Done" returns to the booking.

- **A request** says "Requested. Nadia usually replies in ~12 min", and the ticket shows a "Waiting for Nadia" stub in ice.
- **An instant booking** says "Booked", and the stub shows "Paid €16.00" in `--money`.
- **Reduce Motion:** the ticket appears in place with a 100 ms fade and a static highlight.

### 2.9 Haptics mapping

It needs `@capacitor/haptics`, which is not installed today. It is a no-op on
the web; `navigator.vibrate` is never used. There is a "Haptics" switch in You
→ Preferences. This extends UX-68.

| Event | iOS (UIFeedbackGenerator) / Android (HapticFeedbackConstants) |
|---|---|
| Dock tab change, segmented control, chip toggle | `selectionChanged` / `CLOCK_TICK` |
| Scrubbing the day strip or hours, each step | `selectionChanged` / `CLOCK_TICK` |
| Sheet snaps to a detent | `impact(.light)` / `CONTEXT_CLICK` |
| Heart on, glass control long-press | `impact(.light)` / `LONG_PRESS` |
| Pull to refresh commits | `impact(.medium)` / `CONFIRM` |
| Booking confirmed, request accepted, listing published, payout sent | `notification(.success)` / `CONFIRM` |
| Card declined, slot taken while booking | `notification(.error)` / `REJECT` |
| Destructive confirm (withdraw, delete) | `notification(.warning)` / `REJECT` |

### 2.10 Dark mode as its own theme

Dark is **night in the workshop**, not paper inverted.
- **Ground:** the green-black ladder of UX-47 stays as it is: `page` #121813 … `pill` #404c42. It was measured and fixed a round ago, so it is not churned.
- **Ambient light:** the top of the Explore, Earn and You screens carries a soft plate-green glow (`--ambient-night`, a radial gradient from `--field` at 60 % to transparent). The screen feels lit from the top, as a room at night is lit by one lamp. The listing screen's glow comes from its photo instead (`--ambient` at 30 %).
- **Photos:** stay dimmed about 10 % (rule). Glass over them is smoked (`--glass-tint` dark, α .72), with its rim at 22 % white, so the silhouette is drawn by light, not by a border.
- **Type:** Bodoni only ≥ 44 px in dark (up from 34; it is now used only at display sizes anyway). Archivo titles at width 112 hold up in dark where Bodoni's hairlines don't.
- **Accent:** crimson #f2606d with dark ink text. It is still one per view, and it glows a little: a 0 0 24 px −8 px shadow in the accent at 40 %, on the primary only. It is the one "neon" allowed, and it marks the action.
- **The plate** in dark is a lighter, more saturated green (#1f3a24 → keep), with a lit rim, so it reads as a material above the page rather than a hole.
- **Contrast** is measured exactly as in light: `check:contrast` gains the glass-worst-case pairs (§3.4).

---

## 3. Liquid Glass spec for Cappy

### 3.1 Where glass is used and where it is never used

**Glass (plane 2):**
- the phone dock (a floating capsule) and the compact search button beside it;
- the desktop top bar, once content scrolls under it (transparent at rest);
- phone top bars on detail screens: back, share and heart over photos (the **clear** variant), and title bars once scrolled (the **regular** variant);
- floating buttons: the map/list toggle, "Filters" on results, "Show map";
- the sheet chrome, meaning the grabber row, the sheet's header, and the sticky action row of the booking sheet;
- segmented controls (I booked / I'm hosting; All / Unread) as a glass track with a sliding droplet;
- the map controls: the zoom and locate capsule and the price pins' selected state;
- the hour tag on photos (clear) and on the plate (plate glass);
- toasts;
- menus popping from ⋯.

**Never glass:**
- cards, list rows, listing text, reviews, prices in content, forms, text areas, the chat body, message bubbles;
- the body of any sheet or dialog (opaque `--elevated`);
- anything that scrolls;
- anything under 32 px.

The number of glass surfaces on a screen at once: **at most three** (for example dock + top bar + one floating group). Where more are needed, group them into one capsule, the web's `GlassEffectContainer`.

### 3.2 Components

**Dock (phone, replaces UX-46's bar):**
```
            safe-area gutter 16                                   16
 ┌──────────────────────────────────────────────────────────┐  ┌────┐
 │  (◉ Explore)   Bookings    Inbox •3    Earn      You      │  │ ⌕  │   ← only when shrunk
 └──────────────────────────────────────────────────────────┘  └────┘
   height 64, radius capsule, bottom = max(8, safe-area-bottom − 12)
```
- Five destinations (no change). Each item is 56 wide, with a 24 px icon over a 12/16 label.
- The active item sits on the **droplet**: a 64 × 52 capsule of `--glass-tint-strong` plus a lit rim, sliding on `--spring-snappy`. The icon is filled and in `--ink`, with no crimson (Apple: monochrome symbols).
- Badges keep the UX-46 rules.
- Inset 16 from the sides and floating above the home indicator. Scroll views keep `padding-bottom: var(--dock-h) + 16` (the rule stands; `--dock-h` becomes 64 + bottom offset + safe area).
- **Shrunk state** (scrolling down): the capsule collapses to 64 × 52 around the active icon, bottom left, and a 52 px round glass search button appears bottom right. The dock expands on scroll up, on a tap, or at the top. *(2026-09-27, owner: dropped. The dock never collapses or hides on scroll; always the full five tabs with labels, content scrolls under the glass and ends 16 px above it.)*
- At 200 % text it goes icons only, as now.

**Top bar over a photo (the listing):**
```
 ┌───────────────────────────────────────────┐
 │ (‹)                          (⇪)  (♡)     │  44 × 44 clear-glass circles,
 │                                           │  16 from the edges, below the safe area
 │        full-bleed photo 4:3 (or 1:1)      │
 │                     ┌───────────────┐     │
 │                     │ Free 14–18 h  │     │  the hour tag, bottom-left,
 │                     └───────────────┘ 1/6 │  the counter bottom-right
 └───────────────────────────────────────────┘
```
When scrolled past the photo, the circles merge into one regular-glass bar
with the title (a 180 ms morph).

**Sheet chrome:**
```
 ┌───────────── inset 8 from the sides at medium detent ─────────────┐
 │                          ───  (grabber 36×4)                       │  glass (regular), 56 tall
 │  Saturday, 14:00–18:00                                   (✕)      │
 ├────────────────────────────────────────────────────────────────────┤  scroll-edge fade, no rule
 │  opaque --elevated body: slots, price summary, policy, card row    │
 │                                                                    │
 ├────────────────────────────────────────────────────────────────────┤
 │  €16.00 held · Nothing charged yet        [ Request · €16.00 ]     │  glass action row
 └────────────────────────────────────────────────────────────────────┘
  medium detent: inset 8, radius 32 all corners; large detent: edge to edge, top radius 32, fully opaque
```

**Segmented control:** a glass track, 36 tall, capsule, with a 2 px inner
padding. The selected segment is a droplet of `--glass-tint-strong` with a rim,
sliding on `--spring-snappy`. The label is in `--ink` semibold; the others are in `--ink-2`.

**The hour tag:** a capsule 28 tall, 10 px horizontal padding, `text-label`
semibold tabular.
- On photos: clear glass (`--glass-tint-media-text`), white ink.
- On paper: `--sky-subtle` with `--sky-ink` (not glass: plane 1).
- On the plate: plate glass with ice ink.

**Primary button:**
- On paper: a solid capsule in `--accent`, 48 tall (52 in sticky bars).
- Over media or inside a glass action row: **tinted glass**, meaning an accent fill at 88 % over `--glass-frost-thin`, with the rim.

### 3.3 CSS recipe (tokens)

These amend the existing glass tokens in `theme.css` rather than add a parallel
set. Values that change are marked (was …).

```css
:root {
  /* Frost: small controls / bars / large panes. Lower than today for mid-range Android. */
  --glass-frost-thin: 12px;   /* was 14 */
  --glass-frost: 20px;        /* was 24 */
  --glass-frost-strong: 28px; /* was 34 */
  --glass-sat: 180%;
  --glass-bright: 1.04;       /* new: lifts the backdrop a touch in light */

  /* Fills. The minimum alpha keeps ink ≥ 7.9:1 even over a black backdrop (§3.4). */
  --glass-tint: rgba(251, 250, 247, 0.72);        /* was rgba(255,255,255,.5) */
  --glass-tint-thin: rgba(251, 250, 247, 0.62);   /* icon-only controls; was .38 */
  --glass-tint-strong: rgba(251, 250, 247, 0.84); /* droplets, text-heavy panes; was .66 */
  /* Clear glass over photos (both themes): a built-in dimming layer. */
  --glass-tint-media: rgba(16, 20, 17, 0.5);      /* new: icon-only (white icon ≥ 3:1 over white) */
  --glass-tint-media-text: rgba(16, 20, 17, 0.6); /* new: text on photos (white ≥ 4.5:1 over white) */
  /* Glass on the plate. */
  --glass-tint-dark: rgba(244, 243, 238, 0.1);    /* was rgba(32,49,30,.42): light on the plate, not darker */

  /* Rim: lit top-left, shaded bottom-right, 1px, painted by .glass::before (exists). */
  --glass-edge-lit: rgba(255, 255, 255, 0.9);
  --glass-edge-shade: rgba(24, 33, 26, 0.1);
  --glass-specular: rgba(255, 255, 255, 0.6);     /* the inner top highlight line */
  --glass-glow: rgba(255, 255, 255, 0.45);        /* new: press illumination */

  --glass-shadow: 0 8px 24px -6px rgba(24, 33, 26, 0.16), 0 1px 3px rgba(24, 33, 26, 0.1);
  --glass-shadow-raised: 0 18px 44px -12px rgba(24, 33, 26, 0.3), 0 2px 6px rgba(24, 33, 26, 0.12);
  /* Adaptive shadow (Apple): heavier when content is under the glass. */
  --glass-shadow-over: 0 10px 30px -6px rgba(24, 33, 26, 0.26), 0 1px 3px rgba(24, 33, 26, 0.14);
}
:root[data-theme='dark'] {
  --glass-sat: 140%;
  --glass-bright: 0.92;
  --glass-tint: rgba(31, 40, 33, 0.72);
  --glass-tint-thin: rgba(31, 40, 33, 0.62);
  --glass-tint-strong: rgba(47, 56, 48, 0.86);
  --glass-edge-lit: rgba(238, 240, 234, 0.22);
  --glass-edge-shade: rgba(0, 0, 0, 0.35);
  --glass-specular: rgba(255, 255, 255, 0.12);
  --glass-glow: rgba(255, 255, 255, 0.14);
  --glass-shadow: 0 10px 30px -8px rgba(0, 0, 0, 0.55), 0 0 0 0.5px rgba(238, 240, 234, 0.08);
  --glass-shadow-raised: 0 20px 48px -12px rgba(0, 0, 0, 0.7), 0 0 0 0.5px rgba(238, 240, 234, 0.1);
  --glass-shadow-over: 0 12px 34px -6px rgba(0, 0, 0, 0.7), 0 0 0 0.5px rgba(238, 240, 234, 0.1);
}
```

The pane. This is today's `.glass`, amended; the `::before` rim already exists.
```css
.glass {
  background: var(--glass-tint);
  -webkit-backdrop-filter: blur(var(--glass-frost)) saturate(var(--glass-sat)) brightness(var(--glass-bright));
  backdrop-filter: blur(var(--glass-frost)) saturate(var(--glass-sat)) brightness(var(--glass-bright));
  box-shadow: inset 0 1px 0 var(--glass-specular), var(--glass-shadow);
}
/* The rim: a 1px gradient border lit from 135°, via a masked ::before (exists). */
.glass::before {
  content: ''; position: absolute; inset: 0; border-radius: inherit; padding: 1px; pointer-events: none;
  background: linear-gradient(135deg, var(--glass-edge-lit), transparent 40%, transparent 60%, var(--glass-edge-shade));
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor; mask-composite: exclude;
}
/* Press illumination, from the touch point (--px/--py set on pointerdown). */
.glass[data-pressed]::after {
  content: ''; position: absolute; inset: 0; border-radius: inherit; pointer-events: none;
  background: radial-gradient(circle at var(--px, 50%) var(--py, 50%), var(--glass-glow), transparent 70%);
}
/* Adaptive shadow: the bar knows content is under it (the scroll state exists). */
.glass[data-over='content'] { box-shadow: inset 0 1px 0 var(--glass-specular), var(--glass-shadow-over); }
/* Clear variant over media. */
.glass-media { background: var(--glass-tint-media); --glass-sat: 150%; --glass-bright: 1; }
```

The **edge lensing**: a cheap stand-in for refraction, on the dock, droplets
and round buttons only (small areas). It is a second backdrop layer masked to a
6 px ring, so the edge is sharper, brighter and more saturated than the centre.
That is the visual cue of glass thickness.
```css
.glass-lens::after {
  content: ''; position: absolute; inset: 0; border-radius: inherit; pointer-events: none;
  -webkit-backdrop-filter: blur(2px) saturate(200%) brightness(1.12);
  backdrop-filter: blur(2px) saturate(200%) brightness(1.12);
  -webkit-mask: radial-gradient(closest-side, transparent calc(100% - 6px), #000);
  mask: radial-gradient(closest-side, transparent calc(100% - 6px), #000);
}
```

**True refraction** (`feDisplacementMap`) works in Chromium only and in no
WebKit engine, so none of the iOS shell, Safari or iOS Chrome get it. It is a
**P2 progressive enhancement on desktop Chromium only**, for the droplet, behind
`CSS.supports('backdrop-filter', 'url(#lg)')` and `data-glass='full'`
(VD-30). It is never required for the look.

**Fallbacks:**
```css
/* No backdrop-filter at all: solid, readable, same shape. */
@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
  .glass, .glass-media { background: var(--elevated); }
  .glass-media { background: rgba(16, 20, 17, 0.72); }
}
/* Reduce Transparency (Chromium; the iOS/Android shells set data-transparency='reduce'). */
@media (prefers-reduced-transparency: reduce) { :root { --glass-on: 0; } }
:root[data-transparency='reduce'] { --glass-on: 0; }
/* Increase Contrast: predominantly solid with a contrasting border (Apple). */
@media (prefers-contrast: more) { :root { --glass-contrast: 1; } }
/* Low-power: blur off, fills near-opaque, no lens layer. */
:root[data-glass='lite'] {
  --glass-frost-thin: 0px; --glass-frost: 0px; --glass-frost-strong: 0px;
  --glass-tint: rgba(251, 250, 247, 0.96); --glass-tint-strong: rgba(251, 250, 247, 0.98);
}
```
Under `--glass-on: 0` or `--glass-contrast: 1`:
- `.glass` takes `background: var(--elevated)` and `backdrop-filter: none`;
- the rim becomes a solid `1.5px var(--line-strong)`;
- the specular and glow are off.

This is written once in `theme.css`; components never branch.

**When `data-glass='lite'` is set** (by `theme.ts`, before the first paint, from the cheapest signals first):
1. `navigator.connection.saveData`;
2. `navigator.deviceMemory <= 4` or `navigator.hardwareConcurrency <= 4` on Android;
3. a frame probe: during the first real scroll, if more than 20 % of frames take more than 20 ms, switch to lite for the session and remember it per device;
4. battery saver, where exposed (the Android shell via a tiny bridge).

The user can override this in You → Preferences → "Glass effects: Full · Reduced".

### 3.4 Contrast on glass (measured)

The worst case for glass is a uniform backdrop of pure black or pure white.
Blur averages the backdrop, so a real one sits between the two. The ratios below
come from compositing each fill over black, white and 50 % grey (script in the
session scratchpad; the pairs go into `check:contrast` in VD-4).

| Fill | Text | Over black | Over white | Over grey | Verdict |
|---|---|---|---|---|---|
| light `--glass-tint` α .72 | `ink` #18211a | 7.95 | 15.9 | 11.6 | body text allowed |
| light α .72 | `ink-3` #5a6157 | 3.08 | 6.18 | 4.48 | **not allowed on glass** (use ink or ink-2) |
| light α .62 (today's pattern at .5 is worse) | `ink` | 5.93 | 16.1 | 10.3 | icon-only controls and ≥ 17 px labels |
| dark `--glass-tint` α .72 | `ink` #eef0ea | 15.2 | 5.36 | 9.39 | allowed |
| dark α .72 | `ink-3` #a8b0a4 | 7.82 | 2.76 | 4.83 | **not allowed on glass** |
| `--glass-tint-media` α .5 | white icon | — | 3.95 | — | icons only (≥ 3:1) |
| `--glass-tint-media-text` α .6 | white text | — | 5.7 | — | the hour tag, the counter |
| Apple's 35 % dim + clear | white text | — | 2.12 | — | **why Cappy does not copy it literally** |

Rules that follow:
- On glass, text is `--ink` or `--ink-2` only, at ≥ 13 px semibold or ≥ 15 px regular.
- **Adaptive ink** for small glass over media: each photo has a stored colour. When its relative luminance is > 0.5, the controls over it use light glass and ink; otherwise they use media glass and white. This is Apple's "flip light/dark", decided per photo at render time and not per frame.
- Bars over scrolling text get the scroll edge effect: a 24 px `mask-image` fade on the scroll container's top and bottom edges under the bar. The glass never has text scrolling sharply behind its own text.

### 3.5 Performance budget

| Budget | Limit |
|---|---|
| Glass surfaces visible at once | ≤ 3 (group into one capsule beyond that) |
| Total glass area | ≤ 20 % of the viewport on phones, ≤ 10 % on desktop |
| Blur radius | ≤ 20 px on phones (sheet chrome 28 only while static); cost grows with radius × area |
| Lens layer (second backdrop) | dock, droplets and round buttons only; never on bars |
| Animating glass | only `transform` and `opacity` on the glass element; never animate `backdrop-filter`, `width`, `height` or the radius per frame. The droplet moves by `transform`; the dock no longer shrinks (2026-09-27). |
| Backdrop roots | no `opacity`, `filter`, `mask` or `will-change: opacity` on ancestors of glass (it cuts the blur off; see MDN) |
| Frame time | 60 fps scroll on a 2021 mid-range Android (Moto G-class, 4 GB) in `full`; otherwise `lite` switches on. Measured on a device in VD-31. |
| INP | ≤ 200 ms p75 unchanged; press feedback ≤ 100 ms |
| 3D category objects | 9 × ≤ 12 KB AVIF/WebP at 2×, lazy below the fold, `width`/`height` set |
| Fonts | no new families. Archivo's width axis is already in the shipped file. |

---

## 4. Screen-by-screen redesign

Token names refer to §3.3 and §5. Phone wireframes are for 390 px; desktop
notes follow each one. The copy is proposed in plain words and needs the usual
DE and FR passes.

### 4.1 Welcome (signed out)

```
┌──────────────────────────────┐  --plate (lit radial, grain), full screen
│ Cappy                 [EN ▾] │  wordmark Bodoni 28; language in plate glass
│                              │
│   ┌──────┐ ┌──────┐          │  3D objects float in a slow parallax
│   │ saw  │ │ van  │  ┌─────┐ │  on device tilt (DeviceOrientation, off
│   └──────┘ └──────┘  │print│ │  under Reduce Motion), about 88 px each
│           ┌──────┐   └─────┘ │
│           │studio│           │
│                              │
│ Capacity,                    │  Bodoni display 56/52, on-field
│ shared by the hour.          │
│ Rent the machines, rooms and │  body-l, on-field-dim, 36ch
│ vehicles near you.           │
│ ┌──────────────────────────┐ │
│ │      Create account      │ │  solid accent capsule 52
│ └──────────────────────────┘ │
│        I have an account     │  text button, on-field
└──────────────────────────────┘
```
- The four example chips become the objects, each with its hour tag in plate glass ("€4 / h").
- Desktop: two columns, the objects cluster on the right at 1.5× size, and the type is on the left at `display`.

### 4.2 Explore

```
┌──────────────────────────────┐
│ ░░░ lit plate band ░░░░░░░░░ │  --plate, 0 → 220 px; in dark the band fades into --ambient-night
│ Neukölln, Berlin ▾      (🔔) │  location in plate glass capsule; bell in plate glass
│ Free near you                │  Bodoni 40, on-field (no accented word)
│ ┌──────────────────────────┐ │
│ │ ⌕  What do you need?  │ When │  glass search capsule 56, --glass-tint-strong, radius capsule
│ └──────────────────────────┘ │  tapping expands into the What · When · Where step sheet (UX-15)
├──────────────────────────────┤  paper from here
│  [obj]  [obj]  [obj]  [obj] ›│  3D category objects 56 + label 13/16, horizontal scroll
│  Fabr.  3D pr. Finish Freight│  the selected one: bouncy spring + ink underline 2px
│                              │
│ Free this afternoon      See all │  title-s Archivo 700 wdth 112
│ ┌───────────┐ ┌───────────┐  │  rail cards 4:5, 240 wide, radius 20
│ │  photo    │ │  photo    │  │
│ │  (♡)      │ │  (♡)      │  │  heart: media glass 36
│ │ [14–18 h] │ │ [now–20h] │  │  hour tag: media glass text
│ └───────────┘ └───────────┘  │
│ Bambu H2D      €7.80 / h      │  title body-l 600; price figure 600, ink
│ ★ 4.8 · 1.2 km                │  label, ink-3
│                              │
│ Near you this week    See all │  second rail, then a 2-column grid on scroll
│ …                            │
└──────────────────────────────┘
      (  floating glass dock  )
```
- Sections are separated by 32 px of space, **not** the black rule.
- The grey "Free in the next 24 hours" hero with a half-empty right column is gone. The first photo the user sees is a rail card at 240 px, so a single bad photo no longer owns the screen.
- The count "28" becomes "See all 28".
- Desktop (1440): the plate band spans 1200 px as a 24-radius plate with a 1 px lit top. The glass search capsule is 720 wide and centred in the band, with What · When · Where segments, as Airbnb's desktop bar. The 3D objects sit in one row of 9 below it. Rails become a 4-column grid with the hour tag on each photo. The top bar is transparent over the plate at rest and becomes glass (`--glass-tint`) with `data-over='content'` once scrolled.

### 4.3 Results (text search or category)

```
┌──────────────────────────────┐
│ (‹) [ ⌕ saw · Sat · 14:00 ]  │  glass top bar, the query as a capsule (tap to edit)
│ [Instant] [≤ 2 km] [€ ≤ 10]  │  applied chips on paper (plane 1), removable ✕
│ 12 free on Saturday          │  label ink-2
│ ┌──────────────────────────┐ │  one layout for every result list (UX consistency):
│ │ photo 16:10, radius 20   │ │  full-width card, hour tag bottom-left, heart top-right
│ │ [Sat 14–18 h]      (♡)   │ │
│ └──────────────────────────┘ │
│ Festool TS 55 plunge saw     │
│ €4.00 / h · ★ 4.9 · 800 m    │
│  …                           │
│            (◧ Map)           │  floating glass capsule, centred above the dock
└──────────────────────────────┘
```
- The map (UX-67) is the ground, with results in a sheet over it. The map controls are one glass capsule (zoom, locate). The selected price pin is tinted glass with the accent; the others are paper pins in `--ink`.
- Desktop: list and map side by side at 55/45, and the list cards in 2 columns.

### 4.4 Listing

```
┌──────────────────────────────┐
│(‹)                  (⇪) (♡)  │  media glass circles 44 over the photo
│                              │
│     full-bleed photo 4:3     │  swipe gallery, 1/6 counter in media glass text
│ [Free today 14–18 h]    1/6  │  the hour tag (the shared element from the card)
├──────────────────────────────┤  --ambient wash starts here (photo colour 22 % into page)
│ Bambu H2D, two colour        │  title-l Archivo 700 wdth 112 (user text, never Bodoni)
│ Neukölln · ★ 4.8 (4)         │  label ink-2
│                              │
│ €7.80                        │  display figure: Archivo wdth 125 / 800 / 56, cents 60 %
│ per hour · 2 h minimum       │  label ink-3
│                              │
│ ┌ Amira Haddad ─────────── ┐ │  host card: plane 1, surface, radius 20, avatar 48
│ │ Replies in ~18 min · 13 … │ │
│ └──────────────────────────┘ │
│ Free this week               │  the capacity strip: day columns, ice = free, ink = taken
│ ▮▮▯▮▮▯▯                      │  (tap a day → opens the booking sheet on that day)
│ About · Rules · Where        │  sections with 32 gaps, no rules
│ Reviews ★ 4.8 (5–1 bars)     │
└──────────────────────────────┘
 ┌──────────────────────────────┐
 │ Sat 14:00–18:00   [Request]  │  sticky: glass capsule 64, inset 12, radius capsule;
 │ €31.20 total                 │  left: hour + total (ink, figure); right: tinted-glass primary
 └──────────────────────────────┘
```
- The top bar merges into one regular glass bar with the title once the photo scrolls away (§2.7).
- Desktop: a 7/5 grid. The left column has the mosaic (UX-56) and the content. The right column has the booking card, sticky, plane 1 opaque with the hour picker inline. The ambient wash runs behind the whole top 480 px.

### 4.5 Booking sheet and confirmation

```
┌─ inset 8, radius 32, medium detent ─┐
│             ───                      │  glass header
│ Saturday 27 Sep               (✕)    │  title-s 700
├──────────────────────────────────────┤
│ Sa Su Mo Tu We Th Fr  ›              │  day strip: 44×56 cells, selected = ink droplet (snappy)
│ [14:00] [15:00] [16:00] [17:00]      │  start chips radius-s; taken ones struck, ink-4
│ For  − 4 h +                          │  stepper, figure
│ ──────────────                        │
│ €7.80 × 4 h            €31.20         │  PriceSummary (UX-23), tabular right-aligned
│ Service fee             €4.68         │
│ Total                  €35.88         │  body-l 700
│ 🔒 Nothing is charged until Amira accepts │  neutral box, sunken, lock icon (UX-50)
│ Visa ·· 4242                    ›     │  payment row
├──────────────────────────────────────┤
│ [ Sat 14–18 h ]   [ Request · €35.88 ]│  glass action row: hour tag + tinted-glass primary
└──────────────────────────────────────┘
```
- Then the ticket (§2.8):
```
┌──────────────────────────────┐  scrim deepens to --plate
│                              │
│  ┌────────────────────────┐  │  the ticket: --plate, radius 24, lit rim, grain
│  │ (●) Bambu H2D          │  │  photo 40 round
│  │ Saturday               │  │  Bodoni 44, on-field
│  │ 14:00–18:00            │  │  display figure 48, ice
│  │ Neukölln · with Amira  │  │  label on-field-dim
│  │- - - - - - - - - - - - │  │  perforation (a dashed SVG line with notches at each end)
│  │ Waiting for Amira      │  │  stub: ice on plate glass; instant = "Paid €35.88" money
│  └────────────────────────┘  │
│ Requested. Amira usually     │  body-l, ink, centred under the ticket
│ replies in about 18 minutes. │
│ (Message Amira) (Add to cal) │  glass buttons (regular) over the plate
│           Done               │
└──────────────────────────────┘
```

### 4.6 Booking detail

```
┌──────────────────────────────┐
│(‹)  Booking             (⋯)  │  glass bar (appears over content on scroll)
│ ┌──────────────────────────┐ │  the ticket again, compact (plate, 120 tall):
│ │ Sat 14:00–18:00  [Waiting]│ │  the booking always looks like the thing you were given
│ │ Bambu H2D · Amira         │ │
│ └──────────────────────────┘ │
│ ●───●───○───○                │  status timeline: requested · accepted · collected · returned
│ 23:41 left for Amira         │  countdown figure (UX-51)
│ Messages                     │  last 2 messages inline, then "Open chat"
│ Where · How to collect       │  map tile (static) with a glass locate chip
│ Price · Policy · Receipt     │
└──────────────────────────────┘
 ┌──────────────────────────────┐
 │        [ Message Amira ]      │  sticky glass capsule, one primary by the clock (UX-25)
 └──────────────────────────────┘
```

### 4.7 Inbox and thread

```
Inbox                                   Thread
┌──────────────────────────────┐        ┌──────────────────────────────┐
│ Inbox                        │        │(‹) (●) Amira        (⋯)      │ glass bar, avatar 32
│ ( All | Unread )             │ glass  │ ┌ Sat 14–18 · Bambu H2D ──┐  │ pinned booking: plate chip
│                              │ segm.  │ └ Waiting · 23:41 left ───┘  │ (plane 1 plate, not glass)
│ (●) Amira Haddad      14:02  │ 72 row │   You requested Sat 14:00–18:00 │ system line, centred, label ink-3
│ [thumb] Bambu H2D · Sat 14–18│        │ ┌───────────────────┐        │
│ Sure, the bed is levelled… • │        │ │ Hi! Is the bed    │        │ theirs: surface bubble
│ ──────────────────────────── │ inset  │ └───────────────────┘        │
│ (●) Nadia Brandt   Yesterday │        │        ┌─────────────────┐   │ yours: ink bubble, on-inverse
│ …                            │        │        │ Yes, levelled.  │   │ (not crimson: accent is for actions)
└──────────────────────────────┘        │ ┌────────────────────────┐   │
                                        │ │ Message…          (↑)  │   │ composer: glass capsule 48 over
                                        │ └────────────────────────┘   │ the keyboard; send = tinted glass
                                        └──────────────────────────────┘
```
- Rows: a 48 avatar with a 24 listing-photo thumbnail overlapping at the bottom right (who plus what). The name is body-l 600; the time is a label figure. The unread dot is 10 px `--accent` with text "Unread" for screen readers.
- Money in the thread (held, paid, refunded) is a system card with a large figure, as in Revolut's chat. It is plane 1 and not glass.
- Desktop: two panes, the list at 360 and the thread filling the rest, with the booking card as a right rail at ≥ 1200.

### 4.8 Earn

```
┌──────────────────────────────┐
│ ░░ lit plate, 0 → 300 px ░░░ │
│ Earn               (+ New)   │  title Archivo wdth 112 on-field; "+ New" plate-glass capsule
│ This week                    │  label on-field-dim
│ €28.05                       │  display figure 64 wdth 125, on-field; cents 60 %
│ earned · €12.75 on the way   │  label: money (ice-green) · on-field-dim
│ ┌──────────────────────────┐ │  the week chart: content, so an opaque --field-2 card,
│ │ Sa Su Mo Tu We Th Fr     │ │  radius 20, not glass
│ │ ▮▮ ▮▮ ▮▯ ▯▯ ▯▯ ▯▯ ▯▯      │ │  bars: ice = free, on-field = sold, crimson-bright = requested
│ └──────────────────────────┘ │
├──────────────────────────────┤  paper
│ 136 free hours this week     │  title-s; an invitation, not guilt
│ [ Open more hours ]          │  secondary outline capsule
│ Requests (0)                 │  empty: 3D object "bell" 96 + "No one is waiting on you"
│ Coming up                    │  ticket-style rows (compact plate chips)
│ Your listings                │  2-col cards with a status pill (Live, Paused, In review)
└──────────────────────────────┘
```
- The week chart is **content**, so it sits on the plate as an opaque card, never glass (§3.1).
- Desktop: the plate hero spans 1200 wide, with the figure on the left and the week chart on the right, then a 3-column grid of requests, coming up and listings.

### 4.9 Add listing

- **A stepped wizard (UX-19, UX-70)** with a glass progress capsule at the top: "Photos · Basics · Hours · Price · Review", where the current step is a droplet.
- **Photos first**, as in Vinted: a 3-up grid of 1:1 tiles, radius 16, and a dashed "Add photos" tile with the camera 3D object. The three-shot recipe sits under it.
- Each step's body is opaque paper with 48-tall fields at radius 12. The sticky action row is glass: "Back" (text) and "Next" (solid accent capsule).
- **Review** shows the listing exactly as renters will see its card and header (the real `ListingCard`), with the hour tag computed from the hours just entered.
- **Publish** runs a small version of the ticket moment: the card lifts onto the plate, "Live" in money green, and one success haptic.

### 4.10 You

```
┌──────────────────────────────┐
│ ░ ambient-night / plate band ░│  a 160 px plate band, like Explore, but shorter
│ (DH) Demo Host Two     (☾)   │  avatar 64 with a lit rim; theme switch in plate glass
│ Neukölln · member since 2026 │
│ ┌──────┐┌──────┐┌──────┐     │  three stat tiles, opaque field-2, figures 22 wdth 125
│ │ 3    ││€28.05││ €8.00│     │
│ │Listed││Earned││ Spent│     │
│ └──────┘└──────┘└──────┘     │
├──────────────────────────────┤
│ Preferences                  │  grouped list (iOS inset grouped), radius 20, rows 56
│  Appearance   ( Light | Dark | Auto )  glass segmented
│  Glass effects   Full ›      │  new
│  Haptics          [on]       │  new
│  Language       English ›    │
│ Saved · Payouts · Help · Legal │
└──────────────────────────────┘
```

---

## 5. Token changes

New or changed tokens, light then dark, to add to `theme.css` (both theme
blocks). `check:contrast` gains every new text pair, and the glass-worst-case
rows in §3.4.

| Token | Light | Dark | Note |
|---|---|---|---|
| `--accent` | #b0182e (was #8b0d1a) | #f2606d (was #e0525f) | white on light 6.96:1; dark ink on dark 6.24:1 |
| `--accent-hover` | #9c1428 | #f47a85 | |
| `--accent-active` | #86101f | #d9505c | |
| `--accent-text` | #b0182e | #f47a85 | on page 6.67:1 light (measure dark in `check:contrast`) |
| `--badge` | = accent | = accent | |
| `--accent-glow` | none | 0 0 24px -8px rgba(242, 96, 109, 0.4) | the primary only, dark only |
| `--plate` | `radial-gradient(120% 90% at 15% 0%, #2f4a2b 0%, var(--field) 55%, #182716 100%)` | `radial-gradient(120% 90% at 15% 0%, #2c4e33 0%, var(--field) 55%, #142418 100%)` | the lit plate; a 2 % grain via a 128 px tiled noise PNG at 4 % opacity |
| `--plate-rim` | inset 0 1px 0 rgba(255, 255, 255, 0.14) | inset 0 1px 0 rgba(255, 255, 255, 0.1) | |
| `--ambient` | set inline from `photoMeta.color` | same | |
| `--ambient-wash` | `linear-gradient(to bottom, color-mix(in oklab, var(--ambient) 22%, var(--page)), var(--page) 320px)` | `… 30% …` | listing and booking sheet |
| `--ambient-night` | none | `radial-gradient(90% 60% at 50% -10%, color-mix(in oklab, var(--field) 60%, transparent), transparent)` | top of Explore, Earn and You in dark |
| glass tokens | see §3.3 | see §3.3 | amended values plus `--glass-bright`, `--glass-glow`, `--glass-tint-media(-text)`, `--glass-shadow-over` |
| `--radius-card` | 20 (was 14) | | concentric: an image inset by 8 in a card = 12 |
| `--radius-plate` | 24 (was 14) | | |
| `--radius-sheet` | 32 (was 22) | | iOS 26 sheets |
| `--radius-field` | 12 (was 8) | | |
| `--radius-control` | 999px (capsule; was 8) | | primary and secondary buttons |
| `--radius-s` | 8 | | choice chips in forms (unchanged) |
| `--dock-bar-h` | 64 (was 56) | | the floating capsule |
| `--dock-inset` | 16 | | new: side and bottom offset |
| `--dock-droplet-w` / `-h` | 64 / 52 | | replaces the pill 56 × 32 |
| `--dock-h` | `calc(var(--dock-bar-h) + max(8px, env(safe-area-inset-bottom) - 12px) + env(safe-area-inset-bottom))` | | what scroll views keep clear of (the formula lives in one place) |
| `--text-large-title` | 2.125rem / 2.5rem, Archivo 700, `font-stretch: 112%` | | screen titles |
| `--text-figure-hero` | 3.5rem / 3.5rem (4rem on Earn), Archivo 800, `font-stretch: 125%`, tabular | | one per screen |
| `--spring-snappy` | `linear(0, 0.102, 0.305, 0.515, 0.691, 0.821, 0.908, 0.962, 0.991, 1.005, 1.011, 1.011, 1.009, 1.007, 1.004, 1.003, 1)` over `--dur-snappy` 320ms | | droplets, chips, menus |
| `--spring-bouncy` | `linear(0, 0.091, 0.297, 0.538, 0.76, 0.933, 1.047, 1.108, 1.126, 1.116, 1.091, 1.06, 1.032, 1.01, 0.995, 0.987, 0.984, 0.985, 0.988, 0.992, 0.996, 0.999, 1.001, 1.002, 1)` over `--dur-bouncy` 700ms | | the ticket, the objects, the heart |

The two `linear()` curves are sampled from a damped spring:
- snappy: ζ 0.82, ω 26 rad/s;
- bouncy: ζ 0.55, ω 16 rad/s.

The dark surface ladder, `ink` levels, `money`, `focus`, `danger`, `sky` and
`field` are **unchanged**.

### 5.1 Rulebook amendments (`.claude/skills/cappy-ui/SKILL.md`)

Proposed exact text. VD-2 applies these; the rulebook is not edited here.

1. **§2 Type.** Replace the Bodoni bullet with:
   > Bodoni is for moments only: Welcome, the Explore greeting, the booking ticket, the Earn hero word and empty states, at 34 px and up (44 in dark). Screen titles are `text-large-title`: Archivo 700 at width 112, 34/40, left-aligned. One hero figure per screen may use `text-figure-hero` (Archivo 800, width 125, tabular, cents at 60 %).
2. **§3 Colour.** Add:
   > The accent is #b0182e (light) / #f2606d (dark). In dark the one primary may carry `--accent-glow`. Symbols on glass are monochrome `ink`; only the primary action is tinted, and it is tinted on its background, never on its label.
3. **§3 Dark mode.** Replace "Glass only on the dock; sheets are opaque." with:
   > Glass is chrome only (§4 Materials). Sheet bodies are opaque in both themes; their header and action row are glass. The top of Explore, Earn and You carries `--ambient-night`.
4. **New §4 Materials.** Insert before Tap targets:
   > **Materials.** Four planes: ground (page, media, plate), content (opaque surfaces), glass (chrome), lift (pressed glass, menus, the ticket). Content is never glass: no cards, rows, text areas, message bubbles or sheet bodies on glass. At most three glass surfaces are visible at once; group more into one capsule. Glass never sits on glass. Text on glass is `ink` or `ink-2` only, ≥ 13 px semibold or ≥ 15 px regular. Over photos use `glass-media` (icons) or `glass-media-text` (text). Every glass rule has one fallback in `theme.css`: no `backdrop-filter`, Reduce Transparency, Increase Contrast, and `data-glass='lite'`. Components never branch on them.
5. **§4 Dock.** Replace the bullets from "height 56" to "background" with:
   > A floating glass capsule, 64 tall, inset 16 from the sides and `max(8, safe-bottom − 12)` from the bottom. The active item sits on a 64×52 droplet of `glass-tint-strong` that slides on `spring-snappy`; the icon is filled and in `ink`. It never collapses or hides on scroll (owner, 2026-09-27). Under Reduce Transparency it is opaque `elevated` with a `line-strong` edge.
6. **§4 Buttons.** Replace the radius sentence with:
   > Primary and secondary buttons are capsules. Over media or inside a glass action row the primary is tinted glass (accent at 88 % over `glass-frost-thin` with the rim); on paper it is solid.
7. **§4 Sheets.** Replace it with:
   > At the medium detent a sheet is inset 8 from the sides with radius `radius-sheet` (32) on all corners. At the large detent it is edge to edge and fully opaque. Its grabber row, header and action row are glass; its body is opaque `elevated`. There are no dividers: a 24 px scroll-edge fade under the header.
8. **§5 Motion.** Add:
   > Springs: `spring-spatial` (sheets, routes), `spring-snappy` (droplets, chips, menus), `spring-bouncy` (the ticket, the category objects, the heart). Glass is pressed by scale .96 plus `glass-glow` at the touch point. Glass materialises (scale .6 → 1 from its origin, a blur that clears), never a bare fade. The one choreographed moment is the booking ticket (and its small version on publish). Scroll-linked effects use `animation-timeline: scroll()`, with a class-toggle fallback.
9. **§6 Imagery and icons.** Add:
   > Category objects are the nine 3D renders in `web/public/objects/`, 135° key light, the brand palette only, used in the category row, on the no-photo plate and in empty states. With no photo a listing shows its category object on the lit plate, never a grey box. Placeholders are the photo's stored colour or its blurred thumbnail.
10. **§7 Checklist.** Add:
    > Glass: count the glass surfaces (≤ 3); check text on glass over the brightest and darkest photo in the seed; toggle `data-glass='lite'`, `data-transparency='reduce'` and `prefers-contrast: more`; record a 10 s scroll on a mid-range Android (VD-31) in `full`.

**ADR.** Floating glass chrome over a photographic content layer changes the
decisions behind UX-46 and UX-60 (the opaque bar, opaque sheets). CLAUDE.md
asks for a new ADR for that, not a silent edit: **ADR 0014 "Visual system:
glass chrome, photographic content"** (VD-1).

---

## 6. Build checklist (prioritised)

**P0** is the look the owner asked for and the base everything else stands on.
**P1** is the moments. **P2** is polish and progressive enhancement. The order
within a band is the build order.

**P0**
- [ ] VD-1 [design] ADR 0014 "Visual system: glass chrome, photographic content": the four planes, where glass goes, the fallbacks, the budget; it supersedes UX-46's opaque bar and UX-60's opaque sheets — docs/research/2026-10-visual-direction.md §2.6, §3.1
- [ ] VD-2 [design] Amend `.claude/skills/cappy-ui/SKILL.md` with §5.1's ten texts — docs/research/2026-10-visual-direction.md §5.1
- [ ] VD-3 [web] Category-true seed and demo photos first (UX-53), each with a stored colour and a blurred thumbnail; no grey `--sunken` placeholders anywhere — docs/research/2026-10-visual-direction.md §2.4 · https://news-assets.withairbnb.com/wp-content/uploads/sites/21/2025/05/Services-flow-PDP-US.jpg
- [ ] VD-4 [web] Glass tokens and recipe of §3.3 in `theme.css`: amended fills, frost, rim, specular, glow, media variants, adaptive shadow, the lens layer; the fallbacks (no backdrop-filter, `prefers-reduced-transparency`, `data-transparency`, `prefers-contrast: more`, `data-glass='lite'`) written once; the §3.4 worst-case pairs in `check:contrast` — https://developer.apple.com/videos/play/wwdc2025/219/ · https://www.joshwcomeau.com/css/backdrop-filter/
- [ ] VD-5 [web] Low-power detection in `theme.ts` before the first paint (Save-Data, deviceMemory/hardwareConcurrency, a first-scroll frame probe remembered per device), plus You → Preferences "Glass effects: Full · Reduced" — docs/research/2026-10-visual-direction.md §3.3, §3.5
- [ ] VD-6 [web]+[app] The floating glass dock: a 64 capsule inset 16, a 64×52 droplet on `--spring-snappy`, filled active icons in ink, no shrink or hide on scroll (owner, 2026-09-27), badges and 200 % rules kept, `--dock-h` from one formula — https://developer.apple.com/tutorials/data/design/human-interface-guidelines/tab-bars.json · https://www.apple.com/newsroom/images/2025/06/apple-elevates-the-iphone-experience-with-ios-26/article/Apple-WWDC25-iOS-26-hero-250609_big.jpg.large.jpg
- [ ] VD-7 [web] Type and colour: `--text-large-title` (Archivo 700, width 112) for screen titles; Bodoni kept for moments ≥ 34 (≥ 44 dark); `--text-figure-hero` for one figure per screen; the accent to #b0182e / #f2606d with hover and active; `check:contrast` updated — docs/research/2026-10-visual-direction.md §2.2, §5 · https://is1-ssl.mzstatic.com/image/thumb/PurpleSource221/v4/7b/10/8e/7b108e10-1439-6762-215f-4d2f18494702/Screen_2_1242x2208.jpg/600x1300bb.jpg
- [ ] VD-8 [web] Radii to the concentric set (control capsule, field 12, card 20, plate 24, sheet 32); section-top black rules removed in favour of 32/48 spacing — https://developer.apple.com/videos/play/wwdc2025/356/
- [ ] VD-9 [web] The listing page: a full-bleed photo under media-glass back/share/heart, the hour tag and counter on the photo, the ambient wash from the photo colour, the price as a hero figure, a glass sticky capsule with the hour and the total, and the top bar merging into regular glass on scroll (scroll-linked, with a fallback) — docs/research/2026-10-visual-direction.md §4.4 · https://is1-ssl.mzstatic.com/image/thumb/PurpleSource221/v4/01/1b/c7/011bc737-5b1c-3eba-c26a-70596e0839bc/Maps-iPhone6p9-RaveA-USEN-Wrapper2.png/600x1300bb.jpg
- [ ] VD-10 [web] Explore: the lit plate band with the Bodoni greeting and the glass search capsule, photo rails with hour tags (4:5, 240 wide), a 2-column grid below, no grey hero; desktop plate band plus a 720 search bar and a 4-column grid — docs/research/2026-10-visual-direction.md §4.2 · https://news-assets.withairbnb.com/wp-content/uploads/sites/21/2025/05/All-new-app-US.jpg
- [ ] VD-11 [web] The lit plate material (`--plate`, `--plate-rim`, the grain tile) on Welcome, Explore, Earn, You, the ticket and the no-photo listing — docs/research/2026-10-visual-direction.md §2.2, §5
- [ ] VD-12 [web] Sheets: inset 8 with radius 32 at medium, edge to edge and opaque at large; a glass header and action row, an opaque body, a scroll-edge fade instead of dividers; the booking sheet per §4.5 — https://developer.apple.com/tutorials/data/documentation/technologyoverviews/adopting-liquid-glass.json

**P1**
- [ ] VD-13 [design] Nine 3D category objects (brief in §2.5): 135° key light, the brand palette, 96/192 px AVIF/WebP ≤ 12 KB, and 24 px line fallbacks; stored in `web/public/objects/` — https://news-assets.withairbnb.com/wp-content/uploads/sites/21/2025/05/All-new-app-US.jpg · https://is1-ssl.mzstatic.com/image/thumb/PurpleSource211/v4/3e/60/43/3e604383-973c-bcc4-d838-a0264860b4ee/Screen_1_1242x2208.jpg/600x1300bb.jpg
- [ ] VD-14 [web] The category-object row on Explore (a 56 px object plus label, a bouncy selection, an ink underline), the no-photo plate with the object, and the objects in empty states — docs/research/2026-10-visual-direction.md §2.5
- [ ] VD-15 [web] The booking-confirmed ticket moment (§2.8): the hour tag lifts and becomes the plate ticket, rolling time digits, one specular sweep, glass actions in sequence, request and instant variants, the Reduce Motion version; the compact ticket at the top of Booking detail — docs/research/2026-10-visual-direction.md §2.8, §4.5, §4.6
- [ ] VD-16 [web] The hour tag as one shared element from card to listing to sheet to ticket (View Transitions, named only on the tapped card; builds on UX-59) — https://developer.chrome.com/docs/web-platform/view-transitions/same-document
- [ ] VD-17 [web] Glass motion: press scale .96 plus the glow at the touch point, `--spring-snappy`/`--spring-bouncy` tokens, menus that materialise from their button, odometer digits for changing prices and counts, the one-pass skeleton shimmer — docs/research/2026-10-visual-direction.md §2.7
- [ ] VD-18 [web] Earn as a hero: the plate with this week's earned figure (`--text-figure-hero` 64), "on the way" in money, the week chart as an opaque `field-2` card, "136 free hours this week" as an invitation with "Open more hours"; the "nobody is paying you" copy retired — docs/research/2026-10-visual-direction.md §4.8 · https://is1-ssl.mzstatic.com/image/thumb/PurpleSource221/v4/7b/10/8e/7b108e10-1439-6762-215f-4d2f18494702/Screen_2_1242x2208.jpg/600x1300bb.jpg
- [ ] VD-19 [web] Inbox and thread per §4.7: avatar plus listing thumbnail rows, glass segmented, the pinned plate booking chip, ink bubbles for "you" (not crimson), money system cards, the glass composer over the keyboard — https://is1-ssl.mzstatic.com/image/thumb/PurpleSource221/v4/ed/f0/f4/edf0f424-5f32-514c-4e6d-3df77a421617/Screen_3_1242x2208.jpg/600x1300bb.jpg
- [ ] VD-20 [app] `@capacitor/haptics` with the §2.9 map, a no-op on the web, and a Haptics switch in You (extends UX-68) — https://developer.apple.com/tutorials/data/design/human-interface-guidelines/playing-haptics.json
- [ ] VD-21 [app] The iOS and Android shells pass Reduce Transparency, Increase Contrast and battery saver to the web view as `data-transparency`, `data-contrast` and `data-glass='lite'` before the first paint (WKWebView doesn't expose `prefers-reduced-transparency`) — https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-transparency
- [ ] VD-22 [web] Dark as its own theme: `--ambient-night` on Explore, Earn and You, the smoked glass values, `--accent-glow` on the one primary, Bodoni ≥ 44 in dark; a dark screenshot pass on every screen in §4 — docs/research/2026-10-visual-direction.md §2.10 · https://www.apple.com/newsroom/images/2025/06/apple-introduces-a-delightful-and-elegant-new-software-design/article/Apple-WWDC25-Liquid-Glass-Home-Screen-dark-tint-250609_big.jpg.large.jpg
- [ ] VD-23 [web] Adaptive ink over photos: controls and the hour tag choose light glass or media glass from the photo's stored colour luminance — https://developer.apple.com/tutorials/data/design/human-interface-guidelines/color.json
- [ ] VD-24 [web] Welcome on the lit plate with the floating 3D objects (tilt parallax off under Reduce Motion), a Bodoni display and one solid capsule primary — docs/research/2026-10-visual-direction.md §4.1 · https://is1-ssl.mzstatic.com/image/thumb/PurpleSource211/v4/2e/e0/46/2ee0465a-3721-3631-14f5-d42b7b998ee3/1_-_App_store_-_USA_-_6_U002c5_inch.png/600x1300bb.jpg

**P2**
- [ ] VD-25 [web] Results and map per §4.3: one card layout for every result list, a floating glass Map/List capsule, the map controls as one glass capsule, a tinted-glass selected price pin (with UX-67) — https://is1-ssl.mzstatic.com/image/thumb/Purple211/v4/9c/b7/e7/9cb7e71e-7241-121f-3f24-ecb74cce25ce/6cf2abb7-d8c1-49e0-96f5-88dc3b1bdc20_SS01.png/600x1300bb.jpg · https://is1-ssl.mzstatic.com/image/thumb/PurpleSource221/v4/db/9e/0a/db9e0ae3-a3e5-8a6a-1616-a5f35aed16d5/Maps-iPhone6p9-RaveA-USEN-Wrapper1.png/600x1300bb.jpg
- [ ] VD-26 [web] Add listing visuals per §4.9: the glass step capsule, photos first with the three-shot recipe, Review showing the real card and header, and the small publish moment (with UX-19, UX-70) — https://is1-ssl.mzstatic.com/image/thumb/PurpleSource221/v4/bc/38/45/bc384593-d57b-76e5-7e27-c6d130dd5ff1/2_-_App_store_-_USA_-_6_U002c5_inch.png/600x1300bb.jpg
- [ ] VD-27 [design]+[app] A layered iOS 26 app icon (Icon Composer: light, dark, clear, tinted) and a matching Android adaptive/themed icon — https://www.apple.com/newsroom/images/2025/06/apple-introduces-a-delightful-and-elegant-new-software-design/article/Apple-WWDC25-Liquid-Glass-Icon-Composer-250609_big.jpg.large.jpg
- [ ] VD-28 [web] You per §4.10: a plate band with a 64 avatar and a lit rim, opaque stat tiles, an iOS inset-grouped Preferences list with glass segmented Appearance, and the Glass effects and Haptics rows — docs/research/2026-10-visual-direction.md §4.10
- [ ] VD-29 [web] The specular highlight follows device tilt on the ticket and the plate (DeviceOrientation, clamped to ±8°, off under Reduce Motion and in `lite`) — https://developer.apple.com/videos/play/wwdc2025/219/
- [ ] VD-30 [web] True refraction on desktop Chromium only: an `feDisplacementMap` droplet in the dock and segmented controls behind `CSS.supports('backdrop-filter','url(#lg)')` and `data-glass='full'`; never required for the look — https://kube.io/blog/liquid-glass-css-svg/
- [ ] VD-31 [app] A device performance pass: a 10 s scroll on Explore and the listing on a 2021 mid-range Android (4 GB) and an iPhone 12, in `full` and `lite`; frame-time traces attached; the budget in §3.5 met or the thresholds retuned — docs/research/2026-10-visual-direction.md §3.5

---

## 7. What could not be fetched or checked

- **Web search** was unavailable for this session (its quota was used up by earlier agents), so every source here is a directly known URL. Mobbin and Dribbble shots were not collected: Mobbin needs an account, and there was no search to find Dribbble shots.
- **Uber Base** (https://base.uber.com/) and **uber.design** render their text with scripts, so only headings were fetched. The Uber notes come from the App Store screenshots and known public facts about Base and Uber Move.
- **Instagram's** 2025 redesign announcement (a guessed about.instagram.com URL returned 404), **X's** blog (403) and **Revolut's** newsroom (403) could not be fetched. Their notes come from their current App Store screenshots.
- **Spotify Design** (design.spotify.com) did not resolve.
- **The HIG Sheets page** (JSON) holds no Liquid Glass detail. The sheet behaviour is from "Adopting Liquid Glass" and WWDC25 session 356.
- **Airbnb's** newsroom has no text about the 3D icons or motion beyond "dimensional and beautifully animated". The icon notes are read from its images.
- **Signed-out Welcome** was not seen live, because the shared session is signed in. It is described from `Welcome.tsx`.
- **A real 1440 px window** could not be used, because resizing would have moved the other agent's window. The desktop was seen in a 1440 × 1000 iframe and the 900 px window.
- **Refraction, tilt and frame times** need real devices (VD-31).
