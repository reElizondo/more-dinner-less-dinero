# More Dinner, Less Dinero

Plans the weekly grocery order across **Walmart** and **H-E-B** curbside pickup.

Each week it:

1. Collects recurring items that are due (every item has its own schedule).
2. Adds non-due items that are on sale and worth stocking up on.
3. Compares prices at both stores and splits the order the cheapest way, after
   accounting for pickup minimums/fees and the cost of a second stop.
4. Shows the two proposed lists for approval.
5. After approval, fills both carts. **Checkout and pickup-slot selection are
   done by hand**; the app never places orders or touches payment.

Status: **Phase 0 (feasibility check)** — see [Phase 0](#phase-0--feasibility-check-current).

---

## Key constraints

- **No official APIs.** Neither store offers a public API for searching prices
  and filling a customer's cart. The app uses browser automation (Playwright)
  against the normal websites.
- **Bot detection.** Walmart in particular uses strong bot detection. The app
  runs in a visible browser, from a home connection, at a human pace, with a
  saved logged-in browser profile.
- **Terms of service.** Automating a personal account is a gray area. That is
  acceptable for personal use, but a public version needs a different approach
  (see [Later](#phase-3--later)).
- **No stored passwords.** You log in by hand once in the app's browser
  profile, and the session cookies stay in a local folder that is not
  committed (`.profiles/`).

## Design decisions

| Topic | Decision |
|---|---|
| Language | Python 3.12+ |
| Browser automation | Playwright with a persistent profile per store |
| Data | Item list imported from Google Sheets → YAML/SQLite |
| AI | Anthropic Claude for cross-store product matching, size normalization and stock-up suggestions |
| Math | Prices, unit prices and the order split are plain deterministic code, not AI |
| Interface (v1) | Command line (Typer) |
| Runs on | A laptop, run by hand |
| Fulfillment | Curbside pickup at both stores |

### Brand handling

Brands are flexible. Each item is a category with rules, for example
"2% milk, 1 gallon, any brand, avoid brand X". The AI judges which products are
equivalent; the code then picks the cheapest acceptable option by unit price.
After a match is approved, the product ID at each store is **pinned**, so later
runs check that product page directly instead of searching.

### Split logic

- Choose the cheapest store per item by unit price.
- Respect each store's pickup minimum and fee (in config, because they change).
- Only split across two stores if the savings exceed a configurable
  **second-stop cost** (for example $5). Otherwise put everything at the
  store with the lowest total.
- H-E-B prices depend on the selected store, so your store must be set.

### Stock-up suggestions

Only for items flagged as keeping well (pantry, frozen, household), and only
when the discount is above a threshold.

---

## Roadmap

### Phase 0 — Feasibility check (current)

Prove the browser automation works on both sites before building anything else.
For each store:

- [ ] Open a persistent browser profile and log in by hand; confirm the session
      survives a restart of the script.
- [ ] (H-E-B) Confirm the selected store is your pickup store.
- [ ] Search for one item and read the name, price, and unit price of the
      results.
- [ ] Open a product page by URL and read its price (the pinned-product path).
- [ ] Add one item to the cart, then remove it.
- [ ] Note any bot-detection challenges (captchas, "press and hold", blocks).

Run it with `scripts/phase0_probe.py` (see [Getting started](#getting-started)).
**Exit criteria:** all boxes checked for both stores, or a clear finding that one
store can't be automated (which changes the plan).

### Phase 1 — Data and onboarding

- Import the item list from the Google Sheet (export as CSV to start; the
  Sheets API later).
- Item fields: name, quantity, schedule (every N weeks), last bought,
  avoid-brands, keeps-well flag.
- An onboarding command that matches each item to products at both stores with
  AI help, asks for approval, and pins product IDs in SQLite. Runs in batches,
  since there are about 100 items.

### Phase 2 — Weekly run

1. Select due items plus stock-up candidates.
2. Fetch prices from pinned product pages (fall back to search if a product is
   gone).
3. Optimize the split.
4. Print both lists with totals, savings, and suggestions; ask for approval.
5. Fill both carts.

### Phase 3 — Later

- Email confirmation with a link to a simple approval page.
- Scheduled runs.
- Multiple users. For a public version, a browser extension that runs in the
  user's own logged-in browser avoids handling credentials and fits the
  terms-of-service risk better than server-side automation.

---

## Getting started

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
playwright install chromium
```

Phase 0 probe:

```bash
# 1. Log in by hand (once per store). Close the browser window when done.
python scripts/phase0_probe.py login walmart
python scripts/phase0_probe.py login heb

# 2. Search an item and capture results (screenshot + HTML saved to probe-output/)
python scripts/phase0_probe.py search walmart "2% milk gallon"
python scripts/phase0_probe.py search heb "2% milk gallon"

# 3. Open a specific product page
python scripts/phase0_probe.py product walmart "<product url>"
```

The page selectors in the probe are starting guesses. Both sites change their
markup, so expect to adjust them using the saved HTML and screenshots. That
discovery is the point of Phase 0.

## Repository layout

```
config/settings.example.yaml   store fees, minimums, thresholds
data/items.example.yaml        example item list format
scripts/phase0_probe.py        Phase 0 feasibility probe
src/more_dinner_less_dinero/          application package (Phase 1+)
```
