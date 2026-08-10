# -*- coding: utf-8 -*-
# TESHIS ARACI - surum 13
# Amac: Mareas magazasi sayfa 2'nin yapisini anlamak
# (urunler farkli kart kalibinda mi, yoksa oneri vitrini mi?)

import re

MAGAZA_URL = "https://www.trendyol.com/sr?lc=1193&os=1&mid=391392&pi=2"
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
        sayfa = baglam.new_page()
        sayfa.goto(MAGAZA_URL, timeout=60000, wait_until="domcontentloaded")
        sayfa.wait_for_timeout(2000)
        sayfa.evaluate("window.scrollTo(0, 3000)")
        sayfa.wait_for_timeout(2500)
        icerik = sayfa.content()
        tarayici.close()

    print(f"Sayfa boyutu: {len(icerik)} karakter")
    print("eski kalip (product-card):",
          len(re.findall(r'<a id="(\d+)" class="product-card"', icerik)))
    print("genis kalip (id+class):",
          len(re.findall(r'<a id="\d+"[^>]*class="[^"]*product-card', icerik)))
    print("-p- linkleri:",
          len(set(re.findall(r'href="/[^"]*-p-(\d+)', icerik))))
    for ipucu in ("İlgini çekebilecek", "Benzer ürünler", "onerilen",
                  "recommendation", "suggestion"):
        if ipucu.lower() in icerik.lower():
            print(f"oneri vitrini ipucu: '{ipucu}' GECIYOR")
    i = icerik.find('alt="Cool Bottles')
    if i > 0:
        basla = icerik.rfind("<a ", max(0, i - 3000), i)
        print("\n--- ILK URUNUN KART CEVRESI (a etiketinden itibaren 1200 kr) ---")
        print(icerik[basla:basla + 1200])


if __name__ == "__main__":
    main()
