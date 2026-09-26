# Going beyond Germany: Europe, the UK, the US and Canada (2026-09)

This is research, not legal or tax advice. It covers GOAL.md item 16. Items
marked **[legal/business]** need a lawyer, a tax adviser or a founder's
decision before anyone builds them. The proposed decision record is
[`../adr/0013-markets.md`](../adr/0013-markets.md). The checklist is in
section 12 (`M-n`).

Sources were checked on 2026-09-26. These were not fetched and need a check
before anyone relies on them: the Airbnb approximate-location article, the
Aurora PostGIS page, the EU invoicing-rules page, and the Turo, Etsy and
swiss-platform details marked as secondary in the text.

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

## 2. How the big marketplaces run many markets

| Company | What they do | Source |
|---|---|---|
| Airbnb | One global app and dataset. The contracting entity depends on where the user lives: Airbnb, Inc. (US), Airbnb Ireland UC (EEA, UK, CH and most other countries). Payments go through a separate entity per region: Airbnb Payments, Inc. (US), Airbnb Payments UK Ltd (EEA, CH, UK), Airbnb Payments Canada Inc. (from 8 Sep 2025). The currencies you can pay in depend on the payments entity. | https://www.airbnb.com/help/article/2908 · https://www.airbnb.com/help/article/2909 |
| Etsy | EEA users contract with Etsy Ireland UC, and Etsy Payments Ireland Ltd (a regulated payment institution) handles their money. Canada has had a separate Etsy Canada Ltd since Sep 2025. | https://www.etsy.com/legal/etsy-payments/ |
| Vinted | Vinted UAB (Lithuania) runs every market. For a cross-border purchase, the buyer's country terms apply. US↔UK sales are live but limited to some US states. The exchange rate is locked at checkout, with a 1.2 % conversion fee shown. | https://www.vinted.com/help/1555-us-uk-international-sales |
| Getaround | Getaround SAS (Paris) keeps separate EU and US terms. Insurance and protection are per market. (That it left the US in 2025 comes from secondary sources.) | https://getaround-assets.gumlet.io/legal/2024-10-03/20241003_EU_TOS_EN.pdf |
| Fat Llama / Hygglo | Merged in 2022, rebranded Hygglo on 24 Nov 2025. Runs SE, NO, UK, US, FI, DK and CA, and accounts now work across countries. The closest peer to Cappy. | https://hygglo.com/uk/fatllama |
| Turo | Protection plans per market (France and Canada each have their own). It entered France by buying OuiCar. The contracting entities could not be checked (the site blocks fetches). | https://help.turo.com/en_us/protection-plans-in-detail-france-guests-ry6y3o962 |

**What this means for Cappy.** Everyone separates **legal entity and
payments entity by region** (US vs Europe, now Canada too). Everyone keeps
**one app** and uses **per-market terms, insurance and currency**. Vinted and
Hygglo let accounts cross borders and label currency conversion explicitly.
Nobody converts prices silently. Cappy should do the same: one app, a
`market` in configuration, one entity and payments platform per region, and
per-market terms and protection.

## 3. Payments: Stripe Connect across borders

- **A German platform can pay US and Canadian owners.** Stripe's
  cross-border payouts let platforms in the US, UK, EEA, Canada and
  Switzerland transfer to connected accounts in any of those regions. Stripe's
  own example is a platform in Germany paying a seller in Canada.
  https://docs.stripe.com/connect/cross-border-payouts
- **Only with the full service agreement.** "You can't make cross-border
  payouts to connected accounts under a recipient service agreement." Accounts
  on the recipient agreement need Global Payouts, which only US or UK
  platforms can use. https://docs.stripe.com/connect/service-agreement-types
- **Only without `on_behalf_of`.** Cross-border works with separate charges
  and transfers (what ADR 0005 uses) or destination charges, **without**
  `on_behalf_of`. That makes the platform the settlement merchant: its
  country, fees, statement descriptor, refunds and disputes.
  https://docs.stripe.com/connect/charges
  - So on the DE platform, every US charge is a German merchant charging a US
    card: cross-border card fees, and a German company as the obvious US
    marketplace facilitator.
  - A **US entity with its own Stripe platform** gets domestic acquiring and a
    US contracting party. Stripe does not strictly require one (not confirmed
    with Stripe; ask sales) **[legal/business]**.
- **Currencies.** Present in the listing's currency. Stripe converts when the
  presentment currency differs from the settlement currency, and again when a
  transfer's currency differs from the connected account's. Both conversions
  are at mid-market plus a fee.
  - Add settlement bank accounts in GBP, CHF, USD and CAD so the main
    currencies settle without conversion. Connected accounts can enable
    multi-currency settlement.
  - https://docs.stripe.com/connect/currencies · https://docs.stripe.com/connect/payouts-connected-accounts
- **Stripe Tax** supports marketplaces where the platform is liable
  (marketplace facilitator or deemed supplier), with destination charges or
  separate charges and transfers. It does not support direct charges. Stripe
  says a tax adviser has to decide which role applies.
  https://docs.stripe.com/tax/tax-for-marketplaces
