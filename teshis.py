# -*- coding: utf-8 -*-
# TESHIS ARACI - surum 12
# Amac: Mareas (Cool Bottles) Trendyol magazasi GitHub'dan okunabiliyor mu?

import re

MAGAZA_URL = "https://www.trendyol.com/sr?lc=1193&os=1&mid=391392"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def main():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        tarayici = p.chromium.launch()
        baglam = tarayici.new_context(locale="tr-TR", user_agent=UA)
        baglam.add_cookies([
            {"name": "countryCode", "value": "TR", "domain": ".trendyol.com", "path": "/"},
            {"name": "language", "value": "tr", "domain": ".trendyol.com", "path": "/"},
            {"name": "storefrontId", "value": "1", "domain": ".trendyol.com", "path": "/"},
        ])
        for pi in (1, 2, 3):
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
            kartlar = re.findall(r'<a id="(\d+)" class="product-card"', icerik)
            adlar = re.findall(r'data-testid="image-img"[^>]*alt="([^"]{5,80})"', icerik)
            print(f"sayfa {pi}: {len(icerik)} karakter, {len(kartlar)} kart")
            for a in adlar[:6]:
                print("   ornek:", a)
            if not kartlar:
                break
        tarayici.close()


if __name__ == "__main__":
    main()
