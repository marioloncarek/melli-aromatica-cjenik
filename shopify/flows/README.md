# Exported Flow files

Exported Shopify Flow workflows, ready to import into every further store (Flow → **Import**). Add the missing
ones after setting them up (Flow → open the workflow → **More actions → Export**), under these names:

| File | Workflow | Setup guide | In the kit |
|---|---|---|---|
| `anchor-price-backfill.flow` | **Anchor price – backfill** (compare-at value, first-listing date rule, whole-store query, hourly) | README → Step 4 | ✅ verified 24.9.2026 |
| `anchor-price-reset-on-new-variant.flow` | **Anchor price – reset on new variant** | README → Step 5 | ✅ verified 24.9.2026 |
| `anchor-price-reset-on-new-product.flow` | **Anchor price – reset on new product** | README → Step 6 | ✅ verified 24.9.2026 |

The backfill file's schedule starts on 23.9.2026 23:30 (Zagreb). After importing, set the start to a few minutes
from now (README → Step 4a).

Notes:
- `.flow` files are signed by Shopify. Don't edit them in a text editor, or the import will fail. Change them
  after importing, inside Flow.
- An imported workflow arrives **turned off**. Follow README → Step 4a: check every step for red errors, switch the
  backfill query to the **test** version, check the date rule, set the start time, turn it on, test (Step 4c).
- The metafield definitions (README → Step 3) must exist **before** you import, with exactly the same namespace and key.
- The backfill's Anchor price value is the compare-at formula (README → Step 4b.6). Clean the store's compare-at
  prices first (README → Step 2).
