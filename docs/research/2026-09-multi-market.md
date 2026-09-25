# Going beyond Germany: Europe, the UK, the US and Canada (2026-09)

This is research, not legal or tax advice. It covers GOAL.md item 16. Items
marked **[legal/business]** need a lawyer, a tax adviser or a founder's
decision before anyone builds them. The proposed decision record is
[`../adr/0013-markets.md`](../adr/0013-markets.md). The checklist is in
section 12 (`M-n`).

## 1. Where the code assumes Germany

Line numbers are for the `prod-readiness` working tree on 2026-09-26.

| File:line | What it assumes | What changes |
|---|---|---|
| `backend/services/booking/booking/routes.py:180` | Every booking is `currency="eur"` | Take the currency from the listing's market; the quote carries it |
| `backend/services/booking/booking/tables.py:50` | Column default `"eur"` | Drop the default; `NOT NULL` with no default, so a missing currency fails |
| `backend/libs/cappy_common/cappy_common/models.py:19` | `Cents = int`, amounts carry no currency | A `Money(amount_minor, currency)` pair on `Quote`, `Listing` rates, `Offer` and events; minor units come from ISO 4217 (JPY-style 0 decimals and 3-decimal currencies exist) |
| `backend/services/matching/matching/domain/money.py:9` · `web/src/domain/money.ts:22` | `euros(n)` = ×100 | Minor-unit conversion by currency (`Intl.NumberFormat(...).resolvedOptions().maximumFractionDigits` on the web, a small ISO 4217 table in Python) |
| `web/src/domain/money.ts:10` | `Intl.NumberFormat(..., {currency: 'EUR'})`; `formatEur` everywhere | `formatMoney(amount, currency)`; the currency comes with every price |
| `web/src/app/components/ui.tsx:380,386` | Money input shows a fixed "€" and only swaps `.`/`,` for `de-DE` | Symbol and separators from `Intl.NumberFormat(locale, {currency}).formatToParts` |
| `backend/services/notifications/notifications/texts.py:145-150` | Hand-rolled money format; only € £ $; `de` vs everything else | Babel's `format_currency(amount, currency, locale=...)` (CLDR), or send pre-formatted strings from one place |
| `backend/services/payments/payments/invoices.py:3-7,30` | `VAT_BPS = 1900`: German VAT 19 % on every fee, for every owner | A tax decision per fee line: rate, scheme (domestic, reverse charge, OSS, UK VAT, Swiss VAT, GST/HST/QST, US sales tax or none) and the legal text, stored on the invoice row; from Stripe Tax or a rules table per market |
| `backend/services/payments/payments/invoices.py:31-33,55,106` | Invoice date and numbering year in Europe/Berlin | The issuing entity's time zone; a number series per issuing entity (and per country where the law wants one) |
| `backend/services/payments/payments/invoices.py:144-178` | A German invoice: `lang="de"`, "Rechnung", "USt", "Leistungsdatum", "Vermittlungsgebühr", German € format, § 14 UStG, § 33 UStDV | Invoice template per issuing entity and language; US/CA "receipts" carry sales tax/GST lines and registration numbers (GST/HST BN, QST number) instead |
| `backend/services/payments/payments/settings.py:27-47` · `infra/platform/variables.tf:96-97` · `infra/platform/ecs.tf:46-49` | One operator (`LEGAL_COMPANY`, `LEGAL_ADDRESS`, `LEGAL_VAT_ID`, `LEGAL_TAX_NUMBER`), default "Musterstraße 1, 10115 Berlin", "§ 14 UStG" | A `legal_entities` table in config: one per contracting entity, with its tax registrations per jurisdiction (EU VAT ID, UK VAT, CH UID/MWST, US EIN and state permits, CA BN/GST, QST) |
| `backend/services/catalog/catalog/routes.py:99-115` | VAT IDs: EU member-state prefixes only, and the error text explains the German format | Validate per country: EU VAT (+ VIES check), GB VAT (HMRC API), CHE-UID, CA BN, US EIN (format only); error text per country |
| `backend/services/catalog/catalog/tables.py:69` · `models.py:117-126` | Trader identity by § 5b UWG / § 312l BGB | The field set is right for the EU (Omnibus, DSA Art. 30); add country and a structured address; US/CA need a business name and state/province registration only for tax |
| `backend/libs/cappy_common/cappy_common/categories.py:26-29` and every `dac7=` | One reporting scheme: EU DAC7 (PStTG) | A reporting tag that maps to the OECD Model Rules categories (DAC7, UK, Canada Part XX all use them) plus a US 1099-K flag; the tag is per category, the obligation per market |
| `backend/services/payments/payments/provider.py:171-179` | Connected accounts are created with no `country`, so Stripe makes them in the platform's country (DE) | Pass the owner's country; use the market's Stripe platform (a US platform for the US and Canada); request `card_payments` or the recipient service agreement per the cross-border rules |
| `backend/services/payments/payments/cli.py:26-42` | Test account is `DE`, `+49`, Berlin, `eur` | Test fixtures per market (DE, FR, GB, US, CA) |
| `backend/services/payments/payments/provider.py:85-93` | One Stripe client, one platform | A Stripe client per platform account; the booking's market picks it |
| `backend/libs/cappy_common/cappy_common/models.py:108-114,132,155,218-231,310,362` | Places are named `District`s (name, city, metro, country, lat, lng); an owner, a listing and a search origin are a district **name** | A listing has a point (lat/lng), a country, a subdivision (state/province/Land), a postal code and an IANA time zone; a search origin is a point |
| `backend/services/catalog/catalog/tables.py:33-37,52,86,109-130` | `districts` table; `owners.district` and `listings.district` are FKs to its name; indexes by district | Replace with `geography(Point)` + GiST (PostGIS, available on Aurora PostgreSQL 16) or an H3 cell column + B-tree; keep `district` only as a display label |
| `backend/services/catalog/catalog/repository.py:219-262,520-603` | Radius search walks the nearest districts; `nearest_district` scans every district in Python | `ST_DWithin(point, origin, radius)` ordered by `<->`; no district walk |
| `backend/services/catalog/catalog/routes.py:239-240,285-286,347-368` | "unknown district" unless the name is in the seeded list; `GET /districts`, `/districts/nearest` | Geocode addresses; `GET /places/autocomplete` (Amazon Location); the list of districts goes |
| `backend/services/catalog/catalog/settings.py:11` · `web/src/app/store.tsx:38` · `web/src/app/screens/AddListing.tsx:201` | Default home district `"Kreuzberg"` | Default origin = the market's main city from the market config, or the device location |
| `backend/libs/cappy_common/cappy_common/fixtures/seed.json` | 18 of 37 districts are Berlin; the rest are Amsterdam, Paris, Milan, Lisbon; no UK, CH, US or CA | Seed at least one city per launch cell (Berlin, Paris, London, Zürich, New York, Toronto, Montréal) with local currency, units and time zone |
| `backend/libs/cappy_common/cappy_common/fixtures.py:59,73,83` | Seed slots and reviews built in Europe/Berlin | Each seeded listing's own time zone |
| `backend/services/notifications/notifications/texts.py:126-142` | Every time in every email is Berlin time (the code says so: "ponytail: Cappy's market is Germany") | Format in the **listing's** time zone and name it when it differs from the reader's ("14:00 EDT") |
| `web/src/app/format.ts:13-30` · `components/Cover.tsx:36,123` | Times are shown in the device's zone, not the listing's | Pass `timeZone: listing.timeZone` to every `toLocale*String` for booking windows; show the zone when it differs from the device |
| `backend/services/matching/matching/domain/match.py:31,81` | `"{km} km away"` in reasons | Distance stays km internally; the text is formatted by the client in the market's unit |
| `web/src/app/format.ts:78-83` · `screens/Browse.tsx:29-31,274,373,429-438,536` · `store.tsx:34` | Radii 10/30/75/150 km, "75 km is the Berlin-Brandenburg belt", every label in km | Radii and labels in miles for US and GB (`Intl.NumberFormat(locale, {style:'unit', unit:'mile'})`), km elsewhere; defaults per market |
| `backend/services/matching/matching/routes.py:184` · `catalog/routes.py:172` | `maxKm` query parameter | Keep the API in km (one unit on the wire); convert at the edge |
| `backend/services/booking/booking/messages.py:46-47` | Phone masking recognises `+`, `00` or `0` prefixes (German habits) | Also NANP numbers without a prefix ("415 555 0132", "(416) 555-0132"); ideally `phonenumbers.PhoneNumberMatcher` with the market as the default region |
| `backend/services/booking/booking/messages.py:53-54` | IBAN masking only | Also US/CA account and routing number patterns |
| `web/src/app/screens/AddListing.tsx:768` | Address placeholder "Oranienstraße 12, 10999 Berlin"; free-text address | Structured address form per country (fields and order from Google's address metadata / libaddressinput), placeholder per market |
| `web/src/app/screens/AddListing.tsx:43` | Template "Berlin to anywhere in the EU" | Per-market template text |
| `web/src/i18n.ts:11,17,21,30` | `Lang = 'en' \| 'de'`; `locale()` is `de-DE` or `en-GB` | Languages from a list; the locale is language **and** region (`fr-CA`, `en-US`, `de-CH`); message catalogues loaded lazily |
| `web/src/i18n.ts:55-62` | `plural(n, one, many)`: two forms | ICU MessageFormat (`Intl.PluralRules`) — Polish, Czech and others have 3-4 forms |
| `backend/services/notifications/notifications/texts.py:52,104-106` | Emails in `de` or `en` only | Same catalogue list as the web; fall back per language, then English |
| `web/src/app/screens/Help.tsx:171` · `AddListing.tsx:56` · `Legal.tsx:20-39,74` | `lang() === 'de' ? ... : ...` ternaries | Catalogue lookups, so a third language is a file, not an edit in every screen |
| `web/src/app/screens/Legal.tsx:120-148` · `Welcome.tsx:91` · `Profile.tsx:255` | An Impressum under § 5 DDG and § 36 VSBG for everyone | Show the Impressum to EU/DACH users; "Legal notice"/"Company information" per entity elsewhere; the US/CA entity's address and contact |
| `web/src/app/screens/Legal.tsx:241-252,393-470` · `Profile.tsx:258` · `BookingDetail.tsx:186,679-694` | The EU/German withdrawal right, model form and "withdraw" wording for every user | Show it where EU/UK consumer law applies (UK has its own Consumer Contracts Regulations); US/CA get the cancellation policy (Québec's Consumer Protection Act has its own distance-contract rules) |
| `web/src/app/screens/Legal.tsx:268-272` | "German law applies" | Governing law and forum per contracting entity; US terms need an arbitration decision **[legal/business]** |
| `web/src/app/screens/Legal.tsx:150-208` | GDPR-only privacy policy | Per-region notices: GDPR/UK GDPR, CCPA/CPRA "Notice at collection" and rights, PIPEDA/Law 25 |
| `web/src/app/screens/Onboarding.tsx:26-49` · `catalog/tables.py:71` | Minimum age 18, one checkbox | Fine for every target market for contracts, but some US states set 21 for vehicle rental; keep the age per market and per category |
| `infra/envs/prod/main.tf:7,20` · `infra/platform/variables.tf:10-12` | One region, eu-central-1, for all data | One stack per cell (EU, North America); see section 10 |
| `infra/platform/identity.tf:4-110` · `outputs.tf:45` | One Cognito user pool | One pool per cell; the app picks the pool from the market |
| `infra/platform/email.tf:5-70` | SES in the one region, one sender | SES per cell; same domain, per-cell MAIL FROM |
| `web/src/app/screens/Listing.tsx:550` · `Profile.tsx:227` · `BookingDetail.tsx:587` · `domain/pricing.ts:3` · `matching/domain/pricing.py:12` | One 15 % fee, VAT-inclusive, shown as "15 %" | Fee per market in config; US/CA show prices before tax and add tax at checkout, the EU/UK show tax-inclusive prices |

What is already market-neutral and should stay: timestamps are `timestamptz`
and UTC on the wire (`cappy_common/db.py:48-61`); amounts are integers in minor
units; the booking and payment rows already have a `currency` column; the
Payment Element gets the UI language (`PayStep.tsx:29`); `LocationPicker` uses
`Intl.DisplayNames` for country names; the DSA, report/block, account deletion
and data export flows are needed in every market anyway.