- **Tax reporting.**
  - 1099-K: Stripe files it only when the connected account pays Stripe's
    fees (`controller.fees.payer=account`); otherwise the platform files.
    https://docs.stripe.com/connect/tax-reporting
  - DAC7, UK and Canada reports: "platform tax reporting" is a **preview**,
    and it covers all EU countries except Poland.
    https://docs.stripe.com/connect/platform-tax-reporting
- **Cappy today.**
  - `create_account` (`payments/provider.py:171`) passes no `country`, so
    every owner becomes a DE account. Pass the owner's country.
  - Keep separate charges and transfers without `on_behalf_of`: they are
    already right for cross-border.
  - Put the currency on the transfer, and give each market a Stripe platform
    key.

## 4. Tax

**EU VAT.**
- The OSS lets one EU registration cover B2C services across the EU.
  https://europa.eu/youreurope/business/taxation/vat/one-stop-shop/index_en.htm
- Cappy's fee to a *private* owner is likely an electronically supplied
  service, taxed at the owner's country rate through the OSS. To a *business*
  owner in another EU country, the reverse charge applies. **[legal/business]**
  (G-B2 already open).
- Today every fee carries 19 % DE VAT, which is wrong for any non-German
  owner.

**ViDA (Directive (EU) 2025/516).**
- From 1 Jul 2028, platforms become the deemed supplier of short-term
  **accommodation** (≤ 30 nights) and **passenger road transport**. Member
  states may defer this to 2030.
- It does **not** cover tool, van (without driver), workshop or storage
  rental. Cappy should still design for a "deemed supplier" flag per
  category × market, because the scope list may grow.
- https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=OJ%3AL_202500518 · https://sede.agenciatributaria.gob.es/Sede/en_gb/iva/novedades-iva/novedades-normativa-2025/directiva-2025-516-consejo-11-2025.html

**DAC7.**
- Covers rental of immovable property (workshops, studios, storage), rental
  of any means of transport (vans), personal services and sale of goods.
  Plain tool rental is arguably out of scope.
- Non-EU platforms are in scope too. One EU member state receives all the
  reports.
- https://taxation-customs.ec.europa.eu/taxation/tax-transparency-cooperation/administrative-co-operation-and-mutual-assistance/dac7_en

**UK.**
- The online-marketplace deemed-supply rule covers **goods** only.
  https://www.gov.uk/guidance/vat-and-overseas-goods-sold-to-customers-in-the-uk-using-online-marketplaces
- A non-UK-established business has **no registration threshold**, so a fee
  to UK private owners probably means registering for UK VAT from the first
  pound. **[legal/business]** https://www.gov.uk/guidance/register-for-vat
- UK platform reporting follows the OECD model: data collected from 2024,
  first report 31 Jan 2025.
  https://www.gov.uk/government/publications/reporting-rules-for-digital-platforms/reporting-rules-for-digital-platforms

**Switzerland.**
- Foreign businesses register once worldwide turnover exceeds CHF 100,000
  and they make supplies in Switzerland.
- The 2025 platform rule (Art. 20a MWSTG) makes platforms the deemed
  supplier of **goods deliveries** only. For services, Cappy's fee to Swiss
  owners falls under the normal rules. **[legal/business]**
- https://www.estv.admin.ch/de/mwst-anmeldung-plattformbesteuerung

**US sales tax.**
- Every sales-tax state has a marketplace-facilitator law, written mainly
  for goods. https://www.streamlinedsalestax.org/for-businesses/marketplace-facilitator
- **Rental of tangible personal property is taxable in most states**. For
  example, California taxes rental receipts, but not a lease that comes with
  an operator. https://cdtfa.ca.gov/industry/rental-companies/leases-in-general.htm
- Space is taxed in some states:
  - Florida still taxes self-storage, parking and short-term rentals after
    repealing its commercial-rent tax.
    https://floridarevenue.com/taxes/tips/Documents/TIP_25A01-04.pdf
  - Hawaii's GET covers all rental income. https://tax.hawaii.gov/rental/
- Vehicles carry separate rental-car and peer-to-peer car-sharing taxes in
  many states.
- Cappy therefore needs a tax engine that works by address (state, county,
  city) and category: Stripe Tax, or Avalara/TaxJar. It also needs a nexus
  analysis per state **[legal/business]**.

**1099-K.** The One Big Beautiful Bill Act restored the third-party
settlement threshold to **> $20,000 and > 200 transactions**, retroactively.
Owners who never reach it still need a TIN collected for backup withholding
and for 1099-NEC/MISC questions.
https://www.irs.gov/newsroom/irs-issues-faqs-on-form-1099-k-threshold-under-the-one-big-beautiful-bill-dollar-limit-reverts-to-20000

**Canada.**
- GST/HST simplified registration covers non-resident distribution
  platforms (goods, digital) and accommodation platforms (over $30,000).
  Whether tool or space rental through a platform is caught is **not
  settled** **[legal/business]**.
  https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/gst-hst-businesses/digital-economy.html
