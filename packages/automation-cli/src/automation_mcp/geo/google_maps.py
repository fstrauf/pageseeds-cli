from __future__ import annotations

import csv
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


def _clean_text(text: str) -> str:
    return " ".join((text or "").replace("\u00a0", " ").split()).strip()


def _find_repo_root(start: Path) -> Path:
    """Find the workspace repo root by scanning parent dirs for AGENTS.MD."""

    for candidate in [start, *start.parents]:
        if (candidate / "AGENTS.MD").exists():
            return candidate
    return start


_REPO_ROOT = _find_repo_root(Path(__file__).resolve())


def _resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    if path.is_absolute():
        return path
    return (_REPO_ROOT / path).resolve()


def _maybe_accept_google_consent(page: Any) -> None:
    """Best-effort click through Google consent dialogs.

    This is intentionally defensive: selectors and copy vary by locale and change over time.
    """

    # Common button names seen on Google consent dialogs.
    button_names = [
        "Accept all",
        "I agree",
        "Accept",
        "Agree",
        "Reject all",
        "Reject",
    ]

    for name in button_names:
        try:
            locator = page.get_by_role("button", name=name)
            if locator.count() > 0:
                locator.first.click(timeout=1500)
                return
        except Exception:
            continue


def _first_nonempty_inner_text(page: Any, selectors: list[str], timeout_ms: int) -> str:
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if loc.count() == 0:
                continue
            text = loc.first.inner_text(timeout=timeout_ms)
            text = _clean_text(text)
            if text:
                return text
        except Exception:
            continue
    return ""


def _ensure_place_page(page: Any, timeout_ms: int) -> None:
    """Try to navigate from search results into a specific place page."""

    # If we already have a place header, assume we are on a place page.
    try:
        header = page.locator("h1.DUwDvf")
        if header.count() > 0:
            return
    except Exception:
        pass

    # Try clicking the first search result.
    candidate_selectors = [
        'a[href^="/maps/place/"]',
        'a[href^="https://www.google.com/maps/place/"]',
        'a[href*="/maps/place/"]',
        'a.hfpxzc',
    ]

    for sel in candidate_selectors:
        try:
            loc = page.locator(sel)
            if loc.count() == 0:
                continue
            loc.first.click(timeout=timeout_ms)
            try:
                page.wait_for_timeout(500)
            except Exception:
                pass
            break
        except Exception:
            continue


def _extract_place_details(page: Any, timeout_ms: int) -> dict[str, Any]:
    # Give the heavily-client-rendered UI a chance to show either a place header or results list.
    try:
        page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    except Exception:
        pass

    try:
        page.wait_for_timeout(800)
    except Exception:
        pass

    _maybe_accept_google_consent(page)

    try:
        page.wait_for_timeout(800)
    except Exception:
        pass

    # Try to ensure we are on a place page
    _ensure_place_page(page, timeout_ms=timeout_ms)

    # If a results list is present, click into the first result and wait for the place header.
    try:
        if page.locator("a.hfpxzc").count() > 0 and page.locator("h1.DUwDvf").count() == 0:
            page.locator("a.hfpxzc").first.click(timeout=min(timeout_ms, 8000))
            try:
                page.wait_for_timeout(800)
            except Exception:
                pass
    except Exception:
        pass

    place_name = ""
    try:
        h1 = page.locator("h1.DUwDvf")
        if h1.count() > 0:
            place_name = _clean_text(h1.first.inner_text(timeout=timeout_ms))
    except Exception:
        place_name = ""

    # Address is often stored in a button with data-item-id=address
    address = _first_nonempty_inner_text(
        page,
        selectors=[
            'button[data-item-id="address"] div.Io6YTe',
            '[data-item-id="address"] div.Io6YTe',
            'button[data-item-id="address"]',
            '[data-item-id="address"]',
            'button[aria-label^="Address"]',
            'div.Io6YTe',
        ],
        timeout_ms=min(timeout_ms, 8000),
    )

    found = bool(place_name or address)

    return {
        "found": found,
        "place_name": place_name,
        "address": address,
    }


def _extract_best_maps_url(page: Any, fallback_url: str) -> str:
    """Try to return a stable, shareable Maps URL.

    Google Maps is often a SPA; sometimes the address panel updates without a full navigation.
    Canonical/OG URL metadata can still contain a direct /maps/place/ URL.
    """

    candidates: list[str] = []
    try:
        loc = page.locator('link[rel="canonical"]')
        if loc.count() > 0:
            href = loc.first.get_attribute('href')
            if href:
                candidates.append(href)
    except Exception:
        pass

    try:
        loc = page.locator('meta[property="og:url"]')
        if loc.count() > 0:
            content = loc.first.get_attribute('content')
            if content:
                candidates.append(content)
    except Exception:
        pass

    candidates.append(fallback_url)

    for url in candidates:
        url = (url or "").strip()
        if not url:
            continue
        if "/maps/place/" in url or "google.com/maps/place" in url:
            return url
    return fallback_url


