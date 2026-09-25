# 0013. Markets and regional cells

Status: proposed

## Context
Cappy was built for Germany: every price is EUR, every fee carries 19 %
German VAT, every place is a Berlin-style district, every time is Berlin
time, the legal pages are German, there is one Stripe platform account (DE)
and all data lives in eu-central-1. GOAL.md item 16 makes the target all of
Europe, the United States and Canada. The research is in
[`../research/2026-09-multi-market.md`](../research/2026-09-multi-market.md).

Three facts shape the design:
- **Money and tax are per country.** Currency, tax on the fee, platform
  reporting (DAC7, UK, 1099-K, Canada Part XX), consumer law and the
  contracting entity all follow the country, and in the US and Canada the
  state or province as well.
- **Stripe accounts are per legal entity and region.** A European platform
  cannot give US or Canadian owners full Connect accounts; the US and Canada
  need a North American entity with its own Stripe platform account.
- **The law does not require data to stay in a country**, but EU users
  expect EU hosting, Québec's Law 25 requires an assessment before personal
  information leaves Québec, and North American users are 90-150 ms from
  Frankfurt on every request.

## Decision
1. **A market is a country** (ISO 3166-1 alpha-2). Markets are configuration
   in `cappy_common` (one JSON file, also bundled into the web build), not a
   table: changing one needs a legal review and a deploy anyway. Each market
   has: `currency`, `cell`, `entity` (the contracting legal entity),
   `stripePlatform`, `languages` and `defaultLocale`, `distanceUnit`
   (`km`/`mi`), `pricesIncludeTax`, `taxRegime`, `reporting` (DAC7, UK, US,
   CA), `consumerLaw` (EU withdrawal right, UK CCR, Québec CPA, none),
   `feeBps`, `minAge`, and `status` (`planned`, `beta`, `live`). The
   state or province matters only for tax, and comes from the listing's
   address, not from the market.
2. **Two regional cells**, each a full copy of today's stack (the
   `infra/platform` module applied once per cell, its own Aurora cluster,
   Cognito user pool, SES, SNS/SQS, S3 and Stripe secrets):
   - **EU cell, eu-central-1**: the EEA, Switzerland and the UK; entity
     Cappy GmbH (DE); Stripe platform DE.
   - **North America cell, ca-central-1**: the US and Canada; a North
     American entity (a US corporation, **[legal/business]**); Stripe
     platform US. Montréal is ~10 ms from us-east-1, so US users lose
     nothing, and Canadian (and Québec) data stays in Canada.
   Nothing is replicated between cells. The only global pieces are the static
   web bundle, the market configuration and DNS.
3. **Where things belong.**
   - A **person** belongs to one cell, chosen at sign-up from their country of
     residence; their home market is that country. The app remembers the cell
     and talks to `https://<cell>.api.<domain>`; the sign-in screen offers the
     other region. An owner's Stripe connected account is created in their
     country of residence on their cell's platform.
   - A **listing** gets its market from the country of its geocoded address,
     fixed once it has a booking. Its time zone comes from the same point.
   - A **booking** gets the listing's market: its currency, tax rules,
     consumer law and contracting entity. Prices are charged in the listing's
     currency and never converted silently; an approximate conversion may be
     shown, labelled as such.
4. **Cross-market bookings are allowed inside a cell** (a Berlin renter books
   a Paris workshop, a Toronto renter books in Buffalo): the same Stripe
   platform can charge in the listing's currency and pay the owner.
   **Across cells they are not, at first**: a Berlin member visiting New York
   creates a North America account. That keeps every booking, payment and
   message inside one database and one Stripe platform.
5. **Places are points.** Listings and search origins are latitude/longitude
   with PostGIS (`geography(Point)`, GiST index, `ST_DWithin`); districts
   become display labels. Addresses are structured per country and geocoded
   with Amazon Location Service in each cell.

## Rejected
- *One global dataset in eu-central-1.* The least work, and lawful with the
  EU-US Data Privacy Framework and a Québec transfer assessment. But every
  North American request crosses the Atlantic, one Stripe platform still
  cannot serve US and Canadian owners, and "your data stays in the EU" is a
  promise European users and business owners ask for.
- *A cell per country (or US and Canada apart).* Every cell is a copy of the
  whole stack to run, patch and pay for. No target country requires its own
  cell for a private marketplace; add one only if a law or a partner does.
- *Aurora Global Database / DynamoDB global tables.* They copy every row to
  every region, which is the opposite of keeping each market's data at home,
  and they do nothing for the Stripe split.
- *Markets as a database table edited by staff.* A new market changes tax,
  legal text and payments; it is a reviewed change, not a form.
- *H3 or geohash cells instead of PostGIS.* Useful for aggregates (heat maps,
  "idle nearby" counts); for radius search PostGIS on the Aurora cluster we
  already run is less code.

## Consequences
- Money everywhere carries a currency; code that adds amounts across
  currencies is a bug the types should catch.
- Tax on the fee becomes a decision per invoice line (Stripe Tax, or a rules
  table per market), and the invoice template is per entity and language.
- Two Cognito pools: a person with accounts in both cells has two accounts,
  and support has to look in both. A global directory of hashed emails is the
  upgrade path if that becomes common.
- Operations double: two cells to deploy, migrate, alarm and pay for. The CD
  pipeline deploys the same images to both, cell by cell.
- The web and apps are one build; the market configuration and the language
  catalogues decide what each user sees.
- Launch is per market: a market goes `live` only when its legal, tax and
  payment items in the research checklist are done.
