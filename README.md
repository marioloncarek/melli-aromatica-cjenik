# Shopify price compliance kit (Croatia)

**Anchor price (sidrena cijena) + daily machine-readable price list (cjenik) for Shopify stores**

This kit makes a Shopify store meet two Croatian price-control obligations in force from **1 October 2026**, using
only free tools: Shopify Flow, the store's own theme, and GitHub (Actions + Pages).

It is built to be **reusable and plug-and-play**: the code is identical for every store. Each store only needs
its own `config.json`, the metafield definitions, three Flows, one theme template and one snippet.

> This README is the complete manual, from an empty store to a fully running setup. Follow it top to bottom for
> every new store. Nothing here needs to be changed in code.

---

## Contents

0. [What the kit does](#0-what-the-kit-does)
1. [The legal requirements in short](#1-the-legal-requirements-in-short)
2. [Supported setup: read this first](#2-supported-setup-read-this-first)
3. [Setup, step by step (per store)](#3-setup-step-by-step-per-store)
   - [Step 0: Get the kit on your computer](#step-0-get-the-kit-on-your-computer)
   - [Step 1: Back up the products](#step-1-back-up-the-products)
   - [Step 2: Audit and clean compare-at prices](#step-2-audit-and-clean-compare-at-prices)
   - [Step 3: Create the metafield definitions](#step-3-create-the-metafield-definitions)
   - [Step 4: Flow 1: "Anchor price – backfill"](#step-4-flow-1-anchor-price--backfill)
   - [Step 5: Flow 2: "Anchor price – reset on new variant"](#step-5-flow-2-anchor-price--reset-on-new-variant)
   - [Step 6: Flow 3: "Anchor price – reset on new product"](#step-6-flow-3-anchor-price--reset-on-new-product)
   - [Step 7: Verify the anchor prices](#step-7-verify-the-anchor-prices)
   - [Step 8: Show the anchor price on the storefront](#step-8-show-the-anchor-price-on-the-storefront)
   - [Step 9: Install the price list theme template](#step-9-install-the-price-list-theme-template)
   - [Step 10: Create the store's GitHub repository](#step-10-create-the-stores-github-repository)
   - [Step 11: Custom domain (optional)](#step-11-custom-domain-optional)
   - [Step 12: The "Cjenik" page in the store](#step-12-the-cjenik-page-in-the-store)
   - [Step 13: Go live](#step-13-go-live)
4. [Daily operation](#4-daily-operation)
5. [When something goes wrong (runbook)](#5-when-something-goes-wrong-runbook)
6. [Configuration reference (`config.json`)](#6-configuration-reference-configjson)
7. [File names, numbering and archive](#7-file-names-numbering-and-archive)
8. [Maintenance and updates](#8-maintenance-and-updates)
9. [Per-store checklist](#9-per-store-checklist)
10. [FAQ](#10-faq)

---

## 0. What the kit does

```
 SHOPIFY ADMIN                              THEME (published)                      GITHUB (this repo)
 ─────────────                              ─────────────────                      ──────────────────
 Variant metafields                         snippets/anchor-price.liquid           .github/workflows/price-list.yml
   pricing.anchor_price       ─────────►      "Sidrena cijena na dan                  runs every morning (≈04:17)
   pricing.anchor_price_date                   10. 9. 2026.: 62,00 €"                    │
        ▲                                     (next to the price)                        │ fetches page 1 … N
        │ fills empty values                                                             ▼
 Flow 1 "Anchor price – backfill"           templates/collection.price-list.liquid ◄── /collections/all?view=price-list&page=N
   (hourly, 100 products per run)             CSV, 250 products per page,           checks every page and the totals,
 Flow 2 "… reset on new variant"              '#meta' control line per page         builds CSV + XML, names the files,
 Flow 3 "… reset on new product"                                                    keeps ≥ 30 days of archive
   (duplicates get their own values)                                                     │
                                                                                         ▼
 Page "Cjenik" (footer link) ─────────────────────────────────────────────────────►  GitHub Pages: index + files + latest.csv/.xml
```

**Repository contents**

| Path | What it is |
|---|---|
| `config.json` | The **only** file you edit per store (store details, go-live date). |
| `scripts/build_price_list.py` | Fetches, checks and publishes the price list. Python standard library only. |
| `scripts/audit_compare_at.py` | Checks a Shopify products export for misused compare-at prices (step 2). |
| `.github/workflows/price-list.yml` | Daily schedule (main run + three backups), manual runs, GitHub Pages deployment. |
| `.github/workflows/tests.yml` | Runs the automated tests when code changes. |
| `shopify/templates/collection.price-list.liquid` | Theme template that outputs the price list as CSV (step 9). |
| `shopify/snippets/anchor-price.liquid` | Theme snippet that shows the anchor price next to the price (step 8). |
| `shopify/anchor-price-display-brief.md` | Complete task brief for Claude Code to integrate the snippet into a custom theme (step 8). |
| `shopify/flows/` | Put your exported `.flow` files here (steps 4–6). Empty until your first export. |
| `site/` | Created by the workflow: what GitHub Pages publishes (index, archive, latest files). Never edit by hand. |
| `tests/` | Automated tests with a fake Shopify storefront (paging, 1,000+ products, failures, naming, archive). |

---

## 1. The legal requirements in short

> Not legal advice. Summary of the published texts as of September 2026; check the sources for changes.

### 1.1 Anchor price: *Odluka o isticanju dodatne cijene kao mjera izravne kontrole cijena* (NN 101/2026-1212)

- From **1 October 2026**, next to the current retail price, the trader shows an additional price. The decision
  calls it *dodatna cijena*; everyone calls it the **sidrena cijena** (anchor price).
- **Value:** the retail price on the **reference date 10 September 2026**.
  - Products first listed **after** 10 September 2026: the **first listing price**, with a clear date.
  - Products on a **temporary sale** on 10 September 2026: the **regular price before the sale**, not the sale
    price (Ministry clarification of 22 September 2026).
- **How:** *"jasno, vidljivo i čitljivo uz maloprodajnu cijenu"*: clearly, visibly, legibly, next to the retail
  price. It also applies to advertising in digital forms, including websites.
- The decision does not prescribe the label text. The kit uses: `Sidrena cijena na dan 10. 9. 2026.: 62,00 €`.

### 1.2 Price list: *Odluka o objavi cjenika proizvoda i usluga kao mjeri izravne kontrole cijena* (NN 101/2026-1213)

- A webshop publishes a **separate** price list file for the webshop, in **.csv or .xml** (the kit publishes both).
- Required data per product: **naziv, šifra, marka, jedinica mjere** (if applicable), **cijena za jedinicu mjere**
  (if applicable), **maloprodajna cijena** plus whether it applies **during a special form of sale** together with
  **the name of that form**, **sidrena cijena**, **barkod**, **dostupno / nedostupno**.
- **Updated once a day, by 08:00 for the current working day.** The kit publishes every day at about 04:17.
- **Archive:** published price lists stay available for **at least 30 days**. The kit keeps 60 by default, and
  never fewer than 31.
- **File name order** (Ministry clarification): *oblik prodajnog objekta_adresa_oznaka_broj pohrane_datum i vrijeme*.
  The Ministry's example is `prodavaonica_Ilica 150 Zagreb_P01_104_01.10.2026_07:45`. The kit writes the URL-safe
  equivalent: `internetska-trgovina_Ilica-150-Zagreb_WEB01_104_01.10.2026_07.45.csv`.
- **Machine access:** automated programs must be able to download the files. The kit publishes plain static files,
  including the stable `latest.csv` / `latest.xml` and a `manifest.json` list. Nothing is blocked.

### 1.3 What the kit covers

| Requirement | Covered by |
|---|---|
| Anchor price value for every variant | Flow 1 fills `pricing.anchor_price` + `pricing.anchor_price_date` (step 4) |
| Anchor price for new products, variants, duplicates, drafts published later | Flow 1 hourly; Flows 2 and 3 re-open products (steps 5–6) |
| Anchor price shown next to the price | `shopify/snippets/anchor-price.liquid` + brief (step 8) |
| Price list data | `shopify/templates/collection.price-list.liquid` (step 9) |
| Daily publication by 08:00, .csv + .xml, file naming, ≥ 30 days archive, machine access | GitHub workflow + script (step 10) |
| Public link from the store | Page "Cjenik" + footer link (step 12) |

**Not covered:** the rules for announcing price reductions (lowest price in the last 30 days); physical shops;
services. These are separate obligations.

---

## 2. Supported setup: read this first

The kit supports **one** standard way of using Shopify prices. A store that works differently has to clean its
data first (step 2). The code has no exceptions, modes or per-store logic.

| Area | Requirement |
|---|---|
| **Price model** | `Price` = what the customer pays today. `Compare-at price` = set **only** during a real, temporary sale, and holds the regular price before the reduction. **Compare-at above price means the product is on sale.** |
| **Compare-at misuse** | Not supported: compare-at used for bundle "value" (sum of single items), permanent fake strikethroughs, or anything else. It would become the anchor price and be reported as a sale every day. |
| **Currency, VAT, markets** | Base currency **EUR**, prices **including VAT**, the primary market is Croatia, and there are no fixed price overrides for Croatia. The script asks the store for the Croatian market in EUR, and **refuses to publish** if the store answers for another country, in another currency, or without VAT. This can happen if the store shows visitors from other countries (GitHub's servers are in the US) another market's prices, local currencies or tax-exclusive prices. |
| **Storefront** | **Not password-protected.** Every product for sale is **published to the Online Store sales channel**, because the price list reads the built-in collection `/collections/all`. |
| **Product status** | Products for sale have the status **Active**. Products with the status *Unlisted* aren't in `/collections/all` and aren't picked up by Flow 1, so they aren't covered. Don't sell regular products as Unlisted. |
| **`all` collection** | The store must **not** have its own collection with the handle `all`. It would replace Shopify's built-in "all products" collection. |
| **Size** | Up to **25,000 products**, which is where Shopify's pagination stops; the script refuses more instead of publishing a partial list. At most **250 variants per product**: Liquid lists no more, and the run fails with a clear message instead of publishing a partial product. The published site takes about 0.65 KB per variant per archived day, and GitHub Pages allows 1 GB. With the default `keep_days` 60, that's about **24,000 variants** in total; with `keep_days` 31, about 45,000. Beyond that, the deployment fails loudly. |
| **Shopify apps** | **Shopify Flow** installed (free, all plans). |
| **Theme** | You can add a template and a snippet to the **published** theme. |
| **GitHub** | A GitHub account. Store repositories are **public**: GitHub Pages is free for public repositories. The price list is public information anyway. |

**Tools on your computer:**
- **Python 3.10+** for step 2 and the optional local tests (`python3 --version`; on macOS `brew install python`).
  On Windows the command is `py -3` instead of `python3`, and the local tests also need `py -3 -m pip install tzdata`.
- **git** plus a GitHub login for step 10. The easiest ways are **GitHub Desktop**, or `gh auth login` (GitHub CLI).
  A personal access token also works, but it needs the **`workflow`** scope, because the kit contains files in
  `.github/workflows/`. Without git, you can upload the files in GitHub's web UI (**Add file → Upload files**).

---

## 3. Setup, step by step (per store)

Time for a typical store: about 2 hours of work, plus waiting for Flow runs.

> **Order matters.** Clean compare-at prices (step 2) **before** Flow 1 fills the anchor prices (step 4). Flow 1
> never overwrites a value that already exists. Install the theme template (step 9) **before** creating the
> repository (step 10), because the repository starts checking the store right away.

### Step 0: Get the kit on your computer

- **First store ever:** unzip the kit you received (`shopify-price-list-csv-xml-template`).
- **Later stores:** download your template repository (**Code → Download ZIP**) or `git clone` it (step 10.1).

Open a terminal in the kit folder. The commands below assume you're in it.

### Step 1: Back up the products

1. **Products → Export → All products → CSV for Excel, Numbers, or other spreadsheet programs → Export products.**
2. The file is called `products_export_1.csv`. Large stores get it by email as a download link.
3. Keep it. It's your backup, and you'll use it in step 2. Put it in the kit folder, but don't commit it: the
   `.gitignore` already excludes it.

### Step 2: Audit and clean compare-at prices

**Why:** Flow 1 writes *compare-at if it is higher than the price, otherwise the price* as the anchor price. The
price list marks *compare-at above price* as a sale (DA / Akcija). A misused compare-at would therefore produce a
wrong anchor price **and** a false sale flag every day.

1. Run the audit on the export. Include drafts, because they may be published later:
   ```bash
   python3 scripts/audit_compare_at.py products_export_1.csv --include-inactive --out audit.csv
   ```
2. Read the verdicts:

   | Verdict | Meaning | What to do |
   |---|---|---|
   | `SALE?` | compare-at > price | **Ask the client:** is this a **real, temporary sale** right now? **Yes:** keep it. **No** (bundle value, "you save vs. single items", permanent strikethrough): **clear the compare-at**. |
   | `WRONG` | compare-at < price | Clear the compare-at. |
   | `CLEAR` | compare-at = price | Clear the compare-at (it has no meaning). |

3. **Clear compare-at prices with the bulk editor:** **Products** → select the products → **Bulk edit** →
   **Columns → Compare-at price** → empty the cells → **Save**. The bulk editor is safer than a CSV import,
   which can overwrite other columns.
4. **Keep a "you save" display for bundles (optional, theme work):** create a variant metafield, for example
   `pricing.bundle_value` (Money, name "Bundle value", description "Sum of single-item prices"). Put the old
   compare-at value there and show it in the theme as, for example, `Pojedinačno: 69,00 € · Ušteda 11,50 €`.
   Don't use a strikethrough, which reads as a discount. This is optional and not part of the kit's code.
5. Re-export and re-run the audit. Only real, temporary sales may remain as `SALE?`.

> **Stores whose prices changed since 10 September 2026:** Flow 1 copies **today's** prices. If the client
> raised or lowered a **regular** price between 10 September and the day you run Flow 1, fix those variants
> by hand in step 7. Ask the client for that list now.

### Step 3: Create the metafield definitions

**Settings → Metafields and metaobjects** (older admin: *Custom data*) **→ Variants → Add definition**:

| # | Name | Namespace and key | Type | Settings |
|---|---|---|---|---|
| 1 | Anchor price | `pricing.anchor_price` | **Money**, one value | Description: *Regular price on the reference date (NN 101/2026)*. **Pin** it. Access → **Storefronts: on** |
| 2 | Anchor price date | `pricing.anchor_price_date` | **Date**, one value | Description: *Reference date of the anchor price*. **Pin** it. Access → **Storefronts: on** |

Type the namespace and key **exactly**: Flow and the theme find the fields by `pricing.anchor_price` and
`pricing.anchor_price_date`.

**Optional**, under **Products** (not Variants):

| Name | Namespace and key | Type | Purpose |
|---|---|---|---|
| Sale name | `pricing.sale_name` | Single line text | Name of the special form of sale for this product in the price list (e.g. `Sezonsko sniženje`, `Rasprodaja`). Empty = `Akcija`. |

> **Advanced:** the template also reads a **shop** metafield `pricing.sale_name` as the store-wide default.
> The Shopify admin has no simple editing screen for shop metafields, so set it through the Admin API or a
> metafields app, or just use the default `Akcija` plus the per-product field.

### Step 4: Flow 1: "Anchor price – backfill"

**What it does:** every hour, it takes up to 100 **active** products that don't have the tag `anchor-price-set`
yet, oldest first. For every variant **without** an anchor price, it writes:
- **Anchor price:** compare-at if it is higher than the price (the product is on sale, so its regular price),
  otherwise the price.
- **Anchor price date:** the **first listing** date, meaning the later of the variant's creation date and the
  product's publication date. If that is on or before 10 September 2026, it writes `2026-09-10`.

Then it tags the product `anchor-price-set`, so the next run skips it. The tag **stays**. After the backfill,
the Flow only picks up new products.

**Existing values are never overwritten.** A manual fix is safe forever.

#### 4a. Import (if you have an exported file)

1. **Flow → Import** → select the file from `shopify/flows/` → open the imported workflow. It arrives **turned off**.
2. Click every step and check that nothing is marked red. The metafield definitions from step 3 must exist.
3. **Get product data** → set the query to the **test** version from 4b.2, with `tag:test-anchor`.
4. **Update product variant metafield (Anchor price date)** → make sure **Value** is the current date rule from
   4b.7. Older exports used a simpler rule.
5. **Scheduled time** → set the start to a few minutes from now.
6. **Turn on**, then continue with 4c.

#### 4b. Build by hand

1. **Flow → Create workflow → Select a trigger → Scheduled time**
   - **Time zone:** `(GMT+02:00) Zagreb`
   - **Start:** today, a few minutes from now. The picker offers :00 and :30, but you can **type** any time
     (e.g. `9:12 pm`).
   - **Repeat:** every **1 hour**. For large stores, use every **10 minutes** until the backfill is done, then
     switch back to hourly.
   - **End:** none.
2. **+ → Action → Get product data**
   - **Sort data by:** `Created at`, `Ascending`
   - **Maximum number of products:** `100`
   - **Select a query to filter data:** `Advanced` → **Edit query** (test version for 4c):
     ```
     status:active AND tag:test-anchor AND -tag:anchor-price-set
     ```
3. **+ → For each loop (iterate)** → **Select list:** `getProductData`
4. On the loop's **Repeat for each item** exit (not "After last item"): **+ → For each loop (iterate)** →
   **Select list:** `getProductDataForeachitem` → `variants`
5. On the **inner** loop's **Repeat for each item** exit: **+ → Condition → Add criteria**
   - Pick `variantsForeachitem` → find **metafields**, click the **+** next to it → **Create variable** →
     select **Anchor price** (`pricing.anchor_price`) → name the variable `anchorPrice` → **Add**.
   - Choose `anchorPrice` → `value` → `amount`. Operator: **Does not exist**.
6. On the condition's **True / Then** exit: **+ → Action → Update product variant metafield**
   - **ProductVariant:** `variantsForeachitem.id`
   - **Metafield:** `Anchor price` (`pricing.anchor_price`), type Money
   - **Value** (one line, paste exactly):
     ```liquid
     {%- assign p = variantsForeachitem.price | plus: 0 -%}{%- assign c = variantsForeachitem.compareAtPrice | plus: 0 -%}{"amount": "{% if c > p %}{{ c }}{% else %}{{ p }}{% endif %}", "currency_code": "EUR"}
     ```
     If `compareAtPrice` turns red: delete the word and insert it with **Add variable →
     variantsForeachitem → compareAtPrice**.
7. Below it: **+ → Action → Update product variant metafield**
   - **ProductVariant:** `variantsForeachitem.id`
   - **Metafield:** `Anchor price date` (`pricing.anchor_price_date`), type Date
   - **Value** (one line, paste exactly):
     ```liquid
     {%- assign listed = variantsForeachitem.createdAt | date: '%Y%m%d' | plus: 0 -%}{%- assign published = getProductDataForeachitem.publishedAt | date: '%Y%m%d' | plus: 0 -%}{%- if published > listed -%}{%- assign listed = published -%}{%- endif -%}{%- if listed <= 20260910 -%}2026-09-10{%- else -%}{%- assign d = listed | append: '' -%}{{ d | slice: 0, 4 }}-{{ d | slice: 4, 2 }}-{{ d | slice: 6, 2 }}{%- endif -%}
     ```
     If `publishedAt` turns red: delete the word and insert it with **Add variable →
     getProductDataForeachitem → publishedAt**. If Flow doesn't offer `publishedAt` at all, use this simpler
     rule, which uses the variant's creation date only:
     ```liquid
     {%- assign listed = variantsForeachitem.createdAt | date: '%Y%m%d' | plus: 0 -%}{%- if listed <= 20260910 -%}2026-09-10{%- else -%}{%- assign d = listed | append: '' -%}{{ d | slice: 0, 4 }}-{{ d | slice: 4, 2 }}-{{ d | slice: 6, 2 }}{%- endif -%}
     ```
     With the simpler rule, a draft published later gets its creation date. Fix those by hand (step 7).
8. On the **inner** loop's **After last item** exit: **+ → Action → Add product tags**
   - **Product:** `getProductDataForeachitem.id`
   - **Tags:** `anchor-price-set`
9. Name the workflow **Anchor price – backfill** → **Turn on**.

> **Common mistakes:** attaching the inner loop to the outer loop's *After last item* (then `variants` isn't
> offered); attaching the tag action anywhere other than the **inner** loop's *After last item*.
>
> **Known edges:** Flow dates are in UTC, so a product first listed between midnight and 02:00 (01:00 in winter)
> Zagreb time gets the previous day's date. A product that was published before 10.9., then hidden from the
> Online Store and published again later, gets the later date. Fix such cases by hand if they matter.

#### 4c. Test on 3 products

1. Tag active products with `test-anchor`:
   - one **on a real sale** (compare-at > price)
   - one **without** compare-at
   - one with **several variants**, if the store has any
   - optional but recommended: a **new test product** created and made active today (draft → active), so the
     date rule is tested too. Delete it after the test.
2. Wait for the next run (or set the start time to a couple of minutes from now).
3. **Flow → the workflow → Recent runs:** the run should say **Completed**, with no failed steps.
4. On each test product, check the **Variant metafields** card:
   - The **on-sale** product has **Anchor price = compare-at**.
   - The others have **Anchor price = price**.
   - Products listed before 10.9. show **Anchor price date = Sep 10, 2026**; the new test product shows
     **today's** date.
   - The product has the tag **`anchor-price-set`**.
5. Open any product **without** `test-anchor`: both fields should be empty, with no tag.

#### 4d. Run it for the whole store

1. Edit **Get product data** → query:
   ```
   status:active AND -tag:anchor-price-set
   ```
   Wait for **Saved**. The red **Turn off workflow** button at the top means the Flow is on.
2. After the next run: open the run → the canvas shows how many products went through each step (e.g. `13`).
   It should match the number of active products without the tag (at most 100 per run). The already-tagged test
   products are skipped.
3. It takes about **1 run per 100 products**: 1,000 products take 10 runs, so 10 hours hourly or 100 minutes at
   every 10 minutes.
4. Remove the `test-anchor` tags whenever you like (bulk editor or product page).
5. Export the finished workflow (**More actions → Export**) into `shopify/flows/anchor-price-backfill.flow`, so
   the next store can import it. Note that the export contains the whole-store query.

### Step 5: Flow 2: "Anchor price – reset on new variant"

**Why:** Flow 1 skips products tagged `anchor-price-set`. When someone adds a **new variant** to such a product,
that variant needs an anchor price too. Flow 2 removes the tag, the next hourly run of Flow 1 picks the product
up again, and it fills **only** the new variant (existing values aren't touched).

1. **Flow → Create workflow → Select a trigger → Product variant added**
2. **+ → Action → Remove product tags**
   - **Product:** `product.id` (the product of the new variant; Flow offers it from the trigger).
   - **Tags:** `anchor-price-set`
3. Name it **Anchor price – reset on new variant** → **Turn on**.
4. Export it into `shopify/flows/anchor-price-reset-on-new-variant.flow`.

*Or import it:* **Flow → Import** → `shopify/flows/anchor-price-reset-on-new-variant.flow` → check that no step is
red → **Turn on**.

### Step 6: Flow 3: "Anchor price – reset on new product"

**Why:** when you **duplicate** a product, Shopify copies its variant metafields (since February 2024) and its
tags. Without Flow 3, the copy would keep the original's anchor price and 10.9. date, and Flow 1 would skip it
because of the copied tag. Flow 3 clears both for every newly created product, so Flow 1 treats the copy as a
new listing.

1. **Flow → Create workflow → Select a trigger → Product created**
2. **+ → For each loop (iterate)** → **Select list:** `product` → `variants`
3. On **Repeat for each item**: **+ → Condition → Add criteria** → `variantsForeachitem` → metafields → **+** →
   **Create variable** → **Anchor price** → name `anchorPrice` → `value` → `amount` → operator **Exists**.
4. On **True / Then**: **+ → Action → Remove product variant metafield**
   - **Product variant:** `variantsForeachitem.id`
   - **Metafield:** `Anchor price` (`pricing.anchor_price`)
5. Below it: **+ → Action → Remove product variant metafield**
   - **Product variant:** `variantsForeachitem.id`
   - **Metafield:** `Anchor price date` (`pricing.anchor_price_date`)
6. On the loop's **After last item**: **+ → Action → Remove product tags** → **Product:** `product.id` →
   **Tags:** `anchor-price-set`
7. Name it **Anchor price – reset on new product** → **Turn on**.
8. **Test:** duplicate a product that already has an anchor price. Open the copy: both fields should be empty,
   with no `anchor-price-set` tag. Delete the copy afterwards.
9. Export it into `shopify/flows/anchor-price-reset-on-new-product.flow`.

*Or import it:* **Flow → Import** → `shopify/flows/anchor-price-reset-on-new-product.flow` → check that no step is
red → **Turn on** → run the duplicate test (point 8).

> **Importing products with anchor prices** (e.g. a CSV migration from another store): Flow 3 clears them.
> Turn Flow 3 off during such an import, then back on.

### Step 7: Verify the anchor prices

1. **Products** → filter **Status: Active** → note the count.
2. Add the filter **Tagged with: `anchor-price-set`**. The count should be the **same**.
3. Spot-check 3 products (one on sale, one normal, one multi-variant) in the **Variant metafields** card.
4. Fix by hand every variant whose **regular** price changed since 10 September 2026 (see step 2): type the
   10.9. price into **Anchor price**. Flow never overwrites it.
5. If you used the simpler date rule (4b.7): drafts published after 10.9. show their creation date. Set
   **Anchor price date** to the publication day.

### Step 8: Show the anchor price on the storefront

**Legal display rules** (1.1): next to the retail price, clearly and legibly, visible without clicking. Never
styled as a discount (no strikethrough). Always shown, even when it equals the current price.

**Output:** `Sidrena cijena na dan 10. 9. 2026.: 62,00 €`. The date comes from `pricing.anchor_price_date`,
so newer products show their own date.

**Fastest way (custom theme + Claude Code):** give Claude Code the file
`shopify/anchor-price-display-brief.md`. It contains the whole task:
- mapping the theme's price outputs, and waiting for your OK before editing
- the snippet, a theme setting, the locale strings and the CSS
- placements on the product page, cards, quick view and predictive search (cart is optional)
- the test plan

**Manual integration (any theme):**
1. **Edit code → Snippets → Add a new snippet** `anchor-price` → paste `shopify/snippets/anchor-price.liquid`.
2. On the **product page**, render it **inside the price element that the theme re-renders when the variant
   changes** (Section Rendering API or equivalent). The anchor price then updates with the variant, with no JS:
   ```liquid
   {% render 'anchor-price', variant: product.selected_or_first_available_variant %}
   ```
3. On **product cards** (collection, search, recommendations): pass the variant whose price the card shows. See
   the brief, §4.3, for "from" prices and price ranges.
4. Add the **locale strings** to the default locale file:
   ```json
   "products": { "product": { "anchor_price": { "label": "Sidrena cijena na dan {{ date }}:", "from": "od" } } }
   ```
5. Add the **theme setting** (`config/settings_schema.json`). It's a kill switch, on by default:
   ```json
   { "name": "Anchor price", "settings": [ { "type": "checkbox", "id": "show_anchor_price", "label": "Show anchor price (sidrena cijena)", "default": true } ] }
   ```
6. Add the **CSS**: at least 14px, body text colour, and **no** `line-through`:
   ```css
   .anchor-price { margin: .25rem 0 0; font-size: max(14px, .875em); line-height: 1.4; color: inherit; text-decoration: none; }
   .anchor-price__value { white-space: nowrap; }
   ```
7. **Test:**
   - Every placement shows the line.
   - Changing the variant updates it.
   - A variant without an anchor price shows nothing, with no empty gap.
   - Mobile (360px) is readable.

### Step 9: Install the price list theme template

1. **Online Store → Themes → the PUBLISHED theme → … → Edit code → Templates → Add a new template.**
2. Type: **collection**. Format: **liquid** (not JSON). Name: **`price-list`**. This creates
   `templates/collection.price-list.liquid`.
3. Replace its whole content with `shopify/templates/collection.price-list.liquid` → **Save**.
4. Open `https://<store-domain>/collections/all?view=price-list`:
   - The browser shows one long paragraph. That's normal, because Shopify serves templates as HTML.
   - **View source** (`Ctrl+U` / `Cmd+Option+U`). Line 1 is the header `naziv;sifra;marka;…;dostupnost`, then
     one line per variant, with **no empty lines in between**.
   - Every line has the **anchor price** filled in (9th column).
   - Products on a real sale show `DA;"Akcija"`. All others show `NE;""`.
   - The **last line** is the control line, e.g.
     `#meta;page=1;pages=1;items=16;listed=16;skipped=0;truncated=0;currency=EUR;country=HR;taxes_included=true`.
     Check that `items` equals the number of active products published to the Online Store, and that it says
     `currency=EUR` and `taxes_included=true`. The script removes this line: it never appears in the published
     files.
5. Open `…/collections/all?view=price-list&page=2`. Small stores (≤ 250 products) show the header and a
   `#meta` line with `listed=0`.

> **Why this template can't be edited per store:** it must stay identical everywhere, so updates can be copied
> over. Store-specific choices live in metafields (sale name) and `config.json`.
>
> **New theme?** If the client publishes another theme, copy the template (and the snippet) into it **before**
> publishing it. Otherwise the next morning's run fails with a clear error email.

### Step 10: Create the store's GitHub repository

#### 10.1 One-time: your template repository

Do this once, not per store:

1. On GitHub: **New repository** → name `shopify-price-list-csv-xml-template` → **Private** (recommended; only the
   store repositories must be public) → create it **empty**, with no README.
2. Upload the kit, using one of these:
   - **git** (in the kit folder):
     ```bash
     git init -b main
     git add -A
     git commit -m "shopify-price-list-csv-xml-template kit"
     git remote add origin https://github.com/<you>/shopify-price-list-csv-xml-template.git
     git push -u origin main
     ```
   - **GitHub Desktop:** File → Add local repository → the kit folder → Publish.
   - **Web UI:** Add file → Upload files → drag in the **contents** of the kit folder (including the `.github`
     folder; on macOS press `Cmd+Shift+.` to show hidden folders) → Commit.
3. Repository **Settings → General →** tick **Template repository**.
4. **Actions** tab: the **Tests** workflow runs once and should be green. (In a private template repository it uses a
   minute or two of your free monthly Actions allowance, and only when you push changes.)
5. Disable the template's own daily workflow, because its `config.json` has `CHANGE_ME` and would fail every
   morning: **Actions → Price list → ⋯ → Disable workflow**. Repositories created from the template get it enabled.

#### 10.2 Per store: a new repository from the template

1. Open your template repository → **Use this template → Create a new repository**.
   - Name: e.g. `price-list-<store>`
   - Visibility: **Public** (required: GitHub Pages is free only for public repositories). A private template can
     create public repositories.
2. **Edit `config.json`** in the new repository (click the file → pencil icon). Fill in every `CHANGE_ME` value
   (see [section 6](#6-configuration-reference-configjson)), then **Commit changes**.
   - `domain`: the store's primary domain, e.g. `www.example-store.hr`. No `https://`, no slash.
   - `address`: the address registered for the webshop, in normal text. The script converts it to
     `Ilica-150-Zagreb` for file names.
   - `premises_label`: the *oznaka poslovnog prostora* for the webshop, e.g. `WEB01`. Letters, digits and
     hyphens only.
   - `first_day`: the go-live date. For stores that go live on the legal start date, `2026-10-01`. For a store you
     set up **later**, use its first real publishing day (e.g. tomorrow), so storage numbers start at 1. For the
     test in 10.4, temporarily **today's date**.
3. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
4. **Settings → Actions → General:** "Allow all actions" (the default).

#### 10.3 Notifications

GitHub emails the account that created the repository when a **scheduled** run fails. Check
**github.com → your profile → Settings → Notifications → Actions:** notifications on, e.g.
"Only notify for failed workflows".

#### 10.4 First test run

1. In `config.json`, set `"first_day"` to **today** (e.g. `"2026-09-24"`) and commit.
2. **Actions → Price list → Run workflow** (leave all options unticked) → **Run workflow**.
3. Open the run once it's done (1–2 minutes):
   - **Summary:** "Price list published", with row count, pages, product total, file names and any warnings.
   - **Deploy to GitHub Pages:** the URL of the site, `https://<you>.github.io/<repo>/`.
4. Open the site. You should see:
   - the trader details and the current price list with **CSV** and **XML** links
   - an archive table with 1 row (storage number **1**)
5. Open `latest.csv`: the header plus one line per variant, the same as the template output in step 9, without
   the `#meta` line.
6. **Compare 2–3 rows with the admin:** same price, same anchor price, in EUR. This proves that GitHub's servers
   see the Croatian prices.
7. Open `latest.xml`: `<cjenik><proizvod>…</proizvod>…</cjenik>`, with decimal dots.
8. Optional: **Run workflow** with **dry_run** ticked. It only fetches and checks, and publishes nothing.

#### 10.5 Switch to the real go-live date

1. In `config.json`, set `"first_day"` back to the go-live date (e.g. `"2026-10-01"`, or tomorrow for a store set
   up after 1 October) → commit.
2. **Actions → Price list → Run workflow** with **reset_archive ticked** → the test files are deleted.
3. Until the go-live date:
   - The site shows *"Objava cjenika počinje 1. 10. 2026."*
   - The daily runs still **check** the store every morning (template, currency, VAT, totals) and email you if
     something is wrong, but they publish nothing.
4. From the go-live date on, the first run publishes storage number **1**.

### Step 11: Custom domain (optional)

For example, to publish the price list at `cjenik.<client>.hr`:

1. At the client's DNS provider: add a **CNAME** record `cjenik` → `<you>.github.io`.
2. Repository **Settings → Pages → Custom domain:** `cjenik.<client>.hr` → **Save** → wait for the DNS check →
   tick **Enforce HTTPS**. The certificate can take up to an hour.
3. Recommended: verify the domain in your GitHub profile (**Settings → Pages → Add a domain**), so nobody else
   can take it over.
4. Use the new address in step 12.

### Step 12: The "Cjenik" page in the store

1. **Online Store → Pages → Add page.** Title **Cjenik**. Paste this content, and replace `PAGES_URL` with the
   site address from step 10.4 (e.g. `https://<you>.github.io/price-list-<store>`) or your custom domain
   from step 11:
   ```text
   Sukladno Odluci o objavi cjenika proizvoda i usluga kao mjeri izravne kontrole cijena (NN 101/2026),
   cjenik proizvoda naše internetske trgovine objavljujemo svaki dan u strojno čitljivom obliku (CSV i XML).

   Trenutni cjenik i arhiva (najmanje 30 dana): PAGES_URL/
   Izravne poveznice: PAGES_URL/latest.csv (CSV) · PAGES_URL/latest.xml (XML)
   ```
   Then select each address in the editor and turn it into a link (link icon).
2. **Save** (visible).
3. **Online Store → Navigation → Footer menu → Add menu item:** "Cjenik" → link to the page.

### Step 13: Go live

Before the go-live date:

- [ ] Compare-at cleaned (step 2); the audit shows only real sales.
- [ ] Flows 1, 2 and 3 turned **on** (steps 4–6).
- [ ] Anchor prices on **all** active variants (step 7); the tag count equals the active product count.
- [ ] Changed regular prices since 10.9. fixed by hand (step 7).
- [ ] Anchor price visible next to the price on product pages and cards (step 8).
- [ ] Template output checked in view-source, including the `#meta` line (step 9).
- [ ] Repository test run OK and compared with the admin (step 10.4).
- [ ] `first_day` = go-live date, archive reset (step 10.5); the daily pre-live checks are green.
- [ ] Page "Cjenik" + footer link live (step 12).

On the go-live morning, check the **Actions** tab: the first scheduled run should be green, and the site should
show storage number 1.

---

## 4. Daily operation

**Every morning, automatically:**
1. About **04:17** (03:17 in winter), the workflow fetches all pages of the price list, checks them, and
   publishes the CSV + XML with today's date and storage number.
2. Backup runs at about 05:47, 06:37 and 07:17 (an hour earlier in winter) do nothing if today is already
   published. If the main run was late, skipped by GitHub, or failed, they publish.
3. Archived days older than `keep_days` are deleted. `latest.csv` / `latest.xml` always contain the most recently
   published list.

**What the client does in Shopify, as usual:**
- **Start a sale:** set the compare-at price (the regular price) and lower the price. The next morning's price
  list says `DA` + `Akcija`, or the product's `Sale name`.
- **End a sale:** set the price back and **clear** the compare-at.
- **Add a product:** Flow 1 gives it an anchor price within an hour of it becoming active, dated with its first
  listing day.
- **Add a variant:** Flow 2 + Flow 1 give it an anchor price within an hour.
- **Duplicate a product:** Flow 3 clears the copied values; Flow 1 fills fresh ones once the copy is active.
- **Publish an old draft:** Flow 1 picks it up within an hour, dated with the publication day. With the simpler
  date rule (4b.7), set the date by hand.
- **Change a regular price:** nothing to do. The anchor price stays the 10.9. value (or first listing value).

**What you check, about once a month (2 minutes):**
- **Actions** tab: all runs green. Open the latest run's summary to see any warnings; green runs can still carry
  warnings, e.g. rows without an anchor price.
- The site: today's date at the top.
- **Products:** Active count = `anchor-price-set` count.

---

## 5. When something goes wrong (runbook)

A failed run publishes **nothing**. Yesterday's files stay online, and GitHub sends you an email. Open the run →
**Summary**; the first line is the reason. After fixing the cause, use **Run workflow** to publish right away,
or let the next backup run do it.

| Message / symptom | Cause | Fix |
|---|---|---|
| `does not start with the expected CSV header` | Template missing in the **published** theme (new theme published?), or `template_view` wrong | Step 9 |
| `has no '#meta' control line` | The theme has an **old version** of the template, or the page was cut off | Re-install the template from `shopify/templates/` (step 9) |
| `The '#meta' line … is incomplete` | The template was edited | Re-install the template |
| `The store answered in currency 'USD' …` | Visitors from abroad are shown another currency (Markets) | Settings → Markets: the Croatia market is the primary market; don't show other currencies to the rest of the world (or remove that market). Then Run workflow |
| `The store answered for country 'US' …` | The store served another market's prices (the market cookie was ignored) | Settings → Markets: make sure other markets don't change prices, or remove them. If the store has **only** the Croatia market: `"require_country_match": false` in `config.json` |
| `… prices WITHOUT VAT …` | "Include or exclude tax based on the customer's country" is on, or prices are entered without VAT | Settings → Taxes and duties. If the store never charges VAT at all: `"require_taxes_included": false` in `config.json` |
| Warning `Could not verify that prices include VAT` | The theme didn't report the VAT mode | Check one row against the admin; nothing else to do |
| `password-protected` | Storefront password on | Online Store → Preferences → remove the password |
| `HTTP 404 …` | Wrong `domain` or `collection_path` | Fix `config.json` |
| `HTTP 402 …` / `HTTP 403 …` | Store frozen or closed (unpaid plan), or a firewall or bot protection blocks GitHub | Check the store in a browser; check apps that block visitors by country |
| `HTTP 429 / 430 / 5xx … after 5 attempts` | Shopify rate limiting or an outage | Usually solved by the backup runs; otherwise Run workflow later |
| `Could not fetch … after 5 attempts` | Network or DNS problem (e.g. domain moved) | Check the domain works in a browser; fix `domain` |
| `Products changed while the price list was being fetched, twice in a row` | Products were added or removed during the run (imports, apps) | Nothing: the next backup run tries again. If it repeats every day, move the import to another time |
| `Only N rows today vs M …` | More than 50% fewer products than the last list (products unpublished by mistake?) | Check the store. If the drop is real: Run workflow with **force** |
| `The price list has 0 products` | Nothing published to the Online Store, or a custom collection with the handle `all` | Publish the products; rename the custom collection |
| `… more variants than Shopify's Liquid can list` | A product with a very large number of variants | Not supported: split the product |
| `Shopify's pagination stops at 25,000` | More than 25,000 products | Not supported by this kit |
| `… pages but max_pages is …` | More pages than the safety cap | Raise `max_pages` (up to 100 = 25,000 products) |
| `Requested page N but the store answered page M` | Something between GitHub and the store rewrites URLs (proxy, app) | Check `domain` points straight at Shopify |
| `Invalid retail price` / `Expected 11 columns` / `Malformed CSV` / `Empty product name` / `posebni_oblik_prodaje must be …` / `dostupnost must be …` | The template was edited, or is an old version | Re-install the template |
| `Sale without a name` | Should not happen with the kit's template | Re-install the template |
| `is not valid JSON` | A comma or quote is missing in `config.json` (easy to do in the web editor) | Fix the syntax; every line except the last one inside `{ }` ends with a comma |
| `Unknown config key(s)`, `Config is missing …`, `CHANGE_ME`, `must be a bare host name`, `must be YYYY-MM-DD`, `'premises_label' may only contain …`, `not a valid ISO code`, `must be true or false`, `must be a whole number`, `must be at least …`, `must be between 0 and 100`, `must start with '/'` | `config.json` typo or not filled in (after a kit update: a key the new version no longer uses) | Fix `config.json` (section 6); delete keys named in `Unknown config key(s)` |
| `Invalid sidrena_cijena` / `Invalid cijena_za_jedinicu_mjere` | The anchor price metafield has the wrong type (e.g. Decimal instead of Money), or the template was edited | Step 3: the definition must be **Money**; re-install the template |
| `is not valid UTF-8`, `more than one '#meta' line`, `non-numeric` | Something between GitHub and the store changes the pages, or the template was edited | Re-install the template; check `domain` points straight at Shopify |
| `manifest.json is corrupted` | Someone edited `site/` by hand, or a merge went wrong | Restore `site/manifest.json` from git history, or Run workflow with **reset_archive** (this deletes the archive; use it only if the history can't be restored) |
| `Generated XML is not well-formed` / `XML has N products but CSV has M` | A bug | Send the run log to the kit maintainer |
| Warning `row(s) without an anchor price` | New product in the last hour, Flow 1 off, or a Flow error | Check Flow 1's runs. The price list is still published |
| Warning `exactly duplicated row(s)` | Two products with the same title, SKU and prices | Check for accidental duplicates in the store |
| Red run at **Configure GitHub Pages** (`Get Pages site failed`) | Pages source isn't "GitHub Actions" | Step 10.2 point 3, then Run workflow |
| Red run at **Save to repository** (push rejected) | Branch protection on `main` | Allow GitHub Actions to push to `main`, or remove the protection |
| No run at all in the morning | GitHub delay or outage, or Actions disabled | **Actions → Price list → Run workflow**. Public repositories with no activity for 60 days get scheduled workflows disabled; the daily commits prevent that after go-live |
| Flow 1 run failed | Usually a metafield definition deleted or renamed | Step 3 names must match exactly |

**Manual run options** (Actions → Price list → Run workflow):

| Option | Effect |
|---|---|
| *(none)* | Normal run: publishes today if not yet published (before the go-live date: only checks) |
| `force` | Rebuilds today even if already published (the old today files are replaced), and skips the row-drop guard |
| `reset_archive` | Deletes **all** published files first. Use once when going live after testing |
| `dry_run` | Fetches and checks only. Nothing is written or deployed |

---

## 6. Configuration reference (`config.json`)

Keys starting with `_` are comments and are ignored. **Any other unknown key is an error**, so a typo can't
silently fall back to a default.

| Key | Required | Default | Meaning |
|---|---|---|---|
| `store_name` | yes | – | Shown on the index page (title). |
| `company_name` | no | `store_name` | Legal name of the trader, shown on the index page. |
| `company_oib` | no | empty | OIB, shown on the index page if set. |
| `domain` | yes | – | Primary store domain, e.g. `www.example-store.hr`. No `https://`, no slash. |
| `address` | yes | – | Registered address of the webshop, normal text. Used on the index page and, converted, in file names. |
| `premises_label` | yes | – | *Oznaka poslovnog prostora*, e.g. `WEB01`. Letters, digits, hyphens. |
| `first_day` | yes | – | Go-live date `YYYY-MM-DD`. Storage number 1 = this day. Before it, runs only check. |
| `form_of_sale` | no | `internetska-trgovina` | First part of the file name (*oblik prodajnog objekta*). |
| `address_slug` | no | from `address` | Override the file-name form of the address. |
| `shop_url` | no | `https://<domain>` | Link to the shop on the index page. |
| `currency` | no | `EUR` | Currency the price list must be in; the run fails otherwise. |
| `country` | no | `HR` | Market requested from the store. |
| `require_country_match` | no | `true` | Fail if the store answers for another country than `country`. Set `false` only if the store has no other markets. |
| `require_taxes_included` | no | `true` | Fail if the store answers with prices without VAT. Set `false` only if the store never charges VAT. |
| `keep_days` | no | `60` | Days of archive kept. Values below 31 are raised to 31. |
| `max_row_drop_percent` | no | `50` | Refuse to publish if today has this % fewer rows than the last list. |
| `fail_on_missing_anchor` | no | `false` | `true` = refuse to publish if any row has no anchor price. `false` = publish and warn. |
| `csv_bom` | no | `false` | `true` = start the CSV with a UTF-8 BOM (helps old Excel show č, ć, ž…). |
| `collection_path` | no | `/collections/all` | Collection the template reads. |
| `template_view` | no | `price-list` | Template suffix (`collection.<view>.liquid`). |
| `sort_by` | no | `created-ascending` | Keeps paging stable while products are added during a run. |
| `max_pages` | no | `100` | Safety cap (× 250 products). 100 pages = Shopify's 25,000 limit. |
| `request_delay_seconds` | no | `1.0` | Pause between page requests (be polite to the store). |
| `request_timeout_seconds` | no | `60` | Timeout per request. |
| `retries` | no | `5` | Attempts per page for network errors and HTTP 408/425/429/430/5xx. |

---

## 7. File names, numbering and archive

**File name:** `oblik_adresa_oznaka_brojpohrane_datum_vrijeme`

```
internetska-trgovina_Ilica-150-10000-Zagreb_WEB01_26_26.10.2026_03.17.csv
└─ form_of_sale ────┘└─ address ────────────┘└label┘└#┘└─ date ──┘└time┘
```

- **Storage number (broj pohrane):** days since `first_day`, plus 1. `first_day` = 1, the next day = 2, and so
  on. It keeps counting through weekends.
- **Date and time:** local Zagreb time of the snapshot. Summer and winter time are handled.
- **Why dots instead of `07:45` and spaces:** colons and spaces aren't safe in URLs.

**Published site (`site/`):**

| Path | Content |
|---|---|
| `index.html` | Trader details, current price list, archive table, format description (Croatian). |
| `latest.csv`, `latest.xml` | The most recently published price list (stable URLs for machines and the "Cjenik" page). |
| `files/<name>.csv`, `files/<name>.xml` | The dated archive. |
| `manifest.json` | Machine-readable list of all files (number, date, time, rows, on-sale count, SHA-256). |
| `robots.txt` | "Allow everything". Crawlers only read it at the root of a domain, so it takes effect with a custom domain (step 11). On `<you>.github.io/<repo>/` nothing blocks crawlers either. |

**Formats:**
- **CSV:** UTF-8, `;` separator, decimal comma, text fields in double quotes (with `""` for a quote), LF line
  endings, one line per variant.
- **XML:** UTF-8, `<cjenik>` with one `<proizvod>` per variant, element names equal to the CSV columns,
  decimal dot.

---

## 8. Maintenance and updates

**Updating a store repository after you improve the template repository:**
```bash
git clone https://github.com/<you>/price-list-<store>.git && cd price-list-<store>
git remote add template https://github.com/<you>/shopify-price-list-csv-xml-template.git
git fetch template
git checkout template/main -- scripts tests shopify .github README.md .gitignore
git commit -m "Update kit from template" && git push
```
This never touches `config.json` or `site/`. With a **private** template repository, `git fetch template` asks
you to sign in (the same GitHub login you push with, e.g. via GitHub Desktop or `gh auth login`). The store
repository itself stays public. If the next run then fails with `Unknown config key(s)`, the new
version no longer uses that key: delete it from `config.json`. If the update changed `shopify/templates/collection.price-list.liquid`
or `shopify/snippets/anchor-price.liquid`, copy them into the store's theme as well. The script's version is
shown at the top of every run log.

**Run the tests locally** (Python 3.10+): `python3 -m unittest discover -s tests -v`

**Common changes:**
- **Address or premises label changed:** edit `config.json`. New files use the new name; archived files keep theirs.
- **New theme:** copy `templates/collection.price-list.liquid` and `snippets/anchor-price.liquid` (plus its
  render calls, locale strings, setting and CSS) into it before publishing.
- **Client leaves:** transfer the repository (**Settings → General → Transfer ownership**) to the client's
  GitHub account, or hand over the configuration.
- **Stop publishing:** Actions → Price list → ⋯ → **Disable workflow**. The site stays online with the last files.

**Hosting note:** GitHub Pages is free for public repositories, but GitHub's terms say Pages isn't meant as
hosting for an online business itself. Publishing a static compliance file is a light use. If you ever need to
move, the published `site/` folder is plain static files and can be served by any static host (Cloudflare Pages,
Netlify…) with the same workflow.

---

## 9. Per-store checklist

Copy this into an issue in the store's repository and tick it off.

```markdown
- [ ] 1  Products exported (backup)
- [ ] 2  Compare-at audit run (incl. drafts); only real temporary sales remain; client confirmed
- [ ] 2  List of regular prices changed since 10.9.2026 obtained from the client
- [ ] 3  Variant metafields pricing.anchor_price (Money) + pricing.anchor_price_date (Date), pinned, storefront access
- [ ] 3  (optional) Product metafield pricing.sale_name
- [ ] 4  Flow 1 "Anchor price – backfill" built/imported, tested on 3 products, query switched to all active products
- [ ] 5  Flow 2 "Anchor price – reset on new variant" on
- [ ] 6  Flow 3 "Anchor price – reset on new product" on; duplicate test OK
- [ ] 7  Active count = anchor-price-set count; spot checks OK; changed prices fixed by hand
- [ ] 8  Anchor price shown next to the price (product page, cards, quick view, search); variant switch OK; mobile OK
- [ ] 9  Template collection.price-list in the PUBLISHED theme; view-source OK; #meta: items, EUR, taxes_included=true
- [ ] 10 Repo from template; config.json filled; Pages source = GitHub Actions; notifications on
- [ ] 10 Test run OK (first_day = today); rows compared with the admin; then first_day = go-live + reset_archive
- [ ] 11 (optional) Custom domain + HTTPS
- [ ] 12 Page "Cjenik" + footer link
- [ ] 13 First scheduled run on go-live day green; storage number 1 online
```

---

## 10. FAQ

**Why GitHub and not Shopify's own Files?** It was tested on 24.9.2026. `fileCreate` requires the source URL to end
in the file extension, and even through a `.csv` redirect, Shopify rejects the theme's output ("Media processing
failed"), because theme templates are always served as HTML. There is no free way that works on every plan to make
Shopify produce and store the file on its own.

**Why is the template limited to 250 products per page?** That's Shopify's maximum per page. The script requests
every page the store reports, up to Shopify's limit of 25,000 products.

**How does the script know it got every product?** Each page ends with a `#meta` line holding the store's total
product count and the number of products on that page. The script adds up the pages. If the sum doesn't match, for
example because products were added or removed during the run, it fetches everything once more. If it still
doesn't match, it publishes nothing and the next backup run tries again. The pages are also sorted by creation
date, so a product added during the run lands on the last page. The one case it can't see is a product removed
**and** another one added in the same few seconds of a run: the total stays the same. That can make one product
missing or stale in that day's list; the next day's list is correct again.

**Why are some fields empty?** `jedinica_mjere` / `cijena_za_jedinicu_mjere` are only filled when the variant has
Shopify's **unit price** set; `barkod` only when the variant has a barcode. The law requires them only "if
applicable".

**What is in `sifra` when a variant has no SKU?** The variant's Shopify ID, so every row still has a unique code.
Setting SKUs is better.

**Gift cards?** Excluded from the price list. Flow 1 may give them an anchor price, which is harmless.

**Weekends and holidays?** The law requires working days; the kit publishes every day, which is allowed and simpler.

**Summer/winter time?** Handled. The schedule is in UTC, chosen so all runs are before 08:00 in both seasons, and
file times are local Zagreb time.

**Can a product show a different sale name, e.g. "Sezonsko sniženje"?** Yes: set the product metafield
`pricing.sale_name` (step 3).

**Bundles that show a saving?** Not through compare-at (step 2). Use a separate metafield and a "you save" line.

**Does the anchor price ever change?** Not automatically. Flow 1 only fills empty values; Flow 3 only clears
values on **newly created** products (duplicates). It changes only if you edit it by hand.

**Is `sort_by=created-ascending` also applied on the storefront?** Only for the price list requests. Nothing
changes for shoppers.

---

### Sources

- Odluka o isticanju dodatne cijene kao mjera izravne kontrole cijena, NN 101/2026-1212:
  https://narodne-novine.nn.hr/clanci/sluzbeni/2026_09_101_1212.html
- Odluka o objavi cjenika proizvoda i usluga kao mjeri izravne kontrole cijena, NN 101/2026-1213:
  https://narodne-novine.nn.hr/clanci/sluzbeni/2026_09_101_1213.html
- Ministry of Economy clarification of 22 September 2026 (webshops: separate file, file-name order, 08:00, 30 days,
  machine access, new products and products on sale).
- Shopify Liquid, metafield types (money = money object, date = date string):
  https://shopify.dev/docs/api/liquid/objects/metafield
- Shopify Flow action "Remove product variant metafield":
  https://help.shopify.com/en/manual/shopify-flow/reference/actions/remove-product-variant-metafield
- Shopify changelog, product duplication copies variant metafields (14 Feb 2024):
  https://shopify.dev/changelog/product-duplication-now-duplicates-variant-metafields
