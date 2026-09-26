# What an EU rental marketplace needs at launch (2026-09)

This is research, not legal advice. Items marked **(counsel)** need a
German Rechtsanwalt or Steuerberater. Tasks are in [`../TASKS.md`](../TASKS.md)
(G-nn).

## Findings that change the scope
- **DAC7** (PStTG in Germany, reported to the BZSt) covers rental of
  immovable property (workshop and storage space) and of **transport**
  (vans), with no minimum threshold. Rental of other movable equipment
  (machines, 3D printers) is **out of scope** unless a service comes with it.
  The data has to be collected all year; the report is due by 31 Jan (DE: 2 Feb).
  Stripe Connect platform tax reporting collects the data and prepares the
  files. https://docs.stripe.com/connect/platform-tax-reporting ·
  https://www.bzst.de/DE/Unternehmen/Intern_Informationsaustausch/DAC7/dac7_node.html
- **Digital Services Act**: micro and small enterprises are exempt from
  Sections 3 and 4 (complaints system, trusted flaggers, KYBC trader
  traceability) until 12 months after they outgrow that size. **Articles
  11–18 apply from day one**: contact points, moderation terms, a
  notice-and-action form (Art. 16), and a statement of reasons for every
  removal, suspension or payout block (Art. 17).
  https://dsa-library.com/article/16/ · https://dsa-library.com/article/17/
- **Consumer law**:
  - Headline prices include the platform fee (PAngV).
  - The pay button reads "zahlungspflichtig buchen" (§312j BGB).
  - Each owner is labelled trader or private (Omnibus).
  - Say how reviews are verified.
  - Withdrawal information, and the **withdrawal button (Art. 11a CRD),
    mandatory since 19 June 2026**.
  - The EU ODR platform closed on 20 July 2025: remove the link.
  https://www.gesetze-im-internet.de/bgb/__312j.html ·
  https://www.freshfields.com/en/our-thinking/blogs/risk-and-compliance/pitfalls-for-e-commerce-how-the-new-eu-withdrawal-button-widerrufsbutton-wi-102ms91
- **P2B**: 15 days' notice of terms changes, reasons for any restriction,
  and the main ranking parameters published.
  https://eur-lex.europa.eu/eli/reg/2019/1150/oj/eng
- **VAT on the fee**: 19% for German business owners; reverse charge for
  other EU business owners; for private owners, likely OSS at their
  country's rate **(counsel)**. Fee invoices need the Art. 226 content;
  domestic B2B e-invoices (XRechnung or ZUGFeRD) from 2027/28.
- **European Accessibility Act (BFSG)**: e-commerce is in scope;
  micro-enterprises are exempt until they cross 10 staff or €2M. Build to
  WCAG 2.1 AA now.
- **App stores** (Apple 1.2, Google UGC): in-app **report and block** for
  user content, filtering, and published contacts. Without them the apps
  are rejected.
  https://developer.apple.com/app-store/review/guidelines/
- **Insurance**: German private liability usually **excludes rented items**.
  Getaround DE requires its Allianz policy, and Fat Llama runs a guarantee
  that needs photos 24 h before and after. A partner insurer or guarantee
  is a business decision to make before launch, and vans need it most.
- **Card holds** expire after 5–7 days: Cappy's holds last at most 24 h
  (accept or lapse), so this is already safe.

## Product gaps (from Airbnb, Turo, Fat Llama, Getaround, Vinted)
In-app messaging with contact details masked until a booking is accepted (and
report/block); two-way blind reviews; renter identity verification (Stripe
Identity) for high-value items and vans; damage protection (card saved for
an off-session damage charge, a claims flow); **check-in and check-out photos**
as evidence; owner-selectable cancellation policies; instant book;
duration discounts; published ranking; German localisation; a help centre
with per-booking "report a problem"; basic fraud rules and a review queue.

## Operations gaps
An admin console (moderation, bans with an Art. 17 statement of reasons,
refunds, payout pause, dispute resolution, all audited); product analytics
from server events (no consent needed); feature flags; email stream
separation and one-click unsubscribe; a helpdesk.
