# -*- coding: utf-8 -*-
# TESHIS ARACI - surum 7
# Amac: Trendyol magaza (sr) sayfasinin fiyatlari HANGI arka plan cevabiyla
# aldigini bulmak. Tum JSON cevaplarinin envanteri cikarilir.

import json
import re

HEDEFLER = [
    "https://www.trendyol.com/sr?wb=103069&lc=103714%2C1193&os=1&mid=849084&pi=1",
    "https://www.trendyol.com/sr?lc=103714%2C1193&os=1&mid=1095234&pi=1",
]


def incele(baglam, url):
    print(f"\n{'='*70}\nSAYFA: {url[:90]}")
    kayitlar = []
    sayfa = baglam.new_page()

    def topla(yanit):
        try:
            ct = yanit.headers.get("content-type") or ""
            if "json" not in ct:
                return
            govde = yanit.text()
            kayitlar.append((yanit.url, len(govde), govde[:400]))
        except Exception:
            pass
    sayfa.on("response", topla)

    try:
        sayfa.goto(url, timeout=60000, wait_until="domcontentloaded")
        sayfa.wait_for_timeout(5000)
        # fiyatlar kaydirinca mi geliyor? yarim sayfa in, tekrar dinle
        sayfa.evaluate("window.scrollTo(0, 1500)")
        sayfa.wait_for_timeout(4000)
        sayfa.evaluate("window.scrollTo(0, 4000)")
        sayfa.wait_for_timeout(4000)
    except Exception as h:
        print("HATA:", h)
    sayfa.close()

    print(f"Toplam JSON cevabi: {len(kayitlar)}")
    for adres, boy, ornek in kayitlar:
        onemli = []
        for kelime in ('"products"', '"price"', '"sellingPrice"', '"discountedPrice"',
                       '"items"', '"id"'):
            if kelime in ornek:
                onemli.append(kelime.strip('"'))
        print(f"\n--- {adres[:110]}")
        print(f"    boyut={boy}, alanlar={onemli}")
        if any(k in ("price", "sellingPrice", "discountedPrice", "products") for k in onemli):
            print(f"    ornek: {ornek[:350]}")


def main():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        tarayici = p.chromium.launch()
        baglam = tarayici.new_context(
            locale="tr-TR",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"))
        baglam.add_cookies([
            {"name": "countryCode", "value": "TR", "domain": ".trendyol.com", "path": "/"},
            {"name": "language", "value": "tr", "domain": ".trendyol.com", "path": "/"},
            {"name": "storefrontId", "value": "1", "domain": ".trendyol.com", "path": "/"},
        ])
        for url in HEDEFLER:
            incele(baglam, url)
        tarayici.close()


if __name__ == "__main__":
    main()
