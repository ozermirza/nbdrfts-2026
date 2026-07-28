# -*- coding: utf-8 -*-
# TESHIS ARACI - surum 2
# Bolum 1: Trendyol & Hepsiburada'yi bassiz tarayiciyla dene (JavaScript calistirarak)
# Bolum 2: sipnjoylife varyant deneyi (ayni sayfa mi, gomulu varyant fiyati var mi?)

import hashlib
import re
import requests
from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

print("=" * 60)
print("BOLUM 1: BASSIZ TARAYICI DENEMESI")

URLLER = [
    "https://www.trendyol.com/sipnjoy/flipsip-cocuk-su-termosu-360-ml-dino-p-983400822",
    "https://www.hepsiburada.com/sipnjoy-flipsip-cocuk-su-termosu-360-ml-bee-honey-pm-HBC0000G0K7WD",
]

with sync_playwright() as p:
    tarayici = p.chromium.launch()
    for url in URLLER:
        print(f"\n--- {url[:65]}...")
        sayfa = tarayici.new_page(locale="tr-TR", user_agent=UA)
        try:
            sayfa.goto(url, timeout=60000, wait_until="domcontentloaded")
            sayfa.wait_for_timeout(7000)  # JavaScript'in fiyati yuklemesine sure taniyoruz
            html = sayfa.content()
            kucuk = html.lower()
            print(f"Sayfa basligi: {sayfa.title()[:70]}")
            print(f"Boyut: {len(html)} karakter | 'price' gecen yer: {kucuk.count('price')}")
            tl_fiyatlar = re.findall(r"(\d{1,3}(?:\.\d{3})*,\d{2})\s*TL", html)
            print(f"TL kalibinda fiyat gorunumu: {len(tl_fiyatlar)} adet, ilk 5: {tl_fiyatlar[:5]}")
            izler = [k for k in ("captcha", "challenge", "robot", "erisim engel") if k in kucuk]
            print(f"Robot-duvari izleri: {izler if izler else 'yok'}")
        except Exception as hata:
            print(f"HATA: {type(hata).__name__}: {str(hata)[:120]}")
        sayfa.close()
    tarayici.close()

print("\n" + "=" * 60)
print("BOLUM 2: SIPNJOYLIFE VARYANT DENEYI")

TABAN = ("https://sipnjoylife.com/flipsip-paslanmaz-celik-cocuk-su-termosu-"
         "matarasi-suluk-360-ml-sipnjoy-sipnjoylife")
D1, D2 = TABAN + "?Desen=Bee-Honey", TABAN + "?Desen=Dino-Roar"

sayfalar = []
for url in (D1, D2):
    c = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "tr-TR"}, timeout=20)
    sayfalar.append(c.text)
    ozet = hashlib.md5(c.text.encode()).hexdigest()[:12]
    print(f"{url.split('=')[-1]}: kod {c.status_code}, boyut {len(c.text)}, parmak izi {ozet}")

if sayfalar[0] == sayfalar[1]:
    print("SONUC: Iki desen linki BIREBIR AYNI sayfayi dondurdu (parametre okunmuyor).")
else:
    print("SONUC: Sayfalar FARKLI - sunucu Desen parametresine gore icerik degistiriyor.")

metin = sayfalar[0]
sayim = {d: metin.count(d) for d in ("Bee-Honey", "Dino-Roar", "Mermaid-Dream")}
print(f"Desen isimleri tek sayfada kac kez geciyor: {sayim}")
for kalip in (r'"price"\s*:\s*[\d.]+', r'variant', r'urunFiyat|productPrice|fiyat"'):
    bulunan = re.findall(kalip, metin, re.I)
    print(f"Kalip {kalip!r}: {len(bulunan)} eslesme, ilk 3: {bulunan[:3]}")
