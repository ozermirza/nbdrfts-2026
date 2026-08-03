# -*- coding: utf-8 -*-
# TESHIS ARACI - surum 11
# Amac: magaza kartlarinda robotun karar zincirini birebir simule etmek
# (hangi kart neden eleniyor?) + alt-tabanli ad cozumunu test etmek.

import csv
import html as html_mod
import re
from urllib.parse import urlparse

MAGAZA_URL = "https://www.trendyol.com/sr?lc=103714%2C1193&os=1&mid=1095234"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
TABAN_FIYAT = 500
DAHIL_KELIMELER = ["matara", "termos", "suluk", "bottle", "şişe", "sise"]
HARIC_KELIMELER = ["tritan", "yemek", "food", "beslenme", "mama"]
SERILER = ["FlipSip", "SippyPals", "WideWonder", "SipSquad", "Lil'Straw"]


def kucuk(m):
    return (m or "").lower().replace("i̇", "i")


def uygun_mu(ad):
    a = kucuk(ad)
    if any(h in a for h in HARIC_KELIMELER):
        return False
    if any(d in a for d in DAHIL_KELIMELER):
        return True
    return any(kucuk(s).replace("'", "") in a.replace("'", "") for s in SERILER)


def model_adi(url):
    yol = urlparse(url.strip()).path.split("/")[-1]
    return re.sub(r"-p-\d+$", "", yol).replace("-", " ")


def main():
    try:
        with open("urunler.csv", newline="", encoding="utf-8") as f:
            nolar = set()
            for u in csv.DictReader(f):
                m = re.search(r"-p-(\d+)", u.get("url") or "")
                if m:
                    nolar.add(m.group(1))
    except FileNotFoundError:
        nolar = set()
    try:
        with open("haric.csv", newline="", encoding="utf-8") as f:
            haric = {(s.get("url") or "").strip() for s in csv.DictReader(f)}
    except FileNotFoundError:
        haric = set()
    print(f"urunler.csv: {len(nolar)} trendyol urun no | haric: {len(haric)} url\n")

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        tarayici = p.chromium.launch()
        baglam = tarayici.new_context(locale="tr-TR", user_agent=UA)
        baglam.add_cookies([
            {"name": "countryCode", "value": "TR", "domain": ".trendyol.com", "path": "/"},
            {"name": "language", "value": "tr", "domain": ".trendyol.com", "path": "/"},
            {"name": "storefrontId", "value": "1", "domain": ".trendyol.com", "path": "/"},
        ])
        for pi in (1, 2):
            sayfa = baglam.new_page()
            sayfa.goto(f"{MAGAZA_URL}&pi={pi}", timeout=60000,
                       wait_until="domcontentloaded")
            try:
                sayfa.wait_for_selector("a.product-card", timeout=15000)
            except Exception:
                pass
            sayfa.wait_for_timeout(1500)
            sayfa.evaluate("window.scrollTo(0, 3000)")
            sayfa.wait_for_timeout(2500)
            icerik = sayfa.content()
            sayfa.close()

            parcalar = re.split(r'<a id="(\d+)" class="product-card"', icerik)
            print(f"===== SAYFA {pi}: {(len(parcalar) - 1) // 2} kart =====")
            for i in range(1, len(parcalar) - 1, 2):
                no, govde = parcalar[i], parcalar[i + 1]
                m = re.search(r'href="(/[^"]+-p-' + no + r'[^"]*)"', govde)
                curl = ("https://www.trendyol.com" + m.group(1).split("?")[0]) if m else ""
                m = re.search(r'data-testid="image-img"[^>]*alt="([^"]+)"', govde)
                alt_ad = html_mod.unescape(m.group(1)).strip() if m else ""
                guncel = None
                for m3 in re.finditer(r'class="([^"]*price[^"]*)"[^>]*>\s*([\d.,]+)\s*TL', govde):
                    if "strikethrough" in m3.group(1) or "old" in m3.group(1):
                        continue
                    deger = float(m3.group(2).replace(".", "").replace(",", "."))
                    if "price-section" in m3.group(1):
                        guncel = deger
                        break
                    if guncel is None:
                        guncel = deger

                ad_g = alt_ad or model_adi(curl)
                if no in nolar:
                    karar = "ESLESIR (listede)"
                elif guncel is None:
                    karar = "ELENIR: fiyat yok"
                elif guncel < TABAN_FIYAT:
                    karar = f"ELENIR: taban alti ({guncel})"
                elif not curl:
                    karar = "ELENIR: url yok"
                elif curl in haric:
                    karar = "ELENIR: haric listesi"
                elif not uygun_mu(ad_g):
                    karar = "ELENIR: uygun_mu=False"
                else:
                    karar = "KESFE GIRER"
                print(f"[{karar}] no={no} fiyat={guncel} alt_ad={alt_ad[:55]!r}")
        tarayici.close()


if __name__ == "__main__":
    main()
