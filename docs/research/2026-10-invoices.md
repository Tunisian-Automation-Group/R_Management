# Legal invoices, credit notes and receipts (October 2026)

What Cappy must put on its invoices, in which format, and how the big apps
present them. It is the basis for `payments/invoices.py` and
`payments/invoice_doc.py`. Items marked **(counsel)** need a tax adviser or
lawyer before launch. They are also in `docs/TASKS.md`.

Sources were fetched on 2026-09-27 unless marked *(not fetched)*.

## 1. What Cappy invoices, and to whom

Cappy's own supply is **arranging the booking**. It charges owners a 15 %
fee, which sits inside the price and is withheld from the payout. The rental is
the owner's supply to the renter. So:

- **Cappy → owner: a VAT invoice for the fee.** This is what Airbnb does for its
  host service fee. Airbnb issues VAT invoices for its own fees, and hosts
  invoice their guests themselves ([Airbnb help: VAT invoices](https://www.airbnb.com/help/article/2525),
  page rendered by script; content from Airbnb's help centre).
- **Cappy → renter: a payment receipt, not an invoice.** Cappy collects the
  money for the owner. A receipt confirms what was charged and refunded. An
  owner who is a business must invoice the renter themselves.
  **(counsel)** Cappy could issue that invoice *in the name and on behalf of*
  business owners (§ 14 (2) S. 4 UStG allows a third party to issue it). That
  needs the owner's agreement in the terms, and each owner's own number series.
- **Self-billing (Gutschrift, § 14 (2) S. 5 UStG) is not needed.** Cappy pays
  owners their share of the renter's money; it doesn't buy anything from
  them. **(counsel)**: confirm the payout isn't consideration for a supply to
  Cappy under the payment-collection model.

## 2. Mandatory contents

### Germany: § 14 (4) UStG ([gesetze-im-internet.de/ustg_1980/__14.html](https://www.gesetze-im-internet.de/ustg_1980/__14.html))

1. The full name and address of the issuer **and** the recipient.
2. The issuer's tax number (Steuernummer) **or** VAT ID (USt-IdNr.).
3. The issue date.
4. A unique sequential number, in one or more series.
5. The quantity and type of the service.
6. The date of supply.
7. The net amount per tax rate.
8. The tax rate and the tax amount, or a note of the exemption.
9. For reverse charge (§ 14a (1) UStG, [__14a.html](https://www.gesetze-im-internet.de/ustg_1980/__14a.html)):
   - the words **"Steuerschuldnerschaft des Leistungsempfängers"**;
   - **both** VAT IDs;
   - issue by the 15th of the month after the supply.
10. The word "Gutschrift" if self-billed (not used).

**Small invoices** (§ 33 UStDV, [__33.html](https://www.gesetze-im-internet.de/ustdv_1980/__33.html)):
up to €250 gross, an invoice needs only the issuer's name and address, the date,
the service, and the gross amount with the rate. That rule does **not** apply to
§ 13b (reverse charge) supplies. Cappy prints every field every time: that is
always allowed, and it keeps one template.

**Business letters** (§ 35a GmbHG, § 37a HGB): a GmbH names its register court,
register number and managing directors on every business letter, invoices
included. Cappy prints them in the footer (`LEGAL_REGISTER`, `LEGAL_DIRECTORS`).

**Retention** (§ 14b (1) UStG, [__14b.html](https://www.gesetze-im-internet.de/ustg_1980/__14b.html),
and § 147 (3) AO): **eight years** since 1 January 2025 (Bürokratieentlastungsgesetz IV),
counted from the end of the year of issue. That was 10 years before. Cappy now
defaults to 8 (`INVOICE_RETENTION_YEARS`). **(counsel)**: confirm nothing else
(for example the booking records they back) must be kept longer.

**Unchangeable (GoBD):** an issued invoice is never edited. A mistake is fixed by a
correction document (a Stornorechnung or Rechnungskorrektur) with its own number,
and then a new invoice if one is due.

### Other markets

- **EU, Art. 226 VAT Directive** (2006/112/EC, [EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32006L0112)):
  - the same core list as § 14 UStG;
  - "Reverse charge" wording (Art. 226 (11a));
  - the customer's VAT ID for intra-EU B2B supplies.

  Cappy's fee to an EU business in another member state is a B2B service taxed
  where the customer is (Art. 44) and reverse-charged (Art. 196).
- **Austria, § 11 UStG 1994** ([RIS](https://www.ris.bka.gv.at/NormDokument.wxe?Abfrage=Bundesnormen&Gesetzesnummer=10004873&Paragraf=11)):
  - the same fields;
  - the recipient's UID is required above €10,000;
  - small invoices up to €400.
- **Switzerland, Art. 26 MWSTG** ([Fedlex](https://www.fedlex.admin.ch/eli/cc/2009/615/de#art_26)):
  - the name and place of both parties;
  - the supplier's UID with "MWST";
  - the date or period, the type and extent of the service, the consideration, and the rate and tax.

  A German issuer's fee to a Swiss business isn't taxable in Germany; the
  recipient pays Swiss acquisition tax (Bezugsteuer). **(counsel)** once Cappy
  has Swiss revenue.
- **UK, VAT Notice 700/21** ([GOV.UK](https://www.gov.uk/guidance/record-keeping-for-vat-notice-70021)):
  a VAT invoice has the same core items. For a B2B service to a UK business from
  abroad, the UK customer reverse-charges, and the invoice from Germany shows no
  German VAT.
- **US:** no VAT. A receipt shows what was paid, and any sales tax Cappy
  collects as a marketplace facilitator. Owners get 1099-K reporting, not
  invoices (docs/research/2026-09-multi-market.md).
- **Canada:** to support an input tax credit, the documents must show the GST/HST
  registration number and name, the date, the amount, and the tax, with more
  details at $100 and $500 ([CRA: information required](https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/gst-hst-businesses/complete-file-input-tax-credit/information-required-support-claim.html),
  *not fetched: timed out*). Québec adds the QST number.

## 3. E-invoicing: what Germany requires, and when

**The law:** § 14 (1) UStG (Wachstumschancengesetz) makes the **e-invoice** a
structured format that follows **EN 16931** the norm for B2B supplies between
German businesses. The transition is in § 27 (38) UStG:

| From | Obligation |
|---|---|
| 1 Jan 2025 | Every German business must be able to **receive** e-invoices. |
| Up to 31 Dec 2026 | Paper or PDF invoices are still allowed. |
| Up to 31 Dec 2027 | Paper or PDF still allowed for issuers with a turnover of €800,000 or less, and for existing EDI. |
| 1 Jan 2028 | Every domestic B2B invoice is an e-invoice. |

([BMF FAQ](https://www.bundesfinanzministerium.de/Content/DE/FAQ/e-rechnung.html))

**Formats:** the BMF names **XRechnung** and **ZUGFeRD from version 2.0.1**
(except the MINIMUM and BASIC-WL profiles) as valid e-invoices.

- **ZUGFeRD 2 / Factur-X** is a PDF/A-3 with the CII XML attached. It is
  readable by people and by machines ([FeRD](https://www.ferd-net.de/standards/zugferd),
  [FNFE-MPE Factur-X](https://fnfe-mpe.org/factur-x/)).
- **XRechnung** is XML only, usually for public-sector buyers
  ([XStandards Einkauf](https://xeinkauf.de/xrechnung/)).

**What Cappy does:**
- Every fee invoice is a **Factur-X, profile EN 16931**: a PDF/A-3 with
  `factur-x.xml` (CII D16B) attached.
- The XML is checked against the Factur-X XSD and the EN 16931 schematron, both
  at issue and in the tests, with the `factur-x` library 6.8.
- The same XML can be downloaded on its own (`.xml`).
- That already meets the 2028 rule for business owners. Private owners get the
  same PDF; e-invoice rules don't apply to them.

**Not verified:**
- **PDF/A-3 conformance** with veraPDF. The base PDF embeds all fonts, and the
  library writes the PDF/A XMP and the attachment relationship, but no veraPDF
  run was possible. Run veraPDF once in CI before launch (task in TASKS).
- **An XRechnung CIUS validation** with the KoSIT validator (BR-DE rules such as
  the buyer reference and the seller's contact). Cappy's XML follows EN 16931. If
  a public-sector buyer ever needs XRechnung, add the BR-DE fields.

## 4. How the big apps present invoices and receipts

- **[Stripe invoices](https://docs.stripe.com/invoicing/customize) and [receipts](https://docs.stripe.com/receipts):**
  - the brand logo top left, the document name and number top right;
  - a summary block with the amount and its status ("Paid", the date);
  - "Bill to" and "From" side by side;
  - line items (description, qty, unit, amount), then subtotal, tax per rate and total;
  - the legal footer with the tax ID, and a "Download PDF" link.

  This is Cappy's layout.
- **Airbnb:** separate VAT invoices for its own fees and a trip receipt with the
  price breakdown. The fee is its own document, not mixed into the rental.
  Cappy does the same: the fee invoice for owners, the receipt for renters.
- **Uber:** each trip gets a receipt, and in the EU a separate VAT invoice for
  the service fee, issued by Uber for itself or on the driver's behalf
  (*not fetched*: help.uber.com answered 404).
- **Apple and App Store** ([support](https://support.apple.com/en-us/118212)):
  a minimal receipt: the order ID, the date, the item, the price, tax included,
  and the seller entity named at the bottom.
- **Amazon:** the seller entity named per invoice, with the VAT per rate, and
  credit notes as separate numbered documents (*not fetched*).

**What Cappy took from them:**
- one status pill ("Paid");
- the amount as the largest figure;
- the tax block in the same place every time;
- every legal detail in the footer, not scattered;
- the document number as the file name;
- plain words, in the reader's language (EN, DE or FR);
- A4, or US Letter for US and Canadian readers.

**Accessibility:** the PDF has a real text layer and a title and language in its
metadata. Tagged PDF (PDF/UA) isn't done: reportlab has no tagging. The HTML
invoice page is the accessible version, with the same facts.

## 5. What is built (branch `feat/invoices`)

- **Fee invoice (Cappy → owner):**
  - every § 14 (4) field, plus the register, directors and contact email;
  - the issuer is **copied onto the invoice at issue**;
  - the recipient's VAT ID sets the tax:
    - domestic VAT;
    - reverse charge for an EU business in another member state, with the § 14a wording and both VAT IDs;
    - not taxable in Germany for a Swiss or UK business.
- **PDF (Factur-X / ZUGFeRD 2, EN 16931):**
  - rendered once on first download, then stored with its SHA-256;
  - served byte for byte ever after, whatever the settings or the reader's language.
- **XML:** the EN 16931 CII on its own.
- **Credit notes:**
  - issued by staff, one per invoice, from their own series (`CAP-<year>-G…`), type 381;
  - they reference the corrected invoice and carry the reason;
  - PDF and XML are the same as for invoices.
- **Renter receipt:** a PDF of what was charged, refunded and paid, with Cappy's
  fee inside it, clearly "not a tax invoice".
- **Endpoints:**
  - `/api/payments/invoices/{number}.pdf|.xml` for the owner;
  - `/api/payments/credit-notes/{number}.pdf` for the owner;
  - `/api/payments/receipts/{bookingId}.pdf` for the renter;
  - `/api/admin/payments/invoices/{number}.pdf` and `…/credit-note` for staff.
- **Logo and fonts:**
  - the logo is the Cappy wordmark as vector paths (`payments/assets/logo.svg`, `web/public/logo.svg`);
  - fonts are embedded: Archivo and Bodoni Moda, OFL (`payments/assets/fonts/OFL.txt`).

## 6. Open questions **(counsel)**

1. **VAT for private owners in other EU states.** Is the fee to a private owner
   in Austria an electronically supplied service taxed in Austria through OSS
   (Art. 58 VAT Directive), or a service taxed where the supplier is (Art. 45)?
   Today: German VAT for every private owner.
2. **Invoicing the rental for business owners.** Should Cappy issue it on their
   behalf (§ 14 (2) S. 4 UStG), with an agreement in the terms and each owner's
   own series?
3. **Payment-collection model.** Confirm the payout to owners is not
   consideration for a supply to Cappy, so no Gutschrift is needed.
4. **Retention.** Eight years for invoices under § 14b; do the booking records
   behind them need longer?
5. **Swiss revenue.** When does Cappy need a Swiss VAT registration (the
   CHF 100,000 worldwide turnover threshold for foreign platforms)?
6. **Canada and US.** The GST/HST and QST registration numbers and the receipt
   contents once the North America cell exists.
