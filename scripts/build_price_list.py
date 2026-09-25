#!/usr/bin/env python3
"""
shopify-price-list-csv-xml-template: daily price list (cjenik) builder for Shopify stores.

Legal basis: Odluka o objavi cjenika proizvoda i usluga kao mjeri izravne kontrole
cijena (NN 101/2026-1213) and the Ministry clarification of 22 September 2026.

What it does, once per run:
  1. Fetches the store's CSV price list page by page from the theme template
     `collection.price-list` (/collections/all?view=price-list&page=N). Every page ends
     with a '#meta' control line (page, total pages, total products, products on this
     page, currency, country, VAT mode). The script uses it to fetch exactly all pages,
     to check that the page totals add up to the store's product count, and that the
     prices are in the right currency, market and VAT mode.
  2. Validates every page and every row (header, 11 columns, number formats, flags).
  3. Merges all pages into one CSV and builds the XML from the same rows, so both
     files always contain exactly the same data.
  4. Names the files in the Ministry's order:
        oblik_adresa_oznaka_brojpohrane_datum_vrijeme
     e.g. internetska-trgovina_Ilica-1-10000-Zagreb_WEB01_1_01.10.2026_05.17.csv
  5. Writes them into the site folder (files/ + latest.csv/latest.xml), keeps the
     archive for `keep_days` (never less than 31), and regenerates index.html and
     manifest.json.

If any check fails, no price list is written (yesterday's files stay online) and the
exit code is 1, so GitHub emails the repository owner. Exit code 0 = published,
already published today, or (before the go-live date) checked without publishing.

Only the Python standard library is used (Python 3.10+).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import html
import http.client
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from xml.etree import ElementTree
from xml.sax.saxutils import escape as xml_escape
from zoneinfo import ZoneInfo

VERSION = "1.1.0"
TIMEZONE = "Europe/Zagreb"  # fixed: the workflow schedule is built for Zagreb time
SHOPIFY_PAGINATION_LIMIT = 25_000  # Shopify's paginate tag cannot go past 25,000 items

HEADER = [
    "naziv",
    "sifra",
    "marka",
    "jedinica_mjere",
    "cijena_za_jedinicu_mjere",
    "maloprodajna_cijena",
    "posebni_oblik_prodaje",
    "naziv_posebnog_oblika_prodaje",
    "sidrena_cijena",
    "barkod",
    "dostupnost",
]
HEADER_LINE = ";".join(HEADER)
COL = {name: i for i, name in enumerate(HEADER)}
NUMERIC_COLUMNS = ("cijena_za_jedinicu_mjere", "maloprodajna_cijena", "sidrena_cijena")
PRICE_RE = re.compile(r"^\d+,\d{2}$")
META_PREFIX = "#meta;"
META_INT_KEYS = ("page", "pages", "items", "listed", "skipped", "truncated")
META_KEYS = META_INT_KEYS + ("currency", "country", "taxes_included")
MIN_KEEP_DAYS = 31  # the law requires at least 30 days; one extra day of margin
RETRY_HTTP_CODES = {408, 425, 429, 430}  # plus every 5xx except 501
XML_INVALID_CHARS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")

DEFAULTS = {
    "company_name": "",
    "company_oib": "",
    "form_of_sale": "internetska-trgovina",
    "address_slug": "",
    "shop_url": "",
    "currency": "EUR",
    "country": "HR",
    "require_taxes_included": True,
    "require_country_match": True,
    "collection_path": "/collections/all",
    "template_view": "price-list",
    "sort_by": "created-ascending",
    "keep_days": 60,
    "max_pages": 100,
    "max_row_drop_percent": 50,
    "fail_on_missing_anchor": False,
    "csv_bom": False,
    "request_delay_seconds": 1.0,
    "request_timeout_seconds": 60,
    "retries": 5,
}
REQUIRED = ("store_name", "domain", "address", "premises_label", "first_day")


class BuildError(Exception):
    """A problem that must stop publishing."""


class CatalogChanged(Exception):
    """Products were added/removed while the pages were being fetched."""


# --------------------------------------------------------------------------- config


def load_config(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise BuildError(f"Config file not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise BuildError(f"Config file {path} is not valid JSON: {exc}") from None
    if not isinstance(raw, dict):
        raise BuildError(f"Config file {path} must contain a JSON object")

    settings = {k: v for k, v in raw.items() if not k.startswith("_")}
    unknown = sorted(set(settings) - set(DEFAULTS) - set(REQUIRED))
    if unknown:
        raise BuildError(
            f"Unknown config key(s): {', '.join(unknown)} (typo?). "
            f"Allowed keys: {', '.join(sorted(set(DEFAULTS) | set(REQUIRED)))}"
        )
    cfg = dict(DEFAULTS)
    cfg.update(settings)

    missing = [k for k in REQUIRED if not str(cfg.get(k, "")).strip()]
    if missing:
        raise BuildError(f"Config is missing required value(s): {', '.join(missing)}")
    placeholders = [k for k, v in cfg.items() if isinstance(v, str) and "CHANGE_ME" in v]
    if placeholders:
        raise BuildError(f"Config still has CHANGE_ME placeholder(s) in: {', '.join(sorted(placeholders))}")

    domain = str(cfg["domain"]).strip().lower()
    if "/" in domain or ":" in domain or " " in domain or "." not in domain:
        raise BuildError(
            f"Config 'domain' must be a bare host name like 'www.example.hr' "
            f"(no https://, no slash), got: {cfg['domain']!r}"
        )
    cfg["domain"] = domain

    try:
        cfg["first_day"] = dt.date.fromisoformat(str(cfg["first_day"]))
    except ValueError:
        raise BuildError(f"Config 'first_day' must be YYYY-MM-DD, got: {cfg['first_day']!r}") from None

    label = str(cfg["premises_label"]).strip()
    if not re.fullmatch(r"[A-Za-z0-9-]+", label):
        raise BuildError(
            f"Config 'premises_label' may only contain letters, digits and hyphens, got: {label!r}"
        )
    cfg["premises_label"] = label

    form = slugify(str(cfg["form_of_sale"]))
    if not form:
        raise BuildError("Config 'form_of_sale' must not be empty")
    cfg["form_of_sale"] = form

    cfg["address_slug"] = slugify(str(cfg["address_slug"]).strip() or str(cfg["address"]))
    if not cfg["address_slug"]:
        raise BuildError("Config 'address' produces an empty file-name part")

    for key, pattern in (("currency", r"[A-Z]{3}"), ("country", r"[A-Z]{2}")):
        cfg[key] = str(cfg[key]).strip().upper()
        if not re.fullmatch(pattern, cfg[key]):
            raise BuildError(f"Config '{key}' is not a valid ISO code: {cfg[key]!r}")

    path_ = str(cfg["collection_path"])
    if not path_.startswith("/"):
        raise BuildError(f"Config 'collection_path' must start with '/', got: {path_!r}")

    for key, lo in (("keep_days", 1), ("max_pages", 1), ("retries", 1), ("request_timeout_seconds", 1)):
        value = cfg[key]
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise BuildError(f"Config '{key}' must be a whole number")
        try:
            cfg[key] = int(value)
        except (TypeError, ValueError):
            raise BuildError(f"Config '{key}' must be a whole number") from None
        if cfg[key] < lo:
            raise BuildError(f"Config '{key}' must be at least {lo}")
    cfg["keep_days"] = max(cfg["keep_days"], MIN_KEEP_DAYS)

    try:
        cfg["max_row_drop_percent"] = float(cfg["max_row_drop_percent"])
        cfg["request_delay_seconds"] = float(cfg["request_delay_seconds"])
    except (TypeError, ValueError):
        raise BuildError("Config 'max_row_drop_percent' and 'request_delay_seconds' must be numbers") from None
    if not 0 <= cfg["max_row_drop_percent"] <= 100:
        raise BuildError("Config 'max_row_drop_percent' must be between 0 and 100")

    for key in ("fail_on_missing_anchor", "csv_bom", "require_taxes_included", "require_country_match"):
        if not isinstance(cfg[key], bool):
            raise BuildError(f"Config '{key}' must be true or false")

    cfg["shop_url"] = str(cfg["shop_url"]).strip() or f"https://{domain}"
    return cfg


def slugify(text: str) -> str:
    """'Ilica 1, 10000 Zagreb' -> 'Ilica-1-10000-Zagreb' (no diacritics, URL-safe)."""
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^A-Za-z0-9]+", "-", text)
    return text.strip("-")


# --------------------------------------------------------------------------- fetching


def is_retryable(code: int) -> bool:
    return code in RETRY_HTTP_CODES or (code >= 500 and code != 501)


def fetch_text(url: str, cfg: dict, log) -> str:
    """GET a URL with retries. Returns the body as text or raises BuildError."""
    attempts = cfg["retries"]
    delay = 5.0
    last_error = ""
    for attempt in range(1, attempts + 1):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": f"shopify-price-list-csv-xml-template/{VERSION} (+price list publisher, NN 101/2026)",
                "Accept": "text/csv,text/plain;q=0.9,*/*;q=0.8",
                "Cache-Control": "no-cache",
                # Ask for the Croatian market in EUR. The '#meta' line verifies what we really got.
                "Cookie": f"localization={cfg['country']}; cart_currency={cfg['currency']}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=cfg["request_timeout_seconds"]) as resp:
                final_url = resp.geturl()
                body = resp.read()
            if "/password" in urllib.parse.urlparse(final_url).path:
                raise BuildError(
                    "The store is password-protected (redirected to /password). "
                    "The price list must be publicly reachable: remove the storefront password."
                )
            try:
                return body.decode("utf-8")
            except UnicodeDecodeError:
                raise BuildError(f"Response from {url} is not valid UTF-8") from None
        except urllib.error.HTTPError as exc:
            if is_retryable(exc.code) and attempt < attempts:
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                wait = min(float(retry_after), 120.0) if retry_after and retry_after.isdigit() else delay
                log(f"  HTTP {exc.code} on attempt {attempt}/{attempts}, retrying in {wait:.0f}s")
                time.sleep(wait)
                delay = min(delay * 2, 120)
                last_error = f"HTTP {exc.code}"
                continue
            hint = ""
            if exc.code == 404:
                hint = " Check 'domain' and 'collection_path' in config.json."
            tried = f" after {attempts} attempts" if is_retryable(exc.code) else ""
            raise BuildError(f"HTTP {exc.code} for {url}{tried}.{hint}") from None
        except (OSError, http.client.HTTPException) as exc:  # network, DNS, TLS, timeouts
            last_error = str(getattr(exc, "reason", exc)) or type(exc).__name__
            if attempt < attempts:
                log(f"  Network error on attempt {attempt}/{attempts} ({last_error}), retrying in {delay:.0f}s")
                time.sleep(delay)
                delay = min(delay * 2, 120)
                continue
    raise BuildError(f"Could not fetch {url} after {attempts} attempts: {last_error}")


def parse_meta(line: str, page: int) -> dict:
    meta = {}
    for part in line[len(META_PREFIX):].split(";"):
        key, sep, value = part.partition("=")
        if sep:
            meta[key.strip()] = value.strip()
    missing = [k for k in META_KEYS if k not in meta]
    if missing:
        raise BuildError(f"The '#meta' line on page {page} is incomplete (missing: {', '.join(missing)}): {line!r}")
    for key in META_INT_KEYS:
        try:
            meta[key] = int(meta[key])
        except ValueError:
            raise BuildError(f"The '#meta' line on page {page} has a non-numeric {key}: {line!r}") from None
    return meta


def parse_page(text: str, page: int) -> tuple[list[str], dict]:
    """Validate one page of the CSV template output. Returns (data lines, meta)."""
    if text.startswith("﻿"):
        text = text[1:]
    lines = [line.rstrip("\r") for line in text.split("\n")]
    first = lines[0] if lines else ""
    if first != HEADER_LINE:
        preview = first[:120].replace("\n", " ")
        raise BuildError(
            f"Page {page} does not start with the expected CSV header. Got: {preview!r}. "
            "Is the theme template 'collection.price-list' installed in the PUBLISHED theme, "
            "and is 'template_view' in config.json correct?"
        )
    body = [line for line in lines[1:] if line.strip()]
    if not body or not body[-1].startswith(META_PREFIX):
        raise BuildError(
            f"Page {page} has no '#meta' control line at the end. The theme template is an older "
            "version (install shopify/templates/collection.price-list.liquid from this kit), "
            "or the page was cut off."
        )
    meta = parse_meta(body[-1], page)
    rows = []
    for number, line in enumerate(body[:-1], start=2):
        if line.startswith(META_PREFIX):
            raise BuildError(f"Page {page} has more than one '#meta' line")
        validate_row(line, page, number)
        rows.append(line)
    return rows, meta


def validate_row(line: str, page: int, line_no: int) -> None:
    where = f"page {page}, line {line_no}"
    try:
        fields = next(csv.reader([line], delimiter=";", quotechar='"', strict=True))
    except csv.Error as exc:
        raise BuildError(f"Malformed CSV on {where}: {exc}: {line[:200]!r}") from None
    if len(fields) != len(HEADER):
        raise BuildError(f"Expected {len(HEADER)} columns on {where}, got {len(fields)}: {line[:200]!r}")
    if not fields[COL["naziv"]].strip():
        raise BuildError(f"Empty product name on {where}: {line[:200]!r}")
    if not PRICE_RE.match(fields[COL["maloprodajna_cijena"]]):
        raise BuildError(f"Invalid retail price on {where}: {fields[COL['maloprodajna_cijena']]!r}")
    for column in ("cijena_za_jedinicu_mjere", "sidrena_cijena"):
        value = fields[COL[column]]
        if value and not PRICE_RE.match(value):
            raise BuildError(f"Invalid {column} on {where}: {value!r}")
    flag = fields[COL["posebni_oblik_prodaje"]]
    if flag not in ("DA", "NE"):
        raise BuildError(f"posebni_oblik_prodaje must be DA or NE on {where}, got {flag!r}")
    if flag == "DA" and not fields[COL["naziv_posebnog_oblika_prodaje"]].strip():
        raise BuildError(f"Sale without a name (naziv_posebnog_oblika_prodaje) on {where}")
    if fields[COL["dostupnost"]] not in ("dostupno", "nedostupno"):
        raise BuildError(f"dostupnost must be 'dostupno' or 'nedostupno' on {where}")


def check_page_context(meta: dict, cfg: dict, page: int, warnings: list[str]) -> None:
    """Currency, VAT mode and variant truncation reported by the '#meta' line."""
    if meta["currency"] != cfg["currency"]:
        raise BuildError(
            f"The store answered in currency '{meta['currency']}' (country '{meta['country']}') instead of "
            f"{cfg['currency']}. The price list must show {cfg['currency']} prices. Check Settings → Markets: "
            f"visitors from other countries (GitHub's servers are in the US) must not be shown another currency."
        )
    if meta["country"] != cfg["country"] and cfg["require_country_match"]:
        raise BuildError(
            f"The store answered for country '{meta['country']}' instead of '{cfg['country']}'. Another market "
            "could have different prices (price adjustments). Check Settings → Markets. If the store has ONLY "
            f"the {cfg['country']} market, so every visitor gets the same prices, set "
            "\"require_country_match\": false in config.json."
        )
    taxes = str(meta["taxes_included"]).lower()
    if taxes == "false" and cfg["require_taxes_included"]:
        raise BuildError(
            f"The store answered with prices WITHOUT VAT (country '{meta['country']}'). Consumer prices must "
            "include VAT. Check Settings → Taxes and duties: 'Include sales tax in product price' and "
            "'Include or exclude tax based on your customer's country'. If the store really never charges "
            "VAT, set \"require_taxes_included\": false in config.json."
        )
    if taxes not in ("true", "false") and page == 1:
        message = f"Could not verify that prices include VAT (taxes_included={meta['taxes_included']!r})."
        if message not in warnings:
            warnings.append(message)
    if meta["truncated"] > 0:
        raise BuildError(
            f"{meta['truncated']} product(s) on page {page} have more variants than Shopify's Liquid can list, "
            "so some variants would be missing from the price list. Not supported: split those products."
        )


def fetch_once(cfg: dict, base_url: str, log, cache_buster: str, warnings: list[str]) -> tuple[list[str], int, dict]:
    rows: list[str] = []
    first: dict | None = None
    counted = 0
    page = 1
    while True:
        query = urllib.parse.urlencode(
            {"view": cfg["template_view"], "page": page, "sort_by": cfg["sort_by"], "cb": cache_buster}
        )
        url = f"{base_url}{cfg['collection_path']}?{query}"
        log(f"Fetching page {page}: {url}")
        page_rows, meta = parse_page(fetch_text(url, cfg, log), page)
        check_page_context(meta, cfg, page, warnings)
        if meta["page"] != page:
            raise BuildError(f"Requested page {page} but the store answered page {meta['page']}.")
        if first is None:
            first = meta
            if meta["items"] > SHOPIFY_PAGINATION_LIMIT:
                raise BuildError(
                    f"The store has {meta['items']} products in {cfg['collection_path']}. Shopify's pagination "
                    f"stops at {SHOPIFY_PAGINATION_LIMIT:,}, so a complete price list is not possible this way."
                )
            if meta["pages"] > cfg["max_pages"]:
                raise BuildError(
                    f"The price list has {meta['pages']} pages but max_pages is {cfg['max_pages']}. "
                    "Raise 'max_pages' in config.json."
                )
            if meta["items"] == 0:
                return [], 0, meta
        elif (meta["items"], meta["pages"]) != (first["items"], first["pages"]):
            raise CatalogChanged(
                f"product count changed from {first['items']} to {meta['items']} between page 1 and page {page}"
            )
        counted += meta["listed"] + meta["skipped"]
        rows.extend(page_rows)
        log(f"Page {page}/{first['pages']}: {len(page_rows)} rows ({meta['listed']} products).")
        if page >= first["pages"]:
            break
        page += 1
        if cfg["request_delay_seconds"] > 0:
            time.sleep(cfg["request_delay_seconds"])
    if counted != first["items"]:
        raise CatalogChanged(f"the pages contained {counted} products but the store reports {first['items']}")
    return rows, first["pages"], first


def fetch_all_rows(cfg: dict, base_url: str, log, now_ts: int, warnings: list[str]) -> tuple[list[str], int, dict]:
    """Fetch every page. If products change during the run, start once more; then give up."""
    for attempt in (1, 2):
        try:
            return fetch_once(cfg, base_url, log, f"{now_ts}-{attempt}", warnings)
        except CatalogChanged as exc:
            if attempt == 2:
                raise BuildError(
                    f"Products changed while the price list was being fetched, twice in a row ({exc}). "
                    "Nothing published; the next (backup) run will try again."
                ) from None
            log(f"Products changed during the run ({exc}); fetching all pages again.")
            if cfg["request_delay_seconds"] > 0:
                time.sleep(max(cfg["request_delay_seconds"], 5))
    raise AssertionError("unreachable")


# --------------------------------------------------------------------------- output


def parse_rows(rows: list[str]) -> list[list[str]]:
    return [next(csv.reader([row], delimiter=";", quotechar='"')) for row in rows]


def build_csv(rows: list[str], bom: bool) -> str:
    return ("﻿" if bom else "") + HEADER_LINE + "\n" + "".join(row + "\n" for row in rows)


def build_xml(parsed: list[list[str]]) -> str:
    out = ['<?xml version="1.0" encoding="UTF-8"?>', "<cjenik>"]
    for fields in parsed:
        parts = []
        for name, value in zip(HEADER, fields, strict=True):
            if name in NUMERIC_COLUMNS and value:
                value = value.replace(",", ".")
            value = XML_INVALID_CHARS.sub("", value)
            parts.append(f"<{name}>{xml_escape(value)}</{name}>")
        out.append("  <proizvod>" + "".join(parts) + "</proizvod>")
    out.append("</cjenik>")
    return "\n".join(out) + "\n"


def check_xml(xml_text: str, expected: int) -> None:
    try:
        root = ElementTree.fromstring(xml_text.encode("utf-8"))
    except ElementTree.ParseError as exc:
        raise BuildError(f"Generated XML is not well-formed: {exc}") from None
    count = len(root.findall("proizvod"))
    if count != expected:
        raise BuildError(f"XML has {count} products but CSV has {expected}")


def file_base(cfg: dict, number: int, now: dt.datetime) -> str:
    return "_".join(
        [
            cfg["form_of_sale"],
            cfg["address_slug"],
            cfg["premises_label"],
            str(number),
            now.strftime("%d.%m.%Y"),
            now.strftime("%H.%M"),
        ]
    )


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_manifest(site: Path) -> dict:
    path = site / "manifest.json"
    if not path.exists():
        return {"entries": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BuildError(f"{path} is corrupted: {exc}") from None
    data.setdefault("entries", [])
    return data


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def fmt_date(iso: str) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{d.day}. {d.month}. {d.year}."


def render_index(cfg: dict, manifest: dict) -> str:
    e = html.escape
    entries = manifest["entries"]
    trader = [f"<strong>{e(cfg['company_name'] or cfg['store_name'])}</strong>"]
    if cfg["company_oib"]:
        trader.append(f"OIB: {e(str(cfg['company_oib']))}")
    trader.append(f"Adresa: {e(cfg['address'])}")
    trader.append(f"Oznaka poslovnog prostora: {e(cfg['premises_label'])}")
    trader.append(f'Internetska trgovina: <a href="{e(cfg["shop_url"])}">{e(cfg["shop_url"])}</a>')

    if entries:
        latest = entries[0]
        current = (
            f"<p class=\"current\">Trenutni cjenik ({e(fmt_date(latest['date']))} u {e(latest['time'])}, "
            f"{latest['rows']} stavki): "
            f'<a href="latest.csv">CSV</a> · <a href="latest.xml">XML</a></p>'
        )
        rows_html = "\n".join(
            "<tr>"
            f"<td>{e(fmt_date(x['date']))}</td>"
            f"<td>{e(x['time'])}</td>"
            f"<td>{x['number']}</td>"
            f"<td>{x['rows']}</td>"
            f"<td><a href=\"{e(x['csv'])}\">CSV</a> · <a href=\"{e(x['xml'])}\">XML</a></td>"
            "</tr>"
            for x in entries
        )
        archive = (
            "<table><thead><tr><th>Datum</th><th>Vrijeme</th><th>Broj pohrane</th>"
            "<th>Broj stavki</th><th>Datoteke</th></tr></thead>\n<tbody>\n"
            f"{rows_html}\n</tbody></table>"
        )
        machine = ' Strojni popis svih datoteka: <a href="manifest.json">manifest.json</a>.'
        updated = f"<p class=\"muted\">Zadnje ažuriranje: {e(fmt_date(latest['date']))} u {e(latest['time'])}.</p>"
    else:
        start = cfg["first_day"]
        current = f"<p class=\"current\">Objava cjenika počinje {start.day}. {start.month}. {start.year}.</p>"
        archive = "<p>Još nema objavljenih cjenika.</p>"
        machine = ""
        updated = ""

    return f"""<!doctype html>
