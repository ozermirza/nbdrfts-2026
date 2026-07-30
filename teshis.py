# -*- coding: utf-8 -*-
# TESHIS ARACI - surum 8
# Amac: color-variants cevabindaki varyant kaydinin TAM yapisini gormek
# (fiyat alaninin adi/bicimi) ve Trixie sayfasinin sessizligini anlamak.

import json

HEDEFLER = [
    ("Trixie", "https://www.trendyol.com/sr?wb=103069&lc=103714%2C1193&os=1&mid=849084&pi=1"),
    ("SipnJoy", "https://www.trendyol.com/sr?lc=103714%2C1193&os=1&mid=1095234&pi=1"),
]


def incele(baglam, ad, url):
    print(f"\n{'='*70}\n{ad}: {url[:90]}")
    yakalanan = []
    sayfa = baglam.new_page()

    def topla(yanit):
        try:
            if "color-variants" in yanit.url:
                yakalanan.append(yanit.text())
        except Exception:
            pass
    sayfa.on("response", topla)

    try:
        sayfa.goto(url, timeout=60000, wait_until="domcontentloaded")
        sayfa.wait_for_timeout(4000)
        # kupon penceresi varsa kapat
        for secici in ("[class*='close']", "[data-testid*='close']"):
            try:
                el = sayfa.locator(secici).first
                if el.count() > 0:
                    el.click(timeout=1500)
                    print("  (bir pencere kapatildi)")
                    break
            except Exception:
                pass
        sayfa.evaluate("window.scrollTo(0, 2500)")
        sayfa.wait_for_timeout(4000)
        sayfa.evaluate("window.scrollTo(0, 6000)")
        sayfa.wait_for_timeout(4000)
    except Exception as h:
        print("HATA:", h)
    sayfa.close()

    print(f"color-variants cevabi: {len(yakalanan)} adet")
    for govde in yakalanan[:2]:
        try:
            veri = json.loads(govde)
        except json.JSONDecodeError:
            print("  JSON okunamadi"); continue
        print(f"  grup sayisi: {len(veri)}")
        for gid, liste in list(veri.items())[:1]:
            print(f"  ornek grup {gid}: {len(liste)} varyant")
            if liste:
                print("  VARYANT KAYDI (tam):")
                print("  " + json.dumps(liste[0], ensure_ascii=False)[:900])


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
        for ad, url in HEDEFLER:
            incele(baglam, ad, url)
        tarayici.close()


if __name__ == "__main__":
    main()
