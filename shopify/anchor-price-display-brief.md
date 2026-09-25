# Task: Show the anchor price (sidrena cijena) in the theme

> Part of the **shopify-price-list-csv-xml-template** kit. The finished snippet is in `shopify/snippets/anchor-price.liquid`; this brief tells Claude Code how to integrate it into a custom theme.

> **Audience:** Claude Code, working in a custom Shopify theme repo.
> **Owner:** Mario (developer). Customer-facing text is Croatian. All code names (files, snippets, classes, settings, locale keys) are English.
> **Scope:** Liquid, CSS and locale changes to the theme **only**. The data already exists; this task only **reads** it and **displays** it.

---

## 1. Context

### 1.1 The law, in short

A Croatian Government decision, *Odluka o isticanju dodatne cijene kao mjera izravne kontrole cijena* (NN 101/2026-1212), takes effect on **1 October 2026**. Traders must show an extra price next to the current retail price. The decision calls it the *dodatna cijena*; everyone else calls it the **sidrena cijena**, or anchor price.

- **What it is:** the regular retail price on the **reference date 10. 9. 2026.**
  - A product first listed **after** that date uses its **first listing price and that date**.
  - A product that was on a **temporary sale** on 10. 9. uses its **regular price before the sale**.
- **How:** the decision says *"jasno, vidljivo i čitljivo uz maloprodajnu cijenu"*: clearly, visibly and legibly, **next to** the retail price. The shopper must see both prices together, without clicking, hovering or opening another page.
- **Where:** at the point of sale and in advertising, including digital forms and websites. For a webshop, the conservative reading is that **wherever the theme shows a product's price to a shopper, the anchor price appears next to it.**
- **Wording:** no exact label is prescribed. We use `Sidrena cijena na dan {date}: {amount}`.
- **Always shown:** it appears **even when it equals the current price**. It is not a discount claim and is never hidden because it matches.

### 1.2 Where the data comes from (already done; don't change)

Shopify Flow fills two **variant** metafields, and Mario sometimes corrects them by hand in the admin:

| Metafield | Type | Liquid access | Liquid returns |
|---|---|---|---|
| `pricing.anchor_price` | Money (one value) | `variant.metafields.pricing.anchor_price.value` | a **money object** in the customer's presentment currency; format it with the `money` filters |
| `pricing.anchor_price_date` | Date (one value) | `variant.metafields.pricing.anchor_price_date.value` | a date string `YYYY-MM-DD`; format it with the `date` filter |

- A variant **can have no anchor price**: a brand-new variant before the next hourly Flow run, a draft product, a gift card. The theme must then render **nothing** (no empty wrapper, no gap).
- **Never** compute, derive or hard-code an anchor price or date in the theme: no compare-at fallback and no "price on 10.9." constant for amounts. The theme is display-only. The single exception is the date fallback in §3.2.

---

## 2. Required outcome

| # | Where | Required? | What to show |
|---|---|---|---|
| A | **Product page, main price** (`main-product` or equivalent) | **Required** | The anchor price of the **currently selected variant**, updated on variant change |
| B | **Product cards:** collection grid, search results, product recommendations, featured collection, "related" or "recently viewed" if they show a price | **Required** (conservative reading) | The anchor price matching the price shape shown on the card (see §4.3) |
| C | **Featured product section and quick view**, if the theme has them | **Required**, if a price is shown | Same as A |
| D | **Predictive search results**, if they show a price | **Required**, if a price is shown | Same as B |
| E | Cart page and cart drawer line items | **Optional. Ask Mario before doing it.** | The anchor price of `item.variant` |
| F | Checkout, order emails, JSON-LD structured data, feeds | **Out of scope. Don't touch.** | — |

**Output format** (Croatian store locale):

```
62,00 €
Sidrena cijena na dan 10. 9. 2026.: 62,00 €
```

The amount uses **exactly the same money filter** as the retail price it sits next to (`money`, `money_with_currency`, `money_without_trailing_zeros`…), so both prices are formatted identically.

---

## 3. Implementation

### 3.0 Before editing, map the theme and report back

Find and list (file plus line) for Mario before changing anything:

1. **Every place a product price is rendered.** Search for `| money`, `price`, `render 'price'`, `compare_at_price`, `price_min`, `price_varies`. Many themes have one shared `snippets/price.liquid` (or similar) used by the product page and the cards. **If one exists, integrate there once**, gated by a parameter so it only shows in the contexts from §2.
2. **How variant changes update the product page.** If the theme uses the **Section Rendering API** (most modern themes do), find the JS that fetches `?section_id=` / `?sections=` with `variant=`, and find **which DOM node(s) it swaps** (for example `#price-{{ section.id }}`). The anchor markup must live **inside a swapped node**, or it will go stale on variant change.
3. **The theme's string handling.** Which locale file is the default (`locales/hr.default.json`? `en.default.json` plus `hr.json`?), or are strings hard-coded in Croatian? Follow the theme's existing convention.
4. **The theme's CSS convention.** Where price styles live (a section CSS file, `base.css`, `{% stylesheet %}` in snippets…).

Then propose the exact insertion points and **wait for Mario's OK**.

### 3.1 Theme setting (kill switch)

Add to `config/settings_schema.json`, as a new group or inside the existing product/price group:

```json
{
  "name": "Anchor price",
  "settings": [
    {
      "type": "checkbox",
      "id": "show_anchor_price",
      "label": "Show anchor price (sidrena cijena)",
      "default": true,
      "info": "Croatian law (NN 101/2026-1212): shows the regular price on the reference date next to the product price. Keep on while the measure is in force."
    }
  ]
}
```

### 3.2 Snippet: `snippets/anchor-price.liquid`

This is the single source of truth. Every placement renders this snippet, and nothing else outputs anchor markup.

```liquid
{%- comment -%}
  snippets/anchor-price.liquid
  Croatian "sidrena cijena" (dodatna cijena, NN 101/2026-1212), shown next to a retail price.
  Reads variant metafields pricing.anchor_price (money) and pricing.anchor_price_date (date).

  Params:
    variant      (required) variant whose anchor price is shown (the lower end, if a range)
    variant_max  (optional) variant at the upper end of a price range (cards showing "min – max")
    from         (optional, boolean) true when the adjacent price is a "from" price ("od 9,50 €")
    money_format (optional) 'money' (default) | 'money_with_currency' | 'money_without_trailing_zeros'.
                 MUST match the filter used for the adjacent retail price.
    class        (optional) extra CSS classes

  Renders nothing when: the setting is off, the variant is blank, the product is a gift card,
  or the variant has no anchor price.

  Usage:
    Product page: {% render 'anchor-price', variant: product.selected_or_first_available_variant %}
    Card, single: {% render 'anchor-price', variant: card_variant %}
    Card, from:   {% render 'anchor-price', variant: min_variant, from: true %}
    Card, range:  {% render 'anchor-price', variant: min_variant, variant_max: max_variant %}
{%- endcomment -%}

{%- liquid
  assign show = false
  if settings.show_anchor_price != false and variant != blank and variant.product.gift_card? != true
    assign anchor = variant.metafields.pricing.anchor_price.value
    if anchor != blank
      assign show = true
    endif
  endif

  if show
    # Fallback only if the price was entered by hand without a date. 2026-09-10 is the legal reference date.
    assign anchor_date = variant.metafields.pricing.anchor_price_date.value | default: '2026-09-10'
    assign date_label = anchor_date | date: '%-d. %-m. %Y.'

    assign is_range = false
    assign show_from = false
    if from == true
      assign show_from = true
    endif

    if variant_max != blank and variant_max.id != variant.id
      assign anchor_max = variant_max.metafields.pricing.anchor_price.value
      assign date_max = variant_max.metafields.pricing.anchor_price_date.value | default: '2026-09-10'
      # A range is only honest if both ends have an anchor price and share the same date; otherwise fall back to "from".
      if anchor_max != blank and date_max == anchor_date
        assign is_range = true
      else
        assign show_from = true
      endif
    endif

    case money_format
      when 'money_with_currency'
        assign amount = anchor | money_with_currency
        if is_range
          assign amount_max = anchor_max | money_with_currency
        endif
      when 'money_without_trailing_zeros'
        assign amount = anchor | money_without_trailing_zeros
        if is_range
          assign amount_max = anchor_max | money_without_trailing_zeros
        endif
      else
        assign amount = anchor | money
        if is_range
          assign amount_max = anchor_max | money
        endif
    endcase

    assign css_class = 'anchor-price'
    if class != blank
      assign css_class = css_class | append: ' ' | append: class
    endif
  endif
-%}

{%- if show -%}
  <p class="{{ css_class }}" data-anchor-price>
    <span class="anchor-price__label">{{ 'products.product.anchor_price.label' | t: date: date_label }}</span>
    <span class="anchor-price__value">
      {%- if is_range -%}
        {{ amount }} – {{ amount_max }}
      {%- elsif show_from -%}
        {{ 'products.product.anchor_price.from' | t }} {{ amount }}
      {%- else -%}
        {{ amount }}
      {%- endif -%}
    </span>
  </p>
{%- endif -%}
```

