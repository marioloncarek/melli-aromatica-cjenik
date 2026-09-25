"""
A tiny fake Shopify storefront for tests.

It serves /collections/all?view=price-list&page=N exactly the way the theme template
collection.price-list.liquid does: every page starts with the header line, lists up to
250 products (one line per variant; gift cards skipped) and ends with the '#meta' line.

Behaviour switches (attributes of FakeShopify) let tests simulate problems:
  password          every request redirects to /password
  fail_first        the first N requests answer HTTP `fail_status` (default 503)
  html_instead      answer an HTML page (template missing / bot challenge)
  status_override   answer this HTTP status for every request (e.g. 404)
  with_meta         False = old template without the '#meta' line
  currency, country, taxes_included, truncated   values reported in the '#meta' line
  report_items      report this total instead of the real number of products
  page_offset       report page N + offset in the '#meta' line
  on_request        callback(fake, page) run before a page is rendered (e.g. add products mid-run)
"""
from __future__ import annotations

import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HEADER_LINE = (
    "naziv;sifra;marka;jedinica_mjere;cijena_za_jedinicu_mjere;maloprodajna_cijena;"
    "posebni_oblik_prodaje;naziv_posebnog_oblika_prodaje;sidrena_cijena;barkod;dostupnost"
)
PAGE_SIZE = 250


def money(cents: int | None) -> str:
    if cents is None:
        return ""
    return f"{cents // 100},{cents % 100:02d}"


def q(text: str) -> str:
    return '"' + text.replace('"', '""') + '"'


def make_products(
    count: int, multi_every: int = 0, variants_per_multi: int = 3, sale_every: int = 0, gift_every: int = 0
) -> list[dict]:
    """`count` products; every `multi_every`-th has several variants, every `sale_every`-th is on sale,
    every `gift_every`-th is a gift card."""
    products = []
    for i in range(1, count + 1):
        n_variants = variants_per_multi if multi_every and i % multi_every == 0 else 1
        on_sale = bool(sale_every and i % sale_every == 0)
        variants = []
        for v in range(1, n_variants + 1):
            price = 500 + (i * 37 + v * 11) % 9000
            variants.append(
                {
                    "title": "Default Title" if n_variants == 1 else f"Size {v}",
                    "sku": f"SKU-{i:05d}-{v}",
                    "price": price - 100 if on_sale else price,
                    "compare_at": price if on_sale else None,
                    "anchor": price,
                    "available": (i + v) % 7 != 0,
                }
            )
        products.append(
            {
                "title": f"Product {i:05d}",
                "vendor": "Brand",
                "variants": variants,
                "gift_card": bool(gift_every and i % gift_every == 0),
            }
        )
    return products


def render_rows(product: dict, sale_name: str = "Akcija") -> list[str]:
    rows = []
    for v in product["variants"]:
        name = product["title"] if v["title"] == "Default Title" else f"{product['title']} - {v['title']}"
        on_sale = v["compare_at"] is not None and v["compare_at"] > v["price"]
        rows.append(
            ";".join(
                [
                    q(name),
                    q(v["sku"]),
                    q(product["vendor"]),
                    q(v.get("unit", "")),
                    money(v.get("unit_price")),
                    money(v["price"]),
                    "DA" if on_sale else "NE",
                    q(sale_name if on_sale else ""),
                    money(v["anchor"]),
                    q(v.get("barcode", "")),
                    "dostupno" if v["available"] else "nedostupno",
                ]
            )
        )
    return rows


class FakeShopify:
    def __init__(self, products: list[dict] | None = None):
        self.products = products or []
        self.password = False
        self.fail_first = 0
        self.fail_status = 503
        self.html_instead = False
        self.status_override: int | None = None
        self.with_meta = True
        self.currency = "EUR"
        self.country = "HR"
        self.taxes_included = "true"
        self.truncated = 0
        self.report_items: int | None = None
        self.page_offset = 0
        self.on_request = None
        self.requests: list[str] = []
        self.cookies: list[str] = []
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # -- page rendering -------------------------------------------------------------
    def page_body(self, page: int) -> str:
        items = self.report_items if self.report_items is not None else len(self.products)
        pages = -(-items // PAGE_SIZE)
        start = (page - 1) * PAGE_SIZE
        chunk = self.products[start:start + PAGE_SIZE] if page >= 1 else []
        rows, listed, skipped = [], 0, 0
        for product in chunk:
            if product.get("gift_card"):
                skipped += 1
                continue
            listed += 1
            rows.extend(render_rows(product))
        body = HEADER_LINE + "\n" + "".join(r + "\n" for r in rows)
        if self.with_meta:
            body += (
                f"#meta;page={page + self.page_offset};pages={pages};items={items};listed={listed};"
                f"skipped={skipped};truncated={self.truncated};currency={self.currency};"
                f"country={self.country};taxes_included={self.taxes_included}\n"
            )
        return body

    # -- server ---------------------------------------------------------------------
    def start(self) -> str:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # keep test output clean
                pass

            def do_GET(self):
                fake.requests.append(self.path)
                fake.cookies.append(self.headers.get("Cookie", ""))
                parsed = urllib.parse.urlparse(self.path)
                params = urllib.parse.parse_qs(parsed.query)
                if parsed.path == "/password":
                    self._send(200, "<html>Password</html>", "text/html")
                    return
                if fake.password:
                    self.send_response(302)
                    self.send_header("Location", "/password")
                    self.end_headers()
                    return
                if fake.fail_first > 0:
                    fake.fail_first -= 1
                    self._send(fake.fail_status, "Service unavailable", "text/plain")
                    return
                if fake.status_override:
                    self._send(fake.status_override, "error", "text/plain")
                    return
                if parsed.path != "/collections/all" or params.get("view") != ["price-list"]:
                    self._send(404, "not found", "text/plain")
                    return
                if fake.html_instead:
                    self._send(200, "<!doctype html><html><body>Collection</body></html>", "text/html")
                    return
                page = int(params.get("page", ["1"])[0])
                if fake.on_request:
                    fake.on_request(fake, page)
                self._send(200, fake.page_body(page), "text/html; charset=utf-8")

            def _send(self, status: int, body: str, content_type: str):
                data = body.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
