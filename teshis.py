# -*- coding: utf-8 -*-
# TESHIS ARACI - surum 10
# Amac: Trendyol-SipnJoy magaza sayfasindaki kartlarin ad/link/fiyat
# sokumunun neden cogu kartta bos dondugunu gormek.

import re

MAGAZA_URL = "https://www.trendyol.com/sr?lc=103714%2C1193&os=1&mid=1095234&pi=1"
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
        try:
            sayfa.wait_for_selector("a.product-card", timeout=15000)
        except Exception:
            pass
        sayfa.wait_for_timeout(1500)
        sayfa.evaluate("window.scrollTo(0, 3000)")
        sayfa.wait_for_timeout(2500)
        icerik = sayfa.content()
        tarayici.close()

    print(f"Sayfa boyutu: {len(icerik)} karakter")
    parcalar = re.split(r'<a id="(\d+)" class="product-card"', icerik)
    print(f"Kart sayisi: {(len(parcalar) - 1) // 2}\n")

    bozuk_ornek = 0
    for i in range(1, len(parcalar) - 1, 2):
        no, govde = parcalar[i], parcalar[i + 1]
        # govdeyi bir sonraki karta kadar sinirla (split zaten yapiyor)

        m = re.search(r'href="(/[^"]+-p-' + no + r'[^"]*)"', govde)
        url_var = "VAR" if m else "YOK"

        m2 = re.search(r'class="product-name[^"]*"[^>]*>([^<]{3,120})<', govde)
        ad = re.sub(r"\s+", " ", m2.group(1)).strip() if m2 else ""

        fiyatlar = []
        for m3 in re.finditer(r'class="([^"]*price[^"]*)"[^>]*>\s*([\d.,]+)\s*TL', govde):
            fiyatlar.append((m3.group(1)[:40], m3.group(2)))

        durum = "OK" if (m and ad and fiyatlar) else "EKSIK"
        print(f"[{durum}] no={no} url={url_var} ad={ad[:45]!r} "
              f"fiyat_adedi={len(fiyatlar)} fiyatlar={fiyatlar[:3]}")

        if durum == "EKSIK" and bozuk_ornek < 2:
            bozuk_ornek += 1
            print(f"\n----- BOZUK KART {bozuk_ornek} (no={no}) HAM HTML ILK 2000 KR -----")
            print(govde[:2000])
            print("----- SON -----\n")


if __name__ == "__main__":
    main()
