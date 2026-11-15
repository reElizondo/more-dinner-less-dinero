# More Dinner, Less Dinero

Plans the weekly grocery order across **Walmart** and **H-E-B** curbside pickup.

Each week it:

1. Collects recurring items that are due (every item has its own schedule).
2. Adds non-due items that are on sale and worth stocking up on.
3. Compares prices at both stores and splits the order the cheapest way, after
   accounting for pickup minimums/fees and the cost of a second stop.
4. Shows the two proposed lists for approval.
5. Gives you a Walmart add-to-cart link and an H-E-B list with product links.
   **Checkout and pickup-slot selection are done by hand**; the app never logs
   in to a store, places orders or touches payment.

Status: **Phase 1** — Walmart API client works on sandbox; production key
blocked on Walmart's side. See [Current status](#current-status).

---

## Current status

_Last updated 2026-11-14._

**Walmart API (walmart.io)**

- Signing works: a search against the **sandbox** (`environment: "stage"`)
  returned HTTP 200 with no error. The sandbox returned no products, which is
  normal for a test environment.
- Two walmart.io applications exist:
  - `more-dinner-less-dinero` (Web Application): **sandbox** consumer ID
    `f65b8b7e-ea47-4eca-8b16-618e89509499`, key version 1, key
    `keys/walmart_private_key.pem`.
  - `mas-dinner-less-dinero` (Desktop Application): created for **production**.
- Walmart rejects reusing the sandbox public key for production, so production
  has its own pair: `keys/walmart_prod_private_key.pem` /
  `keys/walmart_prod_public_key.pem`.
- **Blocker:** uploading the production public key shows a 503 error
  (`addPublicKey ... status code 503`). The network response did return a prod
  consumer ID `c027eede-d237-436e-bbd5-45cef7f7c400`, but the dashboard doesn't
  show it and the API answers `401 Public Key not found for Consumer id`. The
  key never got attached.
- Retried 2026-11-14 on `mas-dinner-less-dinero`, environment PRODUCTION:
  `POST /addPublicKey` returns HTTP 200 with body `{"status":412}`, and the
  dashboard still shows no prod consumer ID. A brand-new key pair
  (`keys/walmart_prod2_*.pem`) got the same 412, so the key isn't the problem;
  the app's production setup looks stuck after the first 503. The API still
  answers `401 Public Key not found` for `c027eede-…`.
- Adding production to the other app, `more-dinner-less-dinero` (new key
  pair), also returned `{"status":412}`. The 412 affects the whole account,
  not one app: walmart.io seems to require something before it grants
  production at all, probably affiliate approval (still waiting on
  affilops@wal-mart.com).
- Next: contact walmart.io support with the 412 details and ask what
  production requires; follow up with the affiliate team. Use
  `keys/walmart_prod2_*.pem` for the next attempt.
- Permission for this personal use was requested by email from Walmart's
  affiliate team (affilops@wal-mart.com); no reply yet.
- Not yet verified: whether a multi-item cart link (`items=id|qty,id`) works.

**Next up**

