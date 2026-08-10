# -*- coding: utf-8 -*-
# TESHIS ARACI - surum 16
# Amac: kidsnjoystore kategori linkleri + urun JSON servis adresi + kart yapisi

import json

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def main():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        tarayici = p.chromium.launch()
        baglam = tarayici.new_context(locale="tr-TR", user_agent=UA)
        sayfa = baglam.new_page()
        json_cevaplar = []

        def topla(y):
            try:
                ct = (y.headers or {}).get("content-type", "")
                if "json" in ct and any(k in y.url.lower()
                                        for k in ("urun", "product", "list", "srv")):
                    json_cevaplar.append((y.url, y.text()[:400]))
            except Exception:
                pass
        sayfa.on("response", topla)

        sayfa.goto("https://kidsnjoystore.com", timeout=60000)
        sayfa.wait_for_timeout(6000)

        linkler = sayfa.eval_on_selector_all(
            "a[href]", "els => [...new Set(els.map(e => e.href))]")
        adaylar = [l for l in linkler
                   if any(k in l.lower() for k in ("termos", "suluk", "matara",
                                                   "bottle", "tumbler"))]
        print("kategori adaylari:")
        for l in adaylar[:12]:
            print("  ", l)

        print("\nana sayfada yakalanan JSON servisleri:")
        for u, ic in json_cevaplar[:6]:
            print("  URL:", u)
            print("  ilk 300:", ic[:300].replace("\n", " "))

        if adaylar:
            json_cevaplar.clear()
            sayfa.goto(adaylar[0], timeout=60000)
            sayfa.wait_for_timeout(6000)
            sayisi = sayfa.eval_on_selector_all(
                ".productItem", "els => els.length")
            print(f"\nkategori sayfasi ({adaylar[0]}): {sayisi} productItem")
            if sayisi:
                ornek = sayfa.eval_on_selector_all(
                    ".productItem", "els => els[0].outerHTML.slice(0, 1500)")
                print("--- ILK KART ---")
                print(ornek[0] if isinstance(ornek, list) else ornek)
            print("\nkategori sayfasi JSON servisleri:")
            for u, ic in json_cevaplar[:6]:
                print("  URL:", u)
                print("  ilk 300:", ic[:300].replace("\n", " "))
        tarayici.close()


if __name__ == "__main__":
    main()