- Québec QST has a parallel specified system.
  https://www.revenuquebec.ca/en/businesses/consumption-taxes/gsthst-and-qst/special-cases-gsthst-and-qst/suppliers-outside-quebec/qst-registration-for-suppliers-outside-quebec/registration-under-the-specified-system-operators-of-accommodation-platforms/
- Cappy's own fee to Canadian owners is a supply by a non-resident. It
  likely needs GST/HST registration once over CAD 30,000.
- **Part XX platform reporting** has been in force since 2024 and covers
  immovable property, means of transport, personal services and goods. Tool
  rental is not listed.
  https://www.canada.ca/en/revenue-agency/programs/about-canada-revenue-agency-cra/compliance/reporting-rules-digital-platforms/guidance-on-reporting-rules.html

**What Cappy should do.**
- Keep the reporting classification per category (already there, as `dac7`).
  Rename it to the OECD activity (`immovable_property`, `transport`,
  `personal_service`, `goods`, `none`), which DAC7, the UK and Canada share.
- Collect TIN, date of birth and address per seller, in every market, from
  day one (Stripe KYC holds most of it).
- Store the tax decision on every invoice line.

## 5. Privacy, marketing and consumer law

**California (CCPA/CPRA).**
- Applies above **$26,625,000** revenue (2025-26), or when handling the
  personal information of 100,000+ consumers, or when most revenue comes from
  selling or sharing it. https://privacy.ca.gov/laws-and-regulations/monetary-thresholds-in-the-ccpa/
- A business that "sells or shares" data (including cross-context
  behavioural ads) needs a **"Do Not Sell or Share My Personal Information"**
  link. It must also treat **Global Privacy Control** as a valid opt-out and
  show that it did. https://cppa.ca.gov/regulations/pdf/ccpa_statute_eff_20260101.pdf · https://globalprivacycontrol.org/
- For Cappy: no ad pixels means nothing is sold or shared. Say so in the
  notice, honour GPC anyway (analytics off), and add a notice at collection
  and the access, deletion and correction rights. Deletion and export
  already exist.

**Other US states.**
- 19 comprehensive state laws are in force on 1 Jan 2026. Indiana, Kentucky
  and Rhode Island started that day.
- Texas and Nebraska have no revenue threshold.
- Most require opt-outs for targeted ads, and several require universal
  opt-out signals (GPC).
- https://iapp.org/resources/article/us-state-privacy-laws-overview

**Canada.**
- **PIPEDA**: processing abroad is a "use" and needs no extra consent, but
  the policy must say so and a contract must protect the data.
  https://www.priv.gc.ca/en/privacy-topics/airports-and-borders/gl_dab_090127/
- **Québec Law 25** (in force in stages 2022-2024):
  - Publish the title and contact of the person in charge of personal
    information.
  - Run a **privacy impact assessment before data leaves Québec**.
  - Set privacy to the highest level by default.
  - Keep an incident register.
  - Support data portability.
  - https://www.cai.gouv.qc.ca/protection-renseignements-personnels/sujets-et-domaines-dinteret/principaux-changements-loi-25
- The North America cell in ca-central-1 removes the transfer PIA for the
  database. Stripe and any US processors still need one.

**UK.**
- UK GDPR plus the **Data (Use and Access) Act 2025**. Most of it has
  applied since 5 Feb 2026.
- A mandatory complaints procedure has applied since 19 Jun 2026.
- Some analytics cookies no longer need consent.
- https://ico.org.uk/about-the-ico/what-we-do/legislation-we-cover/data-use-and-access-act-2025/the-data-use-and-access-act-2025-what-does-it-mean-for-organisations/

**Marketing email and SMS.**
- **CASL** (Canada) needs express opt-in consent (implied consent lasts two
  years after a transaction), sender identification, and unsubscribes
  honoured within 10 business days. https://crtc.gc.ca/eng/com500/faq500.htm
- **CAN-SPAM** (US) needs opt-out within 10 business days and a postal
  address. https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business
- Cappy's marketing is already off by default (U-22). Keep it opt-in
  everywhere, record the consent (when, what text), and add
  `List-Unsubscribe` and a postal address.
- **TCPA** (US): marketing texts need prior express written consent.
  Revocation by any reasonable means (STOP) is honoured within 10 business
  days (since Apr 2025). https://law.justia.com/cases/federal/appellate-courts/ca11/24-10277/24-10277-2025-01-24.html
- Transactional SMS only, and SMS opt-in stored separately.

**Consumer law.**
- The EU withdrawal right and the withdrawal button apply in the EU.
- The UK has its own Consumer Contracts Regulations 2013.
  https://www.legislation.gov.uk/uksi/2013/3134
- Québec's Consumer Protection Act has distance-contract rules
  (cancellation and the required disclosures).
  https://www.legisquebec.gouv.qc.ca/en/document/cs/P-40.1
