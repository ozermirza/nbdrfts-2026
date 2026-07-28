# -*- coding: utf-8 -*-
# TESHIS ARACI - surum 4
# Soru 1: Trendyol'un ulke kapisini cerezle veya tiklamayla gecebiliyor muyuz?
# Soru 2: sipnjoylife'ta varyant fiyatlari sayfanin neresinde (varsa)?

import re
import requests
from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
URL = "https://www.trendyol.com/sipnjoy/flipsip-cocuk-su-termosu-360-ml-dino-p-983400822"


def rapor(sayfa, etiket):
    html = sayfa.content()
    fiyatlar = re.findall(r"(\d{1,3}(?:\.\d{3})*,\d{2})\s*TL", html)
    print(f"[{etiket}] vardigi adres: {sayfa.url[:80]}")
    print(f"[{etiket}] baslik: {sayfa.title()[:70]}")
    print(f"[{etiket}] TL fiyat gorunumu: {len(fiyatlar)} adet, ilk 5: {fiyatlar[:5]}")
    return len(fiyatlar) > 0


print("=" * 60)
print("SORU 1: TRENDYOL ULKE KAPISI")
with sync_playwright() as p:
    tarayici = p.chromium.launch()

    # DENEME A: Turkiye cerezlerini bastan vererek gitmek
    print("\n-- Deneme A: cerezle --")
    baglam = tarayici.new_context(locale="tr-TR", user_agent=UA)
    baglam.add_cookies([
        {"name": "countryCode", "value": "TR", "domain": ".trendyol.com", "path": "/"},
        {"name": "language", "value": "tr", "domain": ".trendyol.com", "path": "/"},
        {"name": "storefrontId", "value": "1", "domain": ".trendyol.com", "path": "/"},
    ])
    sayfa = baglam.new_page()
    try:
        sayfa.goto(URL, timeout=60000, wait_until="domcontentloaded")
        sayfa.wait_for_timeout(6000)
        basarili = rapor(sayfa, "A")
    except Exception as h:
        print(f"[A] HATA: {type(h).__name__}: {str(h)[:100]}")
        basarili = False
    baglam.close()

    # DENEME B: ulke secim sayfasinda Turkiye'ye tiklamak
    if not basarili:
        print("\n-- Deneme B: tiklamayla --")
        baglam = tarayici.new_context(locale="tr-TR", user_agent=UA)
        sayfa = baglam.new_page()
        try:
            sayfa.goto(URL, timeout=60000, wait_until="domcontentloaded")
            sayfa.wait_for_timeout(4000)
            if "select-country" in sayfa.url:
                # Sayfadaki tiklanabilir metinleri gorelim ki dogru dugmeyi taniyalim
                metinler = sayfa.locator("a, button").all_inner_texts()
                print(f"[B] secim sayfasindaki dugme/link metinleri (ilk 15): {metinler[:15]}")
                for aday in ("Türkiye", "Turkey", "Türkiye'den alışveriş"):
                    hedef = sayfa.get_by_text(aday, exact=False).first
                    if hedef.count() > 0:
                        print(f"[B] '{aday}' bulundu, tiklaniyor...")
                        hedef.click()
                        sayfa.wait_for_timeout(6000)
                        break
            rapor(sayfa, "B")
        except Exception as h:
            print(f"[B] HATA: {type(h).__name__}: {str(h)[:100]}")
        baglam.close()
    tarayici.close()

print("\n" + "=" * 60)
print("SORU 2: SIPNJOYLIFE VARYANT VERI AVI")
TABAN = ("https://sipnjoylife.com/flipsip-paslanmaz-celik-cocuk-su-termosu-"
         "matarasi-suluk-360-ml-sipnjoy-sipnjoylife")
metin = requests.get(TABAN, headers={"User-Agent": UA, "Accept-Language": "tr-TR"},
                     timeout=20).text
print(f"Sayfa boyutu: {len(metin)}")

for kalip in (r'"variants"', r'"variantValues"', r'sellingPrice', r'finalPrice',
              r'"prices"', r'"amount"\s*:', r'buyableStockCount', r'__NEXT_DATA__'):
    yerler = [m.start() for m in re.finditer(kalip, metin)]
    print(f"\nKalip {kalip!r}: {len(yerler)} eslesme")
    if yerler:
        b = yerler[0]
        print("  ilk eslesmenin cevresi: " + metin[max(0, b-40):b+260].replace("\n", " ")[:300])
