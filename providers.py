import os
import time
import logging
import requests
from bs4 import BeautifulSoup
from typing import List, Dict

logger = logging.getLogger(__name__)

class ProviderError(Exception):
    pass

class Top200Provider:
    """Base provider interface."""
    def get_top200(self) -> List[Dict]:
        raise NotImplementedError

# --- BitInfoCharts HTML provider (scrapes two pages: ranks 1-100 and 101-200) ---
class BitInfoChartsProvider(Top200Provider):
    """
    Scrapes BitInfoCharts richest address pages.
    NOTE: This relies on public HTML and may break if the site layout/URLs change.
    The user can update SOURCE_URLS below if needed.
    """
    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        proxy = os.getenv("HTTP_PROXY")
        if proxy:
            self.session.proxies.update({"http": proxy, "https": proxy})
        self.SOURCE_URLS = [
            # 1-100
            "https://bitinfocharts.com/top-100-richest-bitcoin-addresses.html",
            # 101-200 (commonly suffixed with -2.html on this site)
            "https://bitinfocharts.com/top-100-richest-bitcoin-addresses-2.html",
        ]

    def _parse_table(self, html: str) -> List[Dict]:
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table")
        if not table:
            raise ProviderError("Не найден HTML-таблица с данными.")
        out = []
        for tr in table.select("tr"):
            tds = tr.find_all("td")
            if len(tds) < 4:
                continue
            # Heuristic columns: Rank | Address | Balance | % / Tags ...
            rank_text = tds[0].get_text(strip=True).replace("#","")
            addr_a = tds[1].find("a")
            address = (addr_a.get_text(strip=True) if addr_a else tds[1].get_text(strip=True))
            balance_text = tds[2].get_text(" ", strip=True)
            tag_text = tds[1].get("title") or tds[1].get_text(" ", strip=True)

            # Cleanup
            try:
                rank = int("".join(c for c in rank_text if c.isdigit()))
            except:
                continue
            # Extract numeric BTC value (before ' BTC')
            btcs = None
            for part in balance_text.split():
                if part.lower().endswith("btc"):
                    val = part[:-3]
                    try:
                        btcs = float(val.replace(",", ""))
                    except:
                        pass
                    break

            out.append({
                "rank": rank,
                "address": address,
                "balance_btc": btcs,
                "tag": tag_text if address not in tag_text else "",
            })
        # Filter plausible rows
        out = [r for r in out if r.get("address") and isinstance(r.get("rank"), int)]
        # Some pages include header rows etc.
        out.sort(key=lambda r: r["rank"])
        return out

    def get_top200(self) -> List[Dict]:
        combined: List[Dict] = []
        for i, url in enumerate(self.SOURCE_URLS):
            logger.info(f"Fetching {url}")
            resp = self.session.get(url, timeout=30)
            if resp.status_code != 200:
                raise ProviderError(f"HTTP {resp.status_code} для {url}")
            # Throttle between requests politely
            if i == 0:
                time.sleep(1.0)
            rows = self._parse_table(resp.text)
            combined.extend(rows)
        # Keep only up to 200
        combined = [r for r in combined if 1 <= r["rank"] <= 200]
        combined.sort(key=lambda r: r["rank"])
        # Deduplicate by address (keep lowest rank if duplicates)
        seen = set()
        dedup = []
        for r in combined:
            if r["address"] in seen:
                continue
            seen.add(r["address"])
            dedup.append(r)
        return dedup[:200]

def get_provider(name: str) -> Top200Provider:
    name = (name or "").strip().lower()
    if name in ("", "bitinfocharts", "bitinfo"):
        return BitInfoChartsProvider()
    # Placeholder for future providers (e.g., Blockchair, Arkham, etc.)
    raise ProviderError(f"Неизвестный провайдер '{name}'. Доступно: bitinfocharts")