- The US has no general withdrawal right. The cancellation policy governs,
  plus state auto-renewal and junk-fee rules (the FTC's fee rule covers
  short-term lodging and live events; list the all-in price anyway).
- The legal pages and the cancel wording are per consumer-law regime.

**Québec Charter of the French Language (Bill 96).**
- Software, apps included, must be available in French when a French version
  exists (s. 52.1).
  https://www.legisquebec.gouv.qc.ca/fr/version/lc/c-11?code=se%3A52_1
- Since 1 Jun 2023, contracts of adhesion (the terms) must be offered in
  French first.
- Since 1 Jun 2025, trademark and signage rules are stricter.
- So **fr-CA is a launch blocker for Québec**, not a nice-to-have. That
  covers the app, emails, terms and invoices.

## 6. Accessibility

- **EAA**: applies to e-commerce services since 28 Jun 2025. Micro-enterprise
  service providers are exempt. EN 301 549 (WCAG 2.1 AA; the new v4 points to
  WCAG 2.2) gives presumption of conformity. https://commission.europa.eu/strategy-and-policy/policies/justice-and-fundamental-rights/disability/european-accessibility-act-eaa_en
- **ADA Title III** has no technical rule for businesses. DOJ points to WCAG,
  and WCAG 2.1 AA is the de facto test in lawsuits.
  https://www.ada.gov/resources/web-guidance/
  - The 2024 Title II rule (WCAG 2.1 AA) binds state and local governments
    only; its deadlines moved to 2027/2028.
    https://www.federalregister.gov/documents/2026/04/20/2026-07663/extension-of-compliance-dates-for-nondiscrimination-on-the-basis-of-disability-accessibility-of-web
  - Section 508 binds federal agencies only.
- **AODA** (Ontario): organisations with 50+ employees need WCAG 2.0 AA on
  public websites. https://www.ontario.ca/laws/regulation/110191
- The **Accessible Canada Act** covers federally regulated sectors only, so
  it is out of scope for Cappy.
  https://www.canada.ca/en/employment-social-development/programs/accessible-canada/act-summary.html
- **For Cappy:** one target covers everything: **WCAG 2.2 AA**, which
  exceeds each law. Publish an accessibility statement per region (the EU one
  exists), and run axe in CI.

## 7. Data residency and regions

- **No target law requires data to stay in its country** for a private
  marketplace:
  - GDPR allows transfers under the EU-US Data Privacy Framework and SCCs.
    https://www.dataprivacyframework.gov/
  - UK and Swiss law recognise the EU as adequate.
  - PIPEDA allows processing abroad with notice.
  - Québec requires a PIA.
- What argues for regions is **latency** (every North American request to
  Frankfurt adds roughly 90-150 ms), **trust** ("EU data stays in the EU" is
  a sales point for European business owners), the Québec PIA, and the
  **blast radius** of an outage.
- **Recommendation: two cells.** EU in eu-central-1 (EEA, CH, UK) and North
  America in ca-central-1 (US, CA).
  - Montréal is a few ms from us-east-1.
  - Canadian data stays in Canada.
  - Every service Cappy uses is there: ECS Fargate, Aurora PostgreSQL,
    Cognito, SES, SNS/SQS and Amazon Location.
    https://docs.aws.amazon.com/general/latest/gr/location.html
  - Avoid ca-west-1: no Location Service and no Cognito multi-Region.
- **Cognito.**
  - User pools are regional. Multi-Region replication launched on 4 Jun 2026,
    but it copies a pool one way for failover; it is not a residency tool.
    https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-multi-region.html
  - Use **one pool per cell**. The app chooses the cell from the market
    picked on the welcome screen, and the sign-in screen can switch region.
  - A global directory of hashed emails (for "which region is my account in")
    is the upgrade path. Skip it until support asks.
- **Routing.**
  - One domain for the web, and an API host per cell (`eu.api…`, `na.api…`).
  - The web bundle and the store apps are the same build; the market config
    maps market to API host and Cognito pool.
  - CloudFront stays global.
- **Rejected:** Aurora Global Database or DynamoDB global tables (they copy
  every row everywhere), and one cell per country (triple the operations for
  no legal gain). See ADR 0013.

## 8. Places: points, addresses, phones, units