@dataclass
class GoogleMapsClient:
    headless: bool = False
    slow_mo_ms: int = 0
    timeout_ms: int = 30000
    cdp_url: str | None = None

    def __post_init__(self) -> None:
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "Playwright is not installed. Add 'playwright' to dependencies and run: "
                "`uv run --directory packages/automation-cli python -m playwright install chromium`"
            ) from exc

        self._sync_playwright = sync_playwright
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None

    def __enter__(self) -> "GoogleMapsClient":
        self._pw = self._sync_playwright().start()

        if self.cdp_url:
            self._browser = self._pw.chromium.connect_over_cdp(self.cdp_url)
            if self._browser.contexts:
                self._context = self._browser.contexts[0]
            else:
                self._context = self._browser.new_context()
        else:
            self._browser = self._pw.chromium.launch(headless=self.headless, slow_mo=self.slow_mo_ms)
            self._context = self._browser.new_context()

        self._page = self._context.new_page()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        try:
            if self._context is not None and not self.cdp_url:
                self._context.close()
        finally:
            try:
                if self._browser is not None and not self.cdp_url:
                    self._browser.close()
            finally:
                if self._pw is not None:
                    self._pw.stop()

    @property
    def page(self) -> Any:
        if self._page is None:
            raise RuntimeError("GoogleMapsClient not started; use as a context manager")
        return self._page

    def lookup(self, query: str) -> dict[str, Any]:
        url = "https://www.google.com/maps/search/" + urllib.parse.quote(query)

        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            details = _extract_place_details(self.page, timeout_ms=self.timeout_ms)
            best_url = _extract_best_maps_url(self.page, fallback_url=self.page.url)
            return {
                "ok": True,
                "query": query,
                "maps_url": best_url,
                **details,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "query": query,
                "maps_url": getattr(self.page, "url", ""),
                "error": str(exc),
            }


def enrich_csv_with_google_maps(
    input_path: str,
    output_path: str,
    *,
    name_column: str = "cafe_name",
    city_column: str = "city_guess",
    country_hint: str = "New Zealand",
    max_rows: int | None = None,
    sleep_seconds: float = 1.0,
    headless: bool = False,
    slow_mo_ms: int = 0,
    timeout_ms: int = 30000,
    cdp_url: str | None = None,
) -> dict[str, Any]:
    """Enrich a CSV with Google Maps address + URL using Playwright.

    Notes:
    - This uses Google Maps web UI automation, which can be fragile and may trigger consent/captcha.
    - Prefer official APIs (e.g., Google Places API) for production-grade enrichment.
    """

    in_path = _resolve_path(input_path)
    out_path = _resolve_path(output_path)

    if not in_path.exists():
        return {"ok": False, "error": f"Input CSV not found: {in_path}"}

    rows: list[dict[str, str]] = []
    with in_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return {"ok": False, "error": "CSV has no header row"}
        fieldnames = list(reader.fieldnames)
        for idx, row in enumerate(reader):
            if max_rows is not None and idx >= max_rows:
                break
            rows.append({k: (v or "") for k, v in row.items()})

    added_fields = [
        "google_maps_query",
        "google_maps_place_name",
        "google_maps_address",
        "google_maps_url",
        "google_maps_ok",
        "google_maps_error",
    ]
    out_fieldnames = fieldnames + [f for f in added_fields if f not in fieldnames]

    results: list[dict[str, Any]] = []
    ok_count = 0

    with GoogleMapsClient(
        headless=headless,
        slow_mo_ms=slow_mo_ms,
        timeout_ms=timeout_ms,
        cdp_url=cdp_url,
    ) as client:
        for i, row in enumerate(rows, start=1):
            name = (row.get(name_column) or "").strip()
            city = (row.get(city_column) or "").strip()

            query_parts = [p for p in [name, city, country_hint] if p]
            query = ", ".join(query_parts)

            lookup = client.lookup(query)
            results.append(lookup)

            row["google_maps_query"] = query
            row["google_maps_place_name"] = str(lookup.get("place_name", ""))
            row["google_maps_address"] = str(lookup.get("address", ""))
            row["google_maps_url"] = str(lookup.get("maps_url", ""))
            row["google_maps_ok"] = "1" if lookup.get("ok") and lookup.get("found") else "0"
            row["google_maps_error"] = str(lookup.get("error", "")) if not lookup.get("ok") else ""

            if lookup.get("ok") and lookup.get("found"):
                ok_count += 1

            if sleep_seconds > 0 and i < len(rows):
                time.sleep(sleep_seconds)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    return {
        "ok": True,
        "input_path": str(in_path),
        "output_path": str(out_path),
        "processed": len(rows),
        "matched": ok_count,
        "results": results,
    }