**Notes for the implementer:**
- **Pre-tested:** this snippet was checked with open-source Liquid 5.5 (Shopify's `blank` semantics emulated, `money` and `t` mocked) across 15 cases: single, new-product date, no anchor, missing date, gift card, setting off, from, range with same date / different date / missing max, money formats, extra class, blank variant. It still needs the real-store checks in §6.
- **Date filter output:** `'%-d. %-m. %Y.'` gives `10. 9. 2026.`, the standard Croatian format. The shop's timezone is Europe/Zagreb, so a date-only string doesn't shift a day. **Verify the rendered output** on a real product anyway.
- **Money filters:** `money` and its variants accept the money object that a money metafield returns. Don't do arithmetic on it (`plus`, `divided_by`…); it isn't needed here.
- **Adapting to the theme:** if the theme passes the product differently (for example `card_product`), keep the snippet's API as it is and adapt at the call site.

### 3.3 Locale strings

Add to the theme's **default** locale (Croatian text), and to any other locales that exist. Match the existing JSON nesting.

```json
"products": {
  "product": {
    "anchor_price": {
      "label": "Sidrena cijena na dan {{ date }}:",
      "from": "od"
    }
  }
}
```

The English locale, if present, gets `"label": "Price on {{ date }}:"` and `"from": "from"`.

If the theme hard-codes Croatian strings instead of using locales, follow that convention. Still keep the label in **one** place, the snippet, and never duplicate it at the call sites.

### 3.4 CSS (legal: "clearly, visibly, legibly")

Put this in the theme's existing price CSS location:

```css
.anchor-price {
  margin: 0.25rem 0 0;
  font-size: max(14px, 0.875em); /* never below 14px, also in themes with a 62.5% root font size */
  line-height: 1.4;
  color: inherit; /* body text colour; must meet WCAG AA 4.5:1 contrast */
  text-decoration: none; /* NEVER strike through: it's not a "was" price */
}
.anchor-price__value { white-space: nowrap; }
```

Rules:
- **No strikethrough, no discount styling.** It's not a former price or a sale badge. Styling it like one would make it look like a discount claim.
- **Nothing that hides it:** no light grey below 4.5:1 contrast, no text under 14px, no hiding on mobile, no tooltip or accordion or hover reveal.
- **Placement:** directly **below or next to** the retail price, inside the same price container. It's fine to put it after compare-at and sale badges, but it must stay visually attached to the price.

---

## 4. Placements

### 4.1 Product page (A, C)

- Render **inside the node the Section Rendering API swaps on variant change**, usually the price container:
  ```liquid
  {% render 'anchor-price', variant: product.selected_or_first_available_variant %}
  ```
- `product.selected_or_first_available_variant` respects `?variant=`, so the section render for a new variant contains that variant's anchor. **No JS changes should be needed.** If the theme swaps only an inner node (for example `.price__regular`), move the render inside that node, or add the anchor's wrapper to the list of swapped selectors, following the theme's pattern.
- **If there's no price block:** if the product page uses blocks and the price is a block, render it inside the price block and not as a separate block. The merchant must not be able to remove or move it away from the price.
- **Quick view and featured product:** same approach, in whichever node they re-render on variant change.

### 4.2 Cart (E): optional, only if Mario says yes

```liquid
{% render 'anchor-price', variant: item.variant, class: 'anchor-price--cart' %}
```

The cart drawer usually re-renders through the Section Rendering API after a cart change, so render it inside the re-rendered node.

### 4.3 Product cards (B, D): mirror the card's price shape

The anchor must describe **the same variant(s)** as the price the card displays. Find out how the card renders its price, then pass matching variants.

```liquid
{%- liquid
  # Pick variants whose current price matches what the card shows.
  # Integer comparisons on price only: safe, no money math on metafields.
  assign min_variant = card_product.selected_or_first_available_variant
  assign max_variant = blank
  if card_product.price_varies
    for v in card_product.variants
      if v.price == card_product.price_min
        assign min_variant = v
        break
      endif
    endfor
    for v in card_product.variants
      if v.price == card_product.price_max
        assign max_variant = v
      endif
    endfor
  endif
-%}
```

| Card shows… | Render |
|---|---|
| a single price (`price_varies` false) | `{% render 'anchor-price', variant: min_variant %}` |
| "od 9,50 €" (from price) | `{% render 'anchor-price', variant: min_variant, from: true %}` |
| "9,50 € – 12,00 €" (range) | `{% render 'anchor-price', variant: min_variant, variant_max: max_variant %}` |
| the selected or first variant's price | `{% render 'anchor-price', variant: card_product.selected_or_first_available_variant %}` |

Use the card's actual product variable name (`card_product`, `product`, `item`…).

---

## 5. Don'ts

- Don't change the metafield definitions, the Flow workflows, or any metafield values.
- Don't hard-code anchor amounts. The only hard-coded date is the fallback in the snippet.
- Don't use compare-at price as a stand-in for a missing anchor price. **Missing means render nothing.**
- Don't add the anchor price to JSON-LD / `Offer` structured data, `og:` / meta tags, or feeds.
- Don't touch the price-list template (`templates/collection.price-list.liquid`) if it exists. That's a separate part of the kit.
- Don't hide the anchor price when it equals the current price.
- Don't push to the **live** theme. Work on a copy or preview (`shopify theme dev` or an unpublished theme); Mario publishes.
- Don't add JS unless the theme's variant update genuinely can't carry the markup, and ask Mario first.

---

## 6. Acceptance criteria and test plan

`shopify theme check` must pass with no new errors or warnings.

**Reference data.** Before starting, Mario fills in 3–4 real products of this store, taken from
the admin (variant fields **Anchor price** and **Anchor price date**). Include at least one product
on sale (compare-at above price), one without compare-at, and one multi-variant product:

| Handle | Current price | Compare-at | Anchor price | Anchor date | Expected line |
|---|---|---|---|---|---|
| `…` | … | … | … | … | `Sidrena cijena na dan 10. 9. 2026.: … €` |
| `…` | … | — | … | … | `Sidrena cijena na dan 10. 9. 2026.: … €` |
| `…` (variant A / B) | … | … | … | … | changes with the selected variant |
| any draft product (preview) | — | — | — | — | nothing rendered |

**Checklist:**
- [ ] **Product page, single-variant product:** the line appears directly under the price, formatted exactly like the retail price (decimal comma, € position).
- [ ] **Product page, multi-variant product:** changing the variant updates the anchor price in the same render as the price. Check the Network tab: the section response for `?variant=<id>` contains that variant's `data-anchor-price` markup.
- [ ] **Deep link:** `/products/<handle>?variant=<id>` shows that variant's anchor on first load.
- [ ] **A variant with no anchor price:** nothing rendered, no empty `<p>`, no extra spacing. Test by temporarily clearing the value on a draft product, not a live one.
- [ ] **Collection page, search results, recommendations, featured collection:** every card with a price has the line, and range or "from" cards mirror the price shape.
- [ ] **Predictive search, quick view, featured product:** present wherever a price is shown.
- [ ] **Theme setting off:** the anchor price disappears everywhere. Setting on: back everywhere.
- [ ] **Mobile, 360px wide:** readable, not truncated, doesn't overlap the price, and no layout shift.
- [ ] **Contrast:** 4.5:1 or better against the background, and font size 14px or larger.
- [ ] **No strikethrough** anywhere on `.anchor-price`.
- [ ] **Other currencies:** if the store has other markets or currencies, the anchor price converts the same way the retail price does. Presentment currency is handled by Shopify.
- [ ] **Unaffected:** JSON-LD, meta tags and price-list templates are unchanged (diff check).

---

## 7. Deliverables

1. `snippets/anchor-price.liquid`, new.
2. Render calls at every placement from §2 (A–D, plus E if approved), ideally one call inside a shared price snippet.
3. `config/settings_schema.json`: the `show_anchor_price` setting.
4. Locale keys `products.product.anchor_price.label` and `.from`.
5. CSS for `.anchor-price`.
6. A short summary for Mario:
   - every file touched, with the reason
   - the placements covered and any skipped, with why
   - anything that needs his decision

**Deadline:** live on the storefront before **1. 10. 2026.**