1. Get the production key working, then run a real search and lookup.
2. Fill in quantities and sizes in `data/items.yaml` as needed (schedules
   start weekly; see [Weekly schedule](#weekly-schedule)).
3. Onboarding: match items to Walmart products and record H-E-B products and
   prices, stored in SQLite.

## Phase 0 results: browser automation is out

The first plan was to drive both store websites with Playwright. Both blocked it:

- **Walmart:** endless "verify you're human" challenge at login.
- **H-E-B:** request blocked by its security service (error 15) at login.

Both sites actively block automated browsers. Getting around that would mean
evading their bot detection, which is fragile, risks the accounts, and is a
dead end for a public version. So the app does not automate either website.

## Data sources

### Walmart: Affiliate API (walmart.io)

- **Search** the catalog, and **look up** live price and availability for up
  to 20 items per call, priced for a zip code. 5,000 calls/day.
- Gives `salePrice`, `msrp` and a `clearance` flag, which drive the stock-up
  suggestions.
- **Cart links:** `affil.walmart.com/cart/addToCart?items=<id>` adds an item
  to the Walmart.com cart. The multi-item form (`id|qty,id|qty`) is not yet
  verified.
- Exact per-store pricing (`storeId`) needs extra approval from Walmart; zip
  pricing is used until then.

**Terms:** Walmart's API terms limit the API to affiliate partners advertising
Walmart.com products; other uses need Walmart's written permission. Permission
for this personal use has been requested from Walmart's affiliate team. The
API terms also restrict emails that contain Walmart product data or links
without permission, which matters for the planned email interface. A public
version would most likely go through the affiliate program properly.

### H-E-B: no API

No public API, automation blocked, and Instacart's developer platform accepts
only product names, can't target a store and doesn't return prices. Plan:

1. **Stored prices:** keep a last-known price per item and ask the user to
   confirm only the close calls each week.
2. **Later:** H-E-B weekly ad / digital coupons for sales, and receipts to keep
   stored prices current.

## Design decisions

| Topic | Decision |
|---|---|
| Language | Python 3.12+ |
| Walmart prices | Affiliate API, signed requests (`src/more_dinner_less_dinero/walmart.py`) |
| H-E-B prices | Stored prices with weekly confirmation of close calls |
| Item list | Google Sheet → imported into the app |
| AI | Anthropic Claude for cross-store product matching, size normalization and stock-up suggestions |
| Math | Prices, unit prices and the split are deterministic code, not AI |
| Interface (v1) | Command line |
| Runs on | A laptop, run by hand |
| Fulfillment | Curbside pickup at both stores |

### Brand handling

Brands are flexible. Each item is a category with rules, for example
"2% milk, 1 gallon, any brand, avoid brand X". The AI judges which products are
equivalent; the code picks the cheapest acceptable option by unit price. After
a match is approved, the product is **pinned** (a Walmart item ID; an H-E-B
product link and price) so weekly runs don't re-match.

### Split logic

- Cheapest store per item by unit price.
- Respect each store's pickup minimum and fee (in config, because they change).
- Only split across two stores if the savings exceed a configurable
  **second-stop cost**. Otherwise everything goes to the cheaper store overall.

### Stock-up suggestions

Only for items flagged as keeping well (pantry, frozen, household), and only
when the discount is above a threshold.

---

## Roadmap

### Phase 1 — Data and onboarding (current)

- [x] Walmart API client: signing, search, lookup, cart links
- [x] Verify signing against the sandbox API
- [ ] Get the production key attached and run a live search
- [ ] Test whether a multi-item cart link works
- [x] Import the item list from the Google Sheet (names, categories, meals)
- [ ] Onboarding: match each item to a Walmart product (AI-assisted, you
      approve) and record its H-E-B product and price; store in SQLite

### Phase 2 — Weekly run

1. Select due items plus stock-up candidates.
2. Live Walmart prices; stored H-E-B prices, confirming close calls.
3. Optimize the split.
4. Print both lists with totals, savings and suggestions.
5. Output the Walmart cart link and the H-E-B list with links.

### Phase 3 — Later

- Email or text delivery (subject to Walmart's terms on electronic
  communications).
- H-E-B weekly ad and receipt import.
- Scheduled runs; multiple users.

---

## Getting started

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

### Walmart API keys

1. At [walmart.io](https://walmart.io), log in with your regular Walmart
   account ("Login with Walmart") and create an application.
2. Generate a key pair in the project folder:

   ```bash
   mkdir -p keys
   openssl genrsa -out keys/walmart_private_key.pem 2048
   openssl rsa -in keys/walmart_private_key.pem -pubout -out keys/walmart_public_key.pem
   ```

3. Upload **only the public key** (`walmart_public_key.pem`) in the walmart.io
   dashboard. You'll get a consumer ID. The private key never leaves your
   laptop; `keys/` and `*.pem` are git-ignored.
4. Copy `config/settings.example.yaml` to `config/settings.yaml` and fill in
   the environment (`prod` or `stage`, matching the consumer ID), consumer ID,
   key version (usually `1`), private key path and your zip code.

Notes from setup:

- Production and sandbox need **different** key pairs; walmart.io rejects
  reusing one.
- The walmart.io page can show an error even when part of the upload
  succeeded. Check the browser's network response, and verify which private
  key matches what you uploaded with
  `openssl rsa -in <private_key>.pem -pubout`.

### Import the item list

The "Grocery Essentials" Google Sheet has one column per category (Fridge,
Pantry, Snacks, Cosmetic, Meat, Spices) with item names below. A block that
follows a blank gap in a column (currently the meals under Cosmetic) is
imported as `meals`.

```bash
python scripts/import_sheet.py --sheet-url "<sheet link>"
```

This writes `data/items.yaml` (git-ignored). The sheet only has names, so
schedules, quantities, sizes and brand rules are set in that file; re-running
the import keeps them, adds new sheet items and reports removed ones. Every
item starts at `every_weeks: 1`.

### Weekly schedule

Everything starts **every week**. An item is due once `every_weeks` weeks have
passed since it was last bought. At the start of each week, anything you
**still have** is skipped that week and its interval grows by one week
(1 → 2, 2 → 3, ...), so it comes up again at the new interval counted from
when it was last bought.

```bash
python scripts/week.py due                     # what's due this week
python scripts/week.py have milk "egg whites"  # still have these
python scripts/week.py ordered --due           # bought everything due
```

Names match exactly or by a unique part ("thighs" → Chicken Thighs). If the
sheet isn't link-shared, download it as CSV and use `--csv <file>`.

### Try it

```bash
python scripts/walmart_try.py search "great value 2% milk gallon"
python scripts/walmart_try.py lookup <itemId> <itemId>
python scripts/walmart_try.py cart <itemId>:2 <itemId>
```

## Repository layout

```
config/settings.example.yaml          API settings, store fees, thresholds
data/items.example.yaml               example item list format
scripts/import_sheet.py               import the item list from the Google Sheet
scripts/week.py                       weekly schedule: due, still have, ordered
scripts/walmart_try.py                try the Walmart API from the command line
src/more_dinner_less_dinero/items.py    sheet import and weekly schedule
src/more_dinner_less_dinero/walmart.py  Walmart Affiliate API client
tests/                                unit tests
```