- **Points, not districts.**
  - Store `geography(Point, 4326)` with a GiST index. Search with
    `ST_DWithin(point, :origin, :metres)`, ordered by `point <-> :origin`.
  - PostGIS is supported on Aurora PostgreSQL.
    https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Appendix.PostgreSQL.CommonDBATasks.PostGIS.html
  - This replaces the district walk (`catalog/repository.py:520-603`) and the
    Python scan of every district (`:252`).
  - H3 (https://h3geo.org/) is useful later for "idle capacity near you"
    counts and privacy-preserving map pins (show the H3 cell, not the
    address). It is not needed for search.
- **Privacy of the owner's location.** Keep the exact point private. Public
  responses get a point snapped to a ~500 m cell and a label
  ("Kreuzberg, Berlin" or "Brooklyn, NY"), as Airbnb does with its
  approximate map circle.
- **Geocoding.**
  - Use Amazon Location Service in the cell's own region, so addresses never
    leave it.
  - Geocode with `IntendedUse=Storage`: storage is allowed and billed higher.
    Autocomplete and Suggest results **may not be stored**, so autocomplete
    only to pick, then geocode the picked place with Storage and store that.
    https://docs.aws.amazon.com/location/latest/developerguide/places-intended-use.html
  - Reverse-geocode to fill country, subdivision and time zone. A time-zone
    lookup library works from the point, for example `timezonefinder`.
- **Addresses.** Use Google's address metadata (the libaddressinput data) for
  the field list, order, required fields and postal-code patterns per
  country: https://github.com/google/libaddressinput ·
  https://chromium-i18n.appspot.com/ssl-address/data/US . Store it
  structured: `line1, line2, locality, dependent_locality, admin_area,
  postal_code, country`.
- **Phones.** Store phone numbers as E.164. Use `libphonenumber`
  (https://github.com/google/libphonenumber; Python:
  https://github.com/daviddrysdale/python-phonenumbers) for validation, and
  its `PhoneNumberMatcher` with the reader's market as the default region for
  masking numbers in chat. The current regex misses "(416) 555-0132".
- **Units.** Use miles for US and GB users, km elsewhere. Keep km on the wire
  and format with `Intl.NumberFormat(locale, {style: 'unit', unit: 'mile'})`.
  https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat/NumberFormat
  Radius presets per market (5/20/50/100 mi).
- **Time zones.**
  - Every listing has an IANA zone.
  - Show booking windows in the listing's zone, and add the zone
    abbreviation when the viewer's device differs.
  - Emails use the listing's zone.
  - Availability (opening hours) is local wall-clock time in the listing's
    zone, which is DST-safe.

## 9. Languages and formats

- **Order:**
  1. English (en-GB, en-US), German (de-DE, with de-AT and de-CH differing in
     a few terms and ß for CH).
  2. **French (fr-FR and fr-CA)**, needed for France, Belgium, Switzerland
     and required for Québec.
  3. Spanish, Italian, Dutch.
  4. Polish, Portuguese, Swedish, Danish, Czech.
  No RTL.
- **Catalogues.**
  - Move from `en → de` string maps with `plural(one, many)` to ICU
    MessageFormat (`{n, plural, one {# day} few {# dni} many {# dni} other
    {# dnia}}`). Polish and Czech have four forms and French has a "many".
    https://www.unicode.org/cldr/charts/48/supplemental/language_plural_rules.html
    · https://unicode-org.github.io/icu/userguide/format_parse/messages/
  - A small library (FormatJS `intl-messageformat`, about 10 kB) or
    `Intl.PluralRules` with a tiny formatter is enough.
  - Load catalogues lazily, per language.
- **Locale vs language.** Locale = language + region, for example `fr-CA` for
  Montréal and `en-CA` for Toronto. Money, dates and numbers come from
  `Intl` with the full locale. Prices come in the listing's currency, whatever
  the reader's language.
- **Backend emails.** Use Babel (`format_currency`, `format_datetime` with
  `tzinfo`) instead of hand-written formats.
  https://babel.pocoo.org/en/latest/api/numbers.html
- **Stores.** App Store Connect treats French (Canada) as its own
  localisation. Add a store listing per launch language.
  https://developer.apple.com/help/app-store-connect/reference/app-information/app-store-localizations/

## 10. Proposed architecture

**Market model** (details in ADR 0013).

```jsonc
// backend/libs/cappy_common/cappy_common/markets.json (also bundled into web/)
{
  "DE": { "currency": "EUR", "cell": "eu", "entity": "cappy-gmbh", "stripePlatform": "eu",
          "languages": ["de", "en"], "defaultLocale": "de-DE", "distanceUnit": "km",
          "pricesIncludeTax": true, "taxRegime": "eu-vat", "reporting": ["dac7"],
          "consumerLaw": "eu-crd", "feeBps": 1500, "minAge": 18, "status": "live" },
  "GB": { "currency": "GBP", "cell": "eu", "entity": "cappy-gmbh", "distanceUnit": "mi",
          "taxRegime": "uk-vat", "reporting": ["uk-drp"], "consumerLaw": "uk-ccr", ... },
  "US": { "currency": "USD", "cell": "na", "entity": "cappy-inc", "stripePlatform": "na",
          "pricesIncludeTax": false, "taxRegime": "us-sales-tax", "reporting": ["1099k"],
          "consumerLaw": "none", "distanceUnit": "mi", ... },
  "CA": { "currency": "CAD", "cell": "na", "languages": ["en", "fr"], "defaultLocale": "en-CA",
          "taxRegime": "ca-gst", "reporting": ["ca-part-xx"], ... }
}
```

**Who gets which market.**
- A **person** belongs to one cell, chosen at sign-up by their country of
  residence (the welcome screen asks; the device locale pre-selects).
  - That country is their home market: the default search origin, language,
    units and currency for display.
  - An owner's Stripe account is created in that country on the cell's
    platform.
- A **listing** gets its market from the country of its geocoded address,
  fixed after its first booking. The market decides:
  - currency;
  - tax (with the address's state or province);
  - consumer law;
  - the contracting entity;
  - the time zone.
- A **booking** takes the listing's market wholesale, frozen onto the booking
  row: `market`, `currency`, `tax_breakdown`, `entity`.

**Cross-market bookings.**
- **Yes inside a cell.** A Berlin member books in Paris, a Torontonian books
  in Buffalo. It is one database and one Stripe platform; the price is in the
  listing's currency, with a labelled approximate conversion.
- **No across cells**, at first. A Berlin member visiting New York creates a
  North America account.
- Owners list only in markets of their own cell. Their Stripe account's
  country is where they live, and cross-border payouts inside a region are
  supported.

**What changes in the services.**
- `cappy_common`: `Money`, `markets.json` and a `market_of(country)` helper;
  market-aware formatting lives only in web and notifications.
- catalog: `country`, `subdivision`, `postal_code`, `time_zone` and a
  `geography` point on listings (and on owners, private); geocoding;
  districts become labels; public coordinates are snapped.
- matching: search by point and radius; the km rule stays; the fee per
  market.
- booking: `market` and `currency` from the listing; the cancellation and
  withdrawal policy per `consumerLaw`.
- payments:
  - a Stripe client per `stripePlatform`;
  - the account country;
  - currency-aware transfers;
  - a tax decision per fee (Stripe Tax calculation, or a rules table);
  - invoices per entity and language;
  - seller tax info (TIN) collection.
- notifications: Babel formatting in the listing's zone; catalogues for
  every language; `List-Unsubscribe` and a postal address on marketing mail.
- web:
  - `formatMoney(amount, currency)`;
  - units and time zones;
  - ICU catalogues;
  - legal pages per regime;
  - a country picker on the welcome screen;
  - an API host and Cognito pool from the market.
- infra: `infra/envs/prod-eu` and `infra/envs/prod-na` (the same
  `infra/platform` module), with a Location Service place index per cell.

## 11. Launch order

1. **DACH: DE, then AT and CH.**
   - One language family, and EUR plus CHF.
   - The legal work is mostly done (German law, DSA, Impressum).
   - AT is EUR and the EU. CH adds only CHF, Swiss VAT on the fee and the
     FADP, and the DE platform can already onboard Swiss accounts.
   - This proves multi-currency and cross-border on the smallest step.
2. **EU core and the UK: FR, NL, BE, IT, ES, IE, then PL, the Nordics
   (SE/DK/NO/FI) and the UK.**
   - Same cell, same Stripe platform, same DSA and GDPR.
   - What's new is per-country VAT on the fee (the OSS), languages, and local
     insurance partners.
   - The UK adds GBP, miles, UK VAT registration, UK reporting and the CCR.
   - Hygglo's markets (Nordics and UK) show demand for tool rental there.
3. **US and Canada together, in the North America cell.**
   - The biggest change: a new entity, Stripe platform, cell, sales tax by
     state, 1099-K, CCPA and state privacy laws, and the TCPA.
   - Canada adds GST/HST, CAD, fr-CA and Québec Law 25 and Bill 96.
   - Start with a few metros (New York, Toronto, Montréal, then the west
     coast), and only in categories whose sales-tax treatment counsel has
     cleared. Vans come last in the US (state car-sharing laws and
     insurance).

The reason for this order: each step adds one new kind of difficulty.
DACH adds currency. EU/UK adds tax per country and languages. North America
adds an entity, a region and sales tax. Never all three at once.

## 12. Checklist

Most important first. `[legal/business]` items are decisions, not code.

- [ ] M-1 [legal/business] Entity plan: Cappy GmbH serves the EEA, CH and UK. Decide whether and when a US corporation (and later a Canadian subsidiary) with its own Stripe platform serves North America, or whether North America starts on the DE platform via cross-border payouts — https://docs.stripe.com/connect/cross-border-payouts
- [ ] M-2 [backend] `markets.json` in `cappy_common` (currency, cell, entity, stripePlatform, languages, units, tax regime, reporting, consumer law, fee, min age, status), with a loader, a test that every market is complete, and a copy in the web build — ADR 0013
- [ ] M-3 [backend] `Money(amount_minor, currency)` in models, quotes, offers and events; no `currency="eur"` (`booking/routes.py:180`) and no `"eur"` column default (`booking/tables.py:50`); minor-unit exponent from ISO 4217 — https://www.iso.org/iso-4217-currency-codes.html
- [ ] M-4 [web] `formatMoney(amount, currency)` replaces `formatEur`; the money input takes symbol and separators from `Intl.NumberFormat.formatToParts`; no hard-coded € (`ui.tsx:386`) — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat/formatToParts
- [ ] M-5 [backend] Listings get `country`, `subdivision`, `postal_code`, `time_zone` and a PostGIS `geography(Point)` with a GiST index; search by `ST_DWithin`; districts become labels; migration from districts to points — https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Appendix.PostgreSQL.CommonDBATasks.PostGIS.html
- [ ] M-6 [backend] Public coordinates snapped to about 500 m; the exact point only in the handover after acceptance (as the address is today) — https://www.airbnb.com/help/article/2874
- [ ] M-7 [backend]+[infra] Geocoding and autocomplete through Amazon Location Service in each cell; store only `IntendedUse=Storage` results, never autocomplete results — https://docs.aws.amazon.com/location/latest/developerguide/places-intended-use.html
- [ ] M-8 [web] Structured address form per country from the libaddressinput metadata, replacing the free-text field and the Berlin placeholder (`AddListing.tsx:768`) — https://github.com/google/libaddressinput
- [ ] M-9 [backend] Stripe accounts created with the owner's `country` on the market's platform (`payments/provider.py:171`); full service agreement; separate charges and transfers stay without `on_behalf_of` — https://docs.stripe.com/connect/service-agreement-types
- [ ] M-10 [backend] A Stripe client per `stripePlatform`; secrets per cell; webhooks per platform — https://docs.stripe.com/connect/charges
- [ ] M-11 [legal/business] VAT on the fee per owner: domestic, reverse charge (EU B2B), OSS (EU B2C), UK VAT (no threshold for non-established), Swiss MWST (CHF 100k worldwide), GST/HST and QST — https://europa.eu/youreurope/business/taxation/vat/one-stop-shop/index_en.htm
- [ ] M-12 [backend] The fee's tax becomes a decision per invoice line (rate, scheme, legal note), from Stripe Tax or a rules table; `VAT_BPS = 1900` goes (`payments/invoices.py:30`) — https://docs.stripe.com/tax/tax-for-marketplaces
- [ ] M-13 [backend] Invoice template and number series per issuing entity and language; issuer details per entity instead of one `LEGAL_*` set; dates in the entity's zone — https://taxation-customs.ec.europa.eu/taxation/vat/vat-directive/vat-invoicing-rules_en
- [ ] M-14 [backend] Seller tax data for reporting in every market: TIN, date of birth, address, and the OECD activity per category (rename `dac7`); reports via Stripe platform tax reporting (preview; not for PL) — https://docs.stripe.com/connect/platform-tax-reporting
- [ ] M-15 [web]+[backend] Times in the listing's time zone everywhere (web `timeZone` option, emails via Babel); show the zone when it differs from the device; no Europe/Berlin constants (`notifications/texts.py:128`, `invoices.py:33`, `fixtures.py:59`) — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat/DateTimeFormat
- [ ] M-16 [web] i18n: languages from a list, locale = language + region, ICU MessageFormat plurals, lazily loaded catalogues; remove every `lang() === 'de'` ternary — https://unicode-org.github.io/icu/userguide/format_parse/messages/
- [ ] M-17 [web]+[backend] French (fr-FR and fr-CA) catalogues for the app, emails, legal pages and invoices; a launch blocker for Québec (Charter s. 52.1, terms in French first) — https://www.legisquebec.gouv.qc.ca/fr/version/lc/c-11?code=se%3A52_1
- [ ] M-18 [web] Miles for US and GB users (radius presets and labels), km elsewhere; km stays on the wire — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat/NumberFormat
- [ ] M-19 [web] Legal pages per regime: Impressum for DE/AT (and CH), a company page elsewhere; withdrawal right and button only where EU consumer law applies; UK CCR text; Québec CPA; US/CA cancellation-policy wording (`Legal.tsx`, `BookingDetail.tsx:679-694`) — https://www.legislation.gov.uk/uksi/2013/3134
- [ ] M-20 [legal/business] Terms per contracting entity: governing law, forum, US arbitration and class-action waiver, the Québec French version — https://www.legisquebec.gouv.qc.ca/en/document/cs/P-40.1
- [ ] M-21 [infra] The North America cell: `infra/envs/prod-na` in ca-central-1 using the same `infra/platform` module; `region` stops defaulting to eu-central-1; validated and applied to LocalStack only (GOAL 12) — https://docs.aws.amazon.com/general/latest/gr/location.html
- [ ] M-22 [web]+[app] The welcome screen asks for the country (pre-selected from the device locale); the app stores the cell and uses its API host and Cognito pool; sign-in can switch region — https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-multi-region.html
- [ ] M-23 [backend] Bookings carry `market` and `entity`; a booking whose listing is in another cell is refused with a clear error; cross-market bookings inside a cell work in the listing's currency — ADR 0013
- [ ] M-24 [legal/business] US sales tax: a nexus study per state and taxability by category (equipment rental, storage and space, vans and car-sharing); Stripe Tax or Avalara registration — https://www.streamlinedsalestax.org/for-businesses/marketplace-facilitator
- [ ] M-25 [backend]+[web] US/CA checkout shows prices before tax and adds tax by the listing's address at checkout; EU/UK/CH prices stay tax-inclusive (PAngV and EU price rules) — https://docs.stripe.com/tax/tax-for-marketplaces
- [ ] M-26 [backend] 1099-K: collect a TIN (W-9) from US owners through Stripe and decide who files (`controller.fees.payer`); thresholds > $20,000 and > 200 transactions — https://docs.stripe.com/connect/tax-reporting
- [ ] M-27 [legal/business] Canada: GST/HST and QST registration for Cappy's fee; whether the distribution-platform rules catch rentals; Part XX reporting (vans, space) — https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/gst-hst-businesses/digital-economy.html
- [ ] M-28 [web]+[backend] US privacy: a notice at collection, CCPA/state rights in the privacy policy, GPC honoured (analytics off, recorded), and a "Do Not Sell or Share" link only if anything is ever sold or shared — https://cppa.ca.gov/regulations/pdf/ccpa_statute_eff_20260101.pdf
- [ ] M-29 [legal/business] Québec Law 25: name the person in charge of personal information and publish the contact; PIAs for processors outside Québec (Stripe, SES if used from the US); an incident register — https://www.cai.gouv.qc.ca/protection-renseignements-personnels/sujets-et-domaines-dinteret/principaux-changements-loi-25
- [ ] M-30 [backend] Marketing consent records (when, which text, which channel) per CASL and CAN-SPAM; `List-Unsubscribe` plus one-click unsubscribe honoured at once; a postal address in marketing mail — https://crtc.gc.ca/eng/com500/faq500.htm
- [ ] M-31 [backend] SMS, if added: transactional only by default; marketing SMS needs separate written consent; STOP handled (TCPA) — https://law.justia.com/cases/federal/appellate-courts/ca11/24-10277/24-10277-2025-01-24.html
- [ ] M-32 [backend] Phone numbers stored as E.164 with `phonenumbers`; the chat masker uses `PhoneNumberMatcher` with the market as the default region, so NANP numbers are caught (`booking/messages.py:47`) — https://github.com/daviddrysdale/python-phonenumbers
- [ ] M-33 [backend] Business identity per country: VAT ID validation for EU (VIES), GB, CH (UID), CA (BN) and US (EIN format); error text per country (`catalog/routes.py:99-115`) — https://ec.europa.eu/taxation_customs/vies/
- [ ] M-34 [backend] Notifications: Babel for money and dates in the listing's zone and the reader's locale; catalogues for every supported language (`notifications/texts.py:104-150`) — https://babel.pocoo.org/en/latest/api/numbers.html
- [ ] M-35 [backend] Seed data for every launch cell (Berlin, Vienna, Zürich, Paris, London, New York, Toronto, Montréal) in local currency, units and time zone; tests run per market — ADR 0010
- [ ] M-36 [web] Accessibility to WCAG 2.2 AA (covers EAA, ADA practice and AODA), axe in CI, an accessibility statement per region — https://www.ada.gov/resources/web-guidance/
- [ ] M-37 [legal/business] Insurance or a damage guarantee per market (van cover differs by country and US state); what the app promises changes per market — https://help.turo.com/en_us/protection-plans-in-detail-france-guests-ry6y3o962
- [ ] M-38 [backend] Minimum age per market and category (21+ for vans where rental law or the insurer requires it) — ADR 0013
- [ ] M-39 [backend] Payout and settlement currencies: platform settlement accounts in GBP, CHF, USD and CAD; transfers in the booking currency; FX shown to owners — https://docs.stripe.com/connect/currencies
- [ ] M-40 [web] Show an approximate conversion into the reader's currency, clearly labelled, when a listing's currency differs; always charge in the listing's currency — https://www.vinted.com/help/1555-us-uk-international-sales
- [ ] M-41 [app] Store listings per language (fr-CA separate in App Store Connect), availability per launch country, and a privacy label per region — https://developer.apple.com/help/app-store-connect/reference/app-information/app-store-localizations/
- [ ] M-42 [legal/business] UK: VAT registration, UK platform reporting, a UK GDPR representative (Art. 27) if Cappy has no UK establishment, and the DUAA complaints procedure — https://www.gov.uk/government/publications/reporting-rules-for-digital-platforms/reporting-rules-for-digital-platforms
- [ ] M-43 [legal/business] Switzerland: MWST registration once CHF 100k worldwide turnover is crossed and there are Swiss supplies; a Swiss representative under the FADP if required — https://www.estv.admin.ch/de/mwst-anmeldung-plattformbesteuerung
- [ ] M-44 [backend] ViDA readiness: a "deemed supplier" flag per category × market, so accommodation-like categories can be taxed as the platform's own supply from 1 Jul 2028 if they are ever added — https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=OJ%3AL_202500518
- [ ] M-45 [infra] Per-cell observability and CD: the same images deployed to both cells in turn, dashboards per cell, and a cell label on every log line — ADR 0008
