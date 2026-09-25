"""
Tests for scripts/build_price_list.py against a fake Shopify storefront.

Run:  python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import contextlib
import csv
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_shopify import HEADER_LINE, FakeShopify, make_products  # noqa: E402

spec = importlib.util.spec_from_file_location("build_price_list", ROOT / "scripts" / "build_price_list.py")
bpl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bpl)

BASE_CONFIG = {
    "store_name": "Test Store",
    "company_name": "Test d.o.o.",
    "company_oib": "12345678901",
    "domain": "www.test-store.hr",
    "address": "Ilica 150, 10000 Zagreb",
    "premises_label": "WEB01",
    "first_day": "2026-10-01",
    "request_delay_seconds": 0,
    "retries": 3,
}
GO_LIVE = "2026-10-01T04:17:00+02:00"


class PriceListTestCase(unittest.TestCase):
    products = 16

    def setUp(self):
        patcher = mock.patch.object(bpl.time, "sleep", lambda seconds: None)  # no real waiting
        patcher.start()
        self.addCleanup(patcher.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.site = self.dir / "site"
        self.shop = FakeShopify(make_products(self.products))
        self.base_url = self.shop.start()
        self.addCleanup(self.shop.stop)
        self.write_config()

    def write_config(self, **overrides):
        cfg = dict(BASE_CONFIG)
        cfg.update(overrides)
        (self.dir / "config.json").write_text(json.dumps(cfg), encoding="utf-8")

    def run_build(self, now: str = GO_LIVE, *extra: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = bpl.main(
                [
                    "--config",
                    str(self.dir / "config.json"),
                    "--site-dir",
                    str(self.site),
                    "--base-url",
                    self.base_url,
                    "--now",
                    now,
                    *extra,
                ]
            )
        return code, out.getvalue()

    def manifest(self) -> dict:
        return json.loads((self.site / "manifest.json").read_text(encoding="utf-8"))

    def files(self) -> list[str]:
        folder = self.site / "files"
        return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


class SmallStoreTests(PriceListTestCase):
    def test_publishes_single_page_store(self):
        code, log = self.run_build()
        self.assertEqual(code, 0, log)
        base = "internetska-trgovina_Ilica-150-10000-Zagreb_WEB01_1_01.10.2026_04.17"
        self.assertEqual(self.files(), [f"{base}.csv", f"{base}.xml"])
        csv_text = (self.site / "files" / f"{base}.csv").read_text(encoding="utf-8")
        lines = csv_text.split("\n")
        self.assertEqual(lines[0], HEADER_LINE)
        self.assertEqual(len(lines), 16 + 2)  # header + 16 rows + trailing empty after final newline
        self.assertEqual(lines[-1], "")
        self.assertNotIn("\r", csv_text)
        self.assertNotIn("#meta", csv_text)  # the control line is never published
        self.assertEqual((self.site / "latest.csv").read_text(encoding="utf-8"), csv_text)
        entry = self.manifest()["entries"][0]
        self.assertEqual((entry["number"], entry["rows"], entry["time"]), (1, 16, "04:17"))
        index = (self.site / "index.html").read_text(encoding="utf-8")
        self.assertIn(f"files/{base}.csv", index)
        self.assertIn("Oznaka poslovnog prostora: WEB01", index)
        self.assertIn("OIB: 12345678901", index)
        self.assertIn("manifest.json", index)
        self.assertEqual((self.site / "robots.txt").read_text(encoding="utf-8"), "User-agent: *\nAllow: /\n")

    def test_requests_croatian_market_in_eur(self):
        self.run_build()
        self.assertTrue(self.shop.cookies)
        self.assertTrue(all(c == "localization=HR; cart_currency=EUR" for c in self.shop.cookies))
        self.assertTrue(all("sort_by=created-ascending" in r for r in self.shop.requests))

    def test_xml_matches_csv(self):
        self.run_build()
        csv_rows = list(csv.reader(io.StringIO((self.site / "latest.csv").read_text(encoding="utf-8")), delimiter=";"))
        root = ElementTree.fromstring((self.site / "latest.xml").read_bytes())
        products = root.findall("proizvod")
        self.assertEqual(root.tag, "cjenik")
        self.assertEqual(len(products), len(csv_rows) - 1)
        for row, element in zip(csv_rows[1:], products, strict=True):
            self.assertEqual(element.findtext("naziv"), row[0])
            self.assertEqual(element.findtext("maloprodajna_cijena"), row[5].replace(",", "."))
            self.assertEqual(element.findtext("sidrena_cijena"), row[8].replace(",", "."))
            self.assertEqual(element.findtext("dostupnost"), row[10])

    def test_same_day_second_run_does_nothing(self):
        self.run_build()
        before = self.files()
        requests_before = len(self.shop.requests)
        code, log = self.run_build("2026-10-01T05:47:00+02:00")
        self.assertEqual(code, 0)
        self.assertIn("Already published today", log)
        self.assertEqual(self.files(), before)
        self.assertEqual(len(self.shop.requests), requests_before)  # store not contacted again

    def test_force_replaces_todays_files(self):
        self.run_build()
        code, log = self.run_build("2026-10-01T09:05:00+02:00", "--force")
        self.assertEqual(code, 0, log)
        self.assertEqual(len(self.files()), 2)
        self.assertTrue(all("_1_01.10.2026_09.05." in name for name in self.files()))
        self.assertEqual(len(self.manifest()["entries"]), 1)

    def test_before_first_day_checks_but_publishes_nothing(self):
        code, log = self.run_build("2026-09-25T04:17:00+02:00")
        self.assertEqual(code, 0, log)
        self.assertIn("Not live yet", log)
        self.assertIn("16 rows", log)
        self.assertTrue(self.shop.requests)  # the store IS checked before go-live
        self.assertEqual(self.files(), [])
        self.assertFalse((self.site / "manifest.json").exists())
        self.assertFalse((self.site / "latest.csv").exists())
        index = (self.site / "index.html").read_text(encoding="utf-8")
        self.assertIn("Objava cjenika počinje 1. 10. 2026.", index)
        self.assertNotIn("manifest.json", index)

    def test_before_first_day_broken_template_fails(self):
        self.shop.html_instead = True
        code, log = self.run_build("2026-09-25T04:17:00+02:00")
        self.assertEqual(code, 1, log)
        self.assertIn("expected CSV header", log)

    def test_dry_run_writes_nothing(self):
        code, log = self.run_build(GO_LIVE, "--dry-run")
        self.assertEqual(code, 0, log)
        self.assertIn("Dry run", log)
        self.assertFalse(self.site.exists())
        code, log = self.run_build("2026-09-25T04:17:00+02:00", "--dry-run")
        self.assertEqual(code, 0, log)
        self.assertIn("checked", log)
        self.assertFalse(self.site.exists())

    def test_dry_run_on_published_day_still_checks(self):
        self.run_build()
        before = (len(self.shop.requests), self.files(), self.manifest())
        code, log = self.run_build("2026-10-01T06:00:00+02:00", "--dry-run")
        self.assertEqual(code, 0, log)
        self.assertNotIn("Already published today", log)
        self.assertIn("Dry run", log)
        self.assertGreater(len(self.shop.requests), before[0])  # the store was fetched again
        self.assertEqual((self.files(), self.manifest()), (before[1], before[2]))  # nothing changed

    def test_storage_number_and_dst(self):
        # summer time (UTC+2) until 25 Oct 2026 03:00, winter time (UTC+1) after that
        self.run_build("2026-10-01T04:17:00+02:00")
        self.run_build("2026-10-25T04:17:00+01:00")  # already winter time at 04:17 on 25 Oct
        self.run_build("2026-10-26T03:17:00+01:00")
        numbers = {e["date"]: (e["number"], e["time"]) for e in self.manifest()["entries"]}
        self.assertEqual(numbers["2026-10-01"], (1, "04:17"))
        self.assertEqual(numbers["2026-10-25"], (25, "04:17"))
        self.assertEqual(numbers["2026-10-26"], (26, "03:17"))
        self.assertIn(
            "internetska-trgovina_Ilica-150-10000-Zagreb_WEB01_26_26.10.2026_03.17.csv", self.files()
        )

    def test_utc_time_is_converted_to_zagreb(self):
        code, log = self.run_build("2026-10-01T02:17:00+00:00")  # 04:17 in Zagreb
        self.assertEqual(code, 0, log)
        self.assertTrue(all("_01.10.2026_04.17." in name for name in self.files()))

    def test_archive_keeps_at_least_31_days(self):
        self.write_config(keep_days=5)  # below the legal minimum: raised to 31
        for day in range(1, 41):  # 1 Oct .. 9 Nov
            month, dom = (10, day) if day <= 31 else (11, day - 31)
            offset = "+02:00" if (month, dom) < (10, 25) else "+01:00"
            code, log = self.run_build(f"2026-{month:02d}-{dom:02d}T04:17:00{offset}")
            self.assertEqual(code, 0, log)
        entries = self.manifest()["entries"]
        self.assertEqual(len(entries), 32)  # today + 31 previous days
        self.assertEqual(entries[0]["date"], "2026-11-09")
        self.assertEqual(entries[-1]["date"], "2026-10-09")
        self.assertEqual(len(self.files()), 64)
        self.assertEqual([e["date"] for e in entries], sorted((e["date"] for e in entries), reverse=True))

    def test_reset_archive(self):
        self.write_config(first_day="2026-09-24")
        self.run_build("2026-09-24T21:00:00+02:00")
        self.assertEqual(len(self.files()), 2)
        self.write_config(first_day="2026-10-01")
        code, log = self.run_build("2026-09-25T04:17:00+02:00", "--reset-archive")
        self.assertEqual(code, 0, log)
        self.assertEqual(self.files(), [])
        self.assertFalse((self.site / "latest.csv").exists())
        self.assertFalse((self.site / "manifest.json").exists())
        code, log = self.run_build()
        self.assertEqual(code, 0, log)
        self.assertEqual(self.manifest()["entries"][0]["number"], 1)

    def test_orphan_files_are_removed(self):
        self.run_build()
        stray = self.site / "files" / "old-test-file.csv"
        stray.write_text("x", encoding="utf-8")
        self.run_build("2026-10-02T04:17:00+02:00")
        self.assertFalse(stray.exists())
        self.assertEqual(len(self.files()), 4)

    def test_csv_bom_option(self):
        self.write_config(csv_bom=True)
        self.run_build()
        raw = (self.site / "latest.csv").read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        self.assertTrue((self.site / "latest.xml").read_bytes().startswith(b"<?xml"))

    def test_gift_cards_counted_but_not_listed(self):
        self.shop.products = make_products(40, gift_every=10)  # 4 gift cards
        code, log = self.run_build()
        self.assertEqual(code, 0, log)
        self.assertEqual(self.manifest()["entries"][0]["rows"], 36)


class LargeStoreTests(PriceListTestCase):
    def setUp(self):
        super().setUp()
        self.shop.products = make_products(1234, multi_every=10, variants_per_multi=3, sale_every=7)
        self.expected_rows = sum(len(p["variants"]) for p in self.shop.products)

    def test_fetches_all_pages(self):
        code, log = self.run_build()
        self.assertEqual(code, 0, log)
        self.assertIn("from 5 page(s)", log)
        text = (self.site / "latest.csv").read_text(encoding="utf-8")
        rows = text.strip("\n").split("\n")
        self.assertEqual(rows.count(HEADER_LINE), 1)
        self.assertEqual(len(rows) - 1, self.expected_rows)
        self.assertEqual(len(set(rows)), len(rows))  # no duplicates
        self.assertTrue(rows[1].startswith('"Product 00001"'))
        self.assertTrue(rows[-1].startswith('"Product 01234'))
        entry = self.manifest()["entries"][0]
        self.assertEqual(entry["rows"], self.expected_rows)
        expected_sale = sum(1 for i in range(1, 1235) if i % 7 == 0 for _ in range(3 if i % 10 == 0 else 1))
        self.assertEqual(entry["on_sale"], expected_sale)
        self.assertEqual(len(self.shop.requests), 5)  # exactly the 5 pages the store reports

    def test_catalog_change_during_run_is_retried(self):
        state = {"added": False}

        def add_product_after_page_2(fake, page):
            if page == 3 and not state["added"]:
                state["added"] = True
                fake.products = fake.products + make_products(1)  # one new product appears mid-run

        self.shop.on_request = add_product_after_page_2
        code, log = self.run_build()
        self.assertEqual(code, 0, log)
        self.assertIn("fetching all pages again", log)
        self.assertEqual(self.manifest()["entries"][0]["rows"], self.expected_rows + 1)
        cache_busters = {r.split("cb=")[1] for r in self.shop.requests}
        self.assertEqual(len(cache_busters), 2)  # the retry pass uses a new cache buster

    def test_catalog_that_keeps_changing_fails(self):
        def add_product_every_time(fake, page):
            if page == 2:
                fake.products = fake.products + make_products(1)

        self.shop.on_request = add_product_every_time
        code, log = self.run_build()
        self.assertEqual(code, 1, log)
        self.assertIn("twice in a row", log)
        self.assertEqual(self.files(), [])

    def test_row_drop_guard(self):
        self.run_build()
        self.shop.products = self.shop.products[:300]
        code, log = self.run_build("2026-10-02T04:17:00+02:00")
        self.assertEqual(code, 1)
        self.assertIn("more than 50% fewer", log)
        self.assertEqual(len(self.manifest()["entries"]), 1)
        code, log = self.run_build("2026-10-02T09:00:00+02:00", "--force")
        self.assertEqual(code, 0, log)
        self.assertEqual(len(self.manifest()["entries"]), 2)


class FailureTests(PriceListTestCase):
    def assert_fails(self, expected_text: str, *extra: str):
        code, log = self.run_build(GO_LIVE, *extra)
        self.assertEqual(code, 1, log)
        self.assertIn("::error", log)
        self.assertIn(expected_text, log)
        self.assertEqual(self.files(), [])
        self.assertFalse((self.site / "latest.csv").exists())
        return log

    def test_password_protected_store(self):
        self.shop.password = True
        self.assert_fails("password-protected")

    def test_template_missing_returns_html(self):
        self.shop.html_instead = True
        self.assert_fails("does not start with the expected CSV header")

    def test_old_template_without_meta(self):
        self.shop.with_meta = False
        self.assert_fails("no '#meta' control line")

    def test_wrong_currency(self):
        self.shop.currency, self.shop.country = "USD", "US"
        self.assert_fails("currency 'USD'")

    def test_wrong_country(self):
        self.shop.country = "US"  # EUR, but another market (could have price adjustments)
        self.assert_fails("country 'US'")

    def test_wrong_country_allowed_by_config(self):
        self.shop.country = "US"
        self.write_config(require_country_match=False)
        code, log = self.run_build()
        self.assertEqual(code, 0, log)

    def test_prices_without_vat(self):
        self.shop.taxes_included = "false"
        self.assert_fails("WITHOUT VAT")

    def test_prices_without_vat_allowed_by_config(self):
        self.shop.taxes_included = "false"
        self.write_config(require_taxes_included=False)
        code, log = self.run_build()
        self.assertEqual(code, 0, log)

    def test_unknown_vat_mode_warns_once_even_after_a_retry(self):
        self.shop.taxes_included = ""

        def wrong_total_on_first_request(fake, page):  # the first pass fails the totals check -> retry
            fake.report_items = 17 if len(fake.requests) == 1 else None

        self.shop.on_request = wrong_total_on_first_request
        code, log = self.run_build()
        self.assertEqual(code, 0, log)
        self.assertIn("fetching all pages again", log)
        self.assertEqual(log.count("::warning title=Price list::Could not verify that prices include VAT"), 1)

    def test_truncated_variants(self):
        self.shop.truncated = 1
        self.assert_fails("more variants than Shopify's Liquid can list")

    def test_more_than_25000_products(self):
        self.shop.report_items = 25_001
        self.assert_fails("pagination stops at 25,000")

    def test_more_pages_than_max_pages(self):
        self.shop.products = make_products(800)  # 4 pages
        self.write_config(max_pages=3)
        self.assert_fails("max_pages is 3")

    def test_page_number_mismatch(self):
        self.shop.page_offset = 1
        self.assert_fails("Requested page 1 but the store answered page 2")

    def test_404(self):
        self.shop.status_override = 404
        self.assert_fails("HTTP 404")

    def test_persistent_503(self):
        self.shop.status_override = 503
        self.assert_fails("after 3 attempts")

    def test_transient_503_is_retried(self):
        self.shop.fail_first = 2
        code, log = self.run_build()
        self.assertEqual(code, 0, log)
        self.assertIn("HTTP 503 on attempt 1/3", log)
        self.assertEqual(len(self.files()), 2)

    def test_transient_520_is_retried(self):
        self.shop.fail_first, self.shop.fail_status = 1, 520
        code, log = self.run_build()
        self.assertEqual(code, 0, log)
        self.assertIn("HTTP 520 on attempt 1/3", log)

    def test_empty_store(self):
        self.shop.products = []
        self.assert_fails("0 products")

    def test_invalid_price_format(self):
        original = self.shop.page_body
        self.shop.page_body = lambda page: original(page).replace(";6,", ";6.", 1)
        self.shop.products[0]["variants"][0]["price"] = 612
        self.assert_fails("Invalid retail price")

    def test_wrong_column_count(self):
        original = self.shop.page_body
        self.shop.page_body = lambda page: original(page).replace(";dostupno\n", ";dostupno;extra\n", 1)
        self.assert_fails("Expected 11 columns")

    def test_missing_anchor_warns_or_fails(self):
        self.shop.products[3]["variants"][0]["anchor"] = None
        code, log = self.run_build()
        self.assertEqual(code, 0, log)
        self.assertIn("::warning", log)
        self.assertIn("1 row(s) without an anchor price", log)
        self.write_config(fail_on_missing_anchor=True)
        code, log = self.run_build("2026-10-02T04:17:00+02:00")
        self.assertEqual(code, 1, log)


class ConfigTests(unittest.TestCase):
    def load(self, **overrides):
        cfg = dict(BASE_CONFIG)
        cfg.update(overrides)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps(cfg), encoding="utf-8")
            return bpl.load_config(path)

    def test_defaults_and_slug(self):
        cfg = self.load()
        self.assertEqual(cfg["address_slug"], "Ilica-150-10000-Zagreb")
        self.assertEqual(cfg["form_of_sale"], "internetska-trgovina")
        self.assertEqual(cfg["shop_url"], "https://www.test-store.hr")
        self.assertEqual((cfg["keep_days"], cfg["max_pages"], cfg["currency"], cfg["country"]), (60, 100, "EUR", "HR"))

    def test_comment_keys_are_ignored(self):
        self.assertEqual(self.load(_note="anything")["store_name"], "Test Store")

    def test_slugify(self):
        self.assertEqual(bpl.slugify("Đakovačka 5, 31400 Đakovo"), "Dakovacka-5-31400-Dakovo")
        self.assertEqual(bpl.slugify("  Šetalište Ž. Š. 12/a  "), "Setaliste-Z-S-12-a")

    def test_invalid_values(self):
        cases = {
            "domain": ["https://www.x.hr", "www.x.hr/", "localhost"],
            "first_day": ["01.10.2026"],
            "premises_label": ["WEB 01", "WEB_01"],
            "collection_path": ["collections/all"],
            "max_row_drop_percent": [150],
            "csv_bom": ["yes"],
            "keep_days": [True, "sixty"],
            "currency": ["euro"],
            "country": ["HRV"],
        }
        for key, values in cases.items():
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaises(bpl.BuildError):
                    self.load(**{key: value})

    def test_unknown_key_is_rejected(self):
        with self.assertRaisesRegex(bpl.BuildError, "Unknown config key"):
            self.load(keep_day=90)
        with self.assertRaisesRegex(bpl.BuildError, "Unknown config key"):
            self.load(timezone="Europe/Zagreb")

    def test_placeholders_and_missing(self):
        with self.assertRaisesRegex(bpl.BuildError, "CHANGE_ME"):
            self.load(store_name="CHANGE_ME Store")
        with self.assertRaisesRegex(bpl.BuildError, "missing"):
            self.load(address="")

    def test_repository_config_is_valid(self):
        # Template repo: config.json may only fail because of CHANGE_ME placeholders.
        # Store repo: the filled-in config.json must load without errors.
        path = ROOT / "config.json"
        if "CHANGE_ME" in path.read_text(encoding="utf-8"):
            with self.assertRaisesRegex(bpl.BuildError, "CHANGE_ME"):
                bpl.load_config(path)
        else:
            bpl.load_config(path)


class XmlTests(unittest.TestCase):
    def test_escaping_and_invalid_characters(self):
        row = '"A & B <c> \x07￾""q""";"S1";"Br";"";;1,50;DA;"Akcija";2,00;"";dostupno'
        parsed = bpl.parse_rows([row])
        xml_text = bpl.build_xml(parsed)
        bpl.check_xml(xml_text, 1)
        element = ElementTree.fromstring(xml_text.encode("utf-8")).find("proizvod")
        self.assertEqual(element.findtext("naziv"), 'A & B <c> "q"')
        self.assertEqual(element.findtext("maloprodajna_cijena"), "1.50")
        self.assertEqual(element.findtext("naziv_posebnog_oblika_prodaje"), "Akcija")


if __name__ == "__main__":
    unittest.main()
