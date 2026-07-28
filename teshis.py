# -*- coding: utf-8 -*-
# TESHIS ARACI - surum 3
# Soru 1: Trendyol bizi nereye yonlendiriyor?
# Soru 2: sipnjoylife'in gomulu varyant verisi hangi yapida?

import re
import requests
from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

print("=" * 60)
print("SORU 1: TRENDYOL YONLENDIRME TAKIBI")
URL = "https://www.trendyol.com/sipnjoy/flipsip-cocuk-su-termosu-360-ml-dino-p-983400822"

with sync_playwright() as p:
    tarayici = p.chromium.launch()
    sayfa = tarayici.new_page(locale="tr-TR", user_agent=UA)
    try:
        sayfa.goto(URL, timeout=60000, wait_until="domcontentloaded")
        sayfa.wait_for_timeout(7000)
        print(f"Istedigimiz adres : {URL}")
        print(f"Vardigimiz adres  : {sayfa.url}")
        print(f"Sayfa basligi     : {sayfa.title()[:80]}")
    except Exception as hata:
        print(f"HATA: {type(hata).__name__}: {str(hata)[:120]}")
    sayfa.close()
    tarayici.close()

print("\n" + "=" * 60)
print("SORU 2: SIPNJOYLIFE GOMULU VERI YAPISI")
TABAN = ("https://sipnjoylife.com/flipsip-paslanmaz-celik-cocuk-su-termosu-"
         "matarasi-suluk-360-ml-sipnjoy-sipnjoylife")
c = requests.get(TABAN, headers={"User-Agent": UA, "Accept-Language": "tr-TR"}, timeout=20)
metin = c.text
print(f"Kod {c.status_code}, boyut {len(metin)}")

# productPrice gecen ilk 4 yerin etrafindaki 250'ser karakteri goster
for i, es in enumerate(re.finditer(r'[Pp]roductPrice', metin)):
    if i >= 4:
        break
    b = max(0, es.start() - 60)
    print(f"\n--- ORNEK {i+1} (konum {es.start()}):")
    print(metin[b:es.start() + 190].replace("\n", " ")[:250])

# Desen adlarinin etrafina da bakalim (fiyatla yan yana mi?)
es = re.search(r'Bee-Honey', metin)
if es:
    b = max(0, es.start() - 150)
    print(f"\n--- 'Bee-Honey' cevresi (konum {es.start()}):")
    print(metin[b:es.start() + 350].replace("\n", " ")[:500])