<html lang="hr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cjenik – {e(cfg['store_name'])}</title>
<style>
  :root {{ color-scheme: light dark; --fg:#1a1a1a; --muted:#666; --line:#ddd; --bg:#fff; --link:#0b5cad; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --fg:#eee; --muted:#aaa; --line:#444; --bg:#141414; --link:#6cb4ff; }}
  }}
  body {{ margin:0; background:var(--bg); color:var(--fg);
         font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }}
  main {{ max-width:860px; margin:0 auto; padding:24px 16px 48px; }}
  h1 {{ font-size:1.6rem; margin:0 0 12px; }}
  h2 {{ font-size:1.2rem; margin:32px 0 8px; }}
  a {{ color:var(--link); }}
  .trader {{ border:1px solid var(--line); border-radius:8px; padding:12px 16px; }}
  .trader p {{ margin:2px 0; }}
  .current {{ font-size:1.1rem; }}
  .muted {{ color:var(--muted); font-size:.9rem; }}
  .table-wrap {{ overflow-x:auto; }}
  table {{ border-collapse:collapse; width:100%; font-size:.95rem; }}
  th, td {{ text-align:left; padding:6px 8px; border-bottom:1px solid var(--line); white-space:nowrap; }}
</style>
</head>
<body>
<main>
<h1>Cjenik proizvoda – {e(cfg['store_name'])}</h1>
<div class="trader">
{''.join(f'<p>{line}</p>' for line in trader)}
</div>
<p>Cjenici su objavljeni u strojno čitljivom obliku (.csv i .xml) sukladno Odluci o objavi cjenika
proizvoda i usluga kao mjeri izravne kontrole cijena (NN 101/2026). Cjenik se objavljuje svaki dan
prije 8:00 sati, a objavljeni cjenici dostupni su najmanje 30 dana od dana objave.</p>
{current}
<h2>Objavljeni cjenici</h2>
<div class="table-wrap">
{archive}
</div>
<h2>Format</h2>
<p>CSV: UTF-8, separator točka-zarez (;), decimalni zarez. XML: UTF-8, decimalna točka.
Stupci: {e(', '.join(HEADER))}.{machine}</p>
{updated}
</main>
</body>
</html>
"""


def write_summary(text: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")


def collect_row_warnings(rows: list[str], parsed: list[list[str]], cfg: dict) -> list[str]:
    warnings = []
    missing_anchor = [f[COL["naziv"]] for f in parsed if not f[COL["sidrena_cijena"]]]
    if missing_anchor:
        msg = f"{len(missing_anchor)} row(s) without an anchor price (sidrena_cijena), e.g.: " + "; ".join(
            missing_anchor[:5]
        )
        if cfg["fail_on_missing_anchor"]:
            raise BuildError(msg)
        warnings.append(msg)
    seen, dupes = set(), 0
    for row in rows:
        if row in seen:
            dupes += 1
        seen.add(row)
    if dupes:
        warnings.append(
            f"{dupes} exactly duplicated row(s) (same name, SKU and prices). Check for duplicated products."
        )
    return warnings


# --------------------------------------------------------------------------- main


def run(args, log) -> int:
    cfg = load_config(Path(args.config))
    tz = ZoneInfo(TIMEZONE)
    now = dt.datetime.fromisoformat(args.now).astimezone(tz) if args.now else dt.datetime.now(tz)
    now = now.replace(second=0, microsecond=0)
    today = now.date()
    site = Path(args.site_dir)
    base_url = (args.base_url or f"https://{cfg['domain']}").rstrip("/")
    manifest = load_manifest(site)
    warnings: list[str] = []

    log(f"shopify-price-list-csv-xml-template {VERSION} | store: {cfg['store_name']} | now: {now.isoformat()}")

    if args.reset_archive and not args.dry_run:
        files_dir = site / "files"
        if files_dir.exists():
            for p in files_dir.iterdir():
                if p.is_file():
                    p.unlink()
        for name in ("latest.csv", "latest.xml", "manifest.json"):
            (site / name).unlink(missing_ok=True)
        manifest = {"entries": []}
        log("Archive reset: all previously published price lists were removed.")

    live = today >= cfg["first_day"]
    todays = [x for x in manifest["entries"] if x["date"] == today.isoformat()]
    if live and todays and not (args.force or args.dry_run):
        log(f"Already published today ({todays[0]['csv']}). Nothing to do. Use --force to rebuild.")
        write_summary(f"### Price list: already published today\n`{todays[0]['csv']}`")
        return 0

    rows, pages, meta = fetch_all_rows(cfg, base_url, log, int(now.timestamp()), warnings)
    if not rows:
        raise BuildError(
            f"The price list has 0 products (store reports {meta['items']} product(s) in "
            f"{cfg['collection_path']}). Nothing published. Are the products published to the Online Store?"
        )
    parsed = parse_rows(rows)
    warnings += collect_row_warnings(rows, parsed, cfg)
    on_sale = sum(1 for f in parsed if f[COL["posebni_oblik_prodaje"]] == "DA")
    csv_text = build_csv(rows, cfg["csv_bom"])
    xml_text = build_xml(parsed)
    check_xml(xml_text, len(rows))
    for w in warnings:
        print(f"::warning title=Price list::{w}", flush=True)

    if not live:
        log(
            f"Not live yet (first_day is {cfg['first_day']}): the price list was checked "
            f"({len(rows)} rows from {pages} page(s), {on_sale} on sale) but not published."
        )
        if not args.dry_run:
            site.mkdir(parents=True, exist_ok=True)
            write_text(site / "index.html", render_index(cfg, manifest))
            write_text(site / "robots.txt", "User-agent: *\nAllow: /\n")
        write_summary(
            f"### Price list checked, not published yet\nPublishing starts on {cfg['first_day']}. "
            f"Today's check: {len(rows)} rows, {on_sale} on sale."
            + ("\n\n**Warnings**\n\n" + "\n".join(f"- {w}" for w in warnings) if warnings else "")
        )
        return 0

    previous = [x for x in manifest["entries"] if x["date"] != today.isoformat()]
    if previous and not args.force:
        last_rows = int(previous[0]["rows"])
        minimum = last_rows * (1 - cfg["max_row_drop_percent"] / 100)
        if len(rows) < minimum:
            raise BuildError(
                f"Only {len(rows)} rows today vs {last_rows} on {previous[0]['date']} "
                f"(more than {cfg['max_row_drop_percent']:g}% fewer). Nothing published. "
                "If the drop is real (products removed), re-run the workflow with 'force'."
            )

    number = (today - cfg["first_day"]).days + 1
    base = file_base(cfg, number, now)
    entry = {
        "number": number,
        "date": today.isoformat(),
        "time": now.strftime("%H:%M"),
        "csv": f"files/{base}.csv",
        "xml": f"files/{base}.xml",
        "rows": len(rows),
        "on_sale": on_sale,
        "sha256_csv": sha256(csv_text),
        "sha256_xml": sha256(xml_text),
    }
    log(f"Built {len(rows)} rows from {pages} page(s); {on_sale} on sale. File: {base}.csv/.xml")

    if args.dry_run:
        log("Dry run: nothing written.")
        return 0

    # Write into a staging folder first, then move into place.
    site.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=site.parent if site.parent.exists() else None) as tmp:
        stage = Path(tmp)
        write_text(stage / f"{base}.csv", csv_text)
        write_text(stage / f"{base}.xml", xml_text)
        (site / "files").mkdir(parents=True, exist_ok=True)
        for old in todays:  # --force: replace today's earlier files
            for key in ("csv", "xml"):
                old_path = site / old[key]
                if old_path.exists() and old_path.name != f"{base}.{key}":
                    old_path.unlink()
        shutil.move(str(stage / f"{base}.csv"), str(site / "files" / f"{base}.csv"))
        shutil.move(str(stage / f"{base}.xml"), str(site / "files" / f"{base}.xml"))

    write_text(site / "latest.csv", csv_text)
    write_text(site / "latest.xml", xml_text)

    entries = [x for x in manifest["entries"] if x["date"] != today.isoformat()]
    entries.append(entry)
    cutoff = today - dt.timedelta(days=cfg["keep_days"])
    kept, removed = [], 0
    for x in sorted(entries, key=lambda x: (x["date"], x["time"]), reverse=True):
        if dt.date.fromisoformat(x["date"]) < cutoff:
            for key in ("csv", "xml"):
                p = site / x[key]
                if p.exists():
                    p.unlink()
            removed += 1
        else:
            kept.append(x)
    referenced = {(site / x[key]).resolve() for x in kept for key in ("csv", "xml")}
    for p in (site / "files").iterdir():
        if p.is_file() and p.resolve() not in referenced:
            p.unlink()
            log(f"Removed file not listed in the manifest: {p.name}")
    manifest = {
        "store": cfg["store_name"],
        "generator": f"shopify-price-list-csv-xml-template {VERSION}",
        "updated_at": now.isoformat(),
        "keep_days": cfg["keep_days"],
        "columns": HEADER,
        "entries": kept,
    }
    write_text(site / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    write_text(site / "index.html", render_index(cfg, manifest))
    write_text(site / "robots.txt", "User-agent: *\nAllow: /\n")
    if removed:
        log(f"Removed {removed} archived day(s) older than {cfg['keep_days']} days.")

    summary = [
        f"### Price list published: {fmt_date(entry['date'])} {entry['time']}",
        "",
        "| | |",
        "|---|---|",
        f"| Rows | {len(rows)} (from {pages} page(s), {meta['items']} products in the store) |",
        f"| On sale (DA) | {on_sale} |",
        f"| Storage number | {number} |",
        f"| CSV | `{entry['csv']}` |",
        f"| XML | `{entry['xml']}` |",
        f"| Archive | {len(kept)} day(s) kept |",
    ]
    if warnings:
        summary += ["", "**Warnings**", ""] + [f"- {w}" for w in warnings]
    write_summary("\n".join(summary))
    log("Done.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build and publish the daily Shopify price list (cjenik).")
    parser.add_argument("--config", default="config.json", help="path to config.json (default: config.json)")
    parser.add_argument("--site-dir", default="site", help="folder published by GitHub Pages (default: site)")
    parser.add_argument("--force", action="store_true", help="rebuild today's price list and skip the row-drop guard")
    parser.add_argument("--dry-run", action="store_true", help="fetch and validate only, write nothing")
    parser.add_argument(
        "--reset-archive",
        action="store_true",
        help="delete all previously published files first (use once when going live after testing)",
    )
    parser.add_argument("--now", help="override the current time (ISO 8601 with offset), for testing")
    parser.add_argument("--base-url", help="override https://<domain>, for testing")
    args = parser.parse_args(argv)

    def log(message: str) -> None:
        print(message, flush=True)

    try:
        return run(args, log)
    except BuildError as exc:
        print(f"::error title=Price list not published::{exc}", flush=True)
        write_summary(f"### Price list NOT published\n\n{exc}")
        return 1
    except Exception as exc:  # unexpected bug: still fail loudly and clearly
        print(f"::error title=Price list not published (unexpected error)::{type(exc).__name__}: {exc}", flush=True)
        write_summary(f"### Price list NOT published (unexpected error)\n\n`{type(exc).__name__}: {exc}`")
        raise


if __name__ == "__main__":
    sys.exit(main())
