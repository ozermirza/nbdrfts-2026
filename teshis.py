# -*- coding: utf-8 -*-
# TESHIS ARACI: Trendyol ve Hepsiburada'nin robota ne gonderdigini raporlar.
import requests

URLLER = [
    "https://www.trendyol.com/sipnjoy/flipsip-cocuk-su-termosu-360-ml-dino-p-983400822",
    "https://www.hepsiburada.com/sipnjoy-flipsip-cocuk-su-termosu-360-ml-bee-honey-pm-HBC0000G0K7WD",
]

BASIT = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9",
}
TAM = {
    **BASIT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Ch-Ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

IPUCLARI = ["captcha", "challenge", "robot", "cloudflare", "queue", "erisim", "engel", "denied"]

for url in URLLER:
    for ad, basliklar in (("BASIT", BASIT), ("TAM", TAM)):
        print(f"\n{'='*60}\n{url[:60]}... | profil: {ad}")
        try:
            c = requests.get(url, headers=basliklar, timeout=20)
            metin = c.text.lower()
            print(f"HTTP kodu: {c.status_code} | sayfa boyutu: {len(c.text)} karakter")
            bulunan = [k for k in IPUCLARI if k in metin]
            print(f"Robot-duvari ipuclari: {bulunan if bulunan else 'yok'}")
            print(f"Fiyat izi ('price' gecen yer sayisi): {metin.count('price')}")
            print(f"Ilk 300 karakter: {c.text[:300]!r}")
        except requests.RequestException as hata:
            print(f"Baglanti hatasi: {hata}")
