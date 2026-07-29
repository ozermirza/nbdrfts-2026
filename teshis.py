# -*- coding: utf-8 -*-
# TESHIS ARACI - surum 6
# Amac: bos gelen Trendyol sayfalarinin robota NE dondugunu anlamak:
# bot filtresi mi, yeni altyapi mi, gec yukleme mi?

import json
import re

import requests

HEDEFLER = [
    # bos gelen sayfa:
    "https://www.trendyol.com/trixie/41-222-bottle-500ml-mrs-cat-p-753701975?boutiqueId=61&merchantId=849084",
    # ayni turda SORUNSUZ okunan bir sayfa (kiyas icin):
    "https://www.trendyol.com/trixie/mr-lion-paslanmaz-celik-suluk-500-ml-pipetsiz-su-matarasi-cocuk-matara-p-754496489?boutiqueId=61&merchantId=849084",
]

BASLIKLAR = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "tr-TR,tr;q=0.9",
}


def metin_raporu(kaynak, metin):
    tl = len(re.findall(r"\d[\d.,]*\s*TL", metin))
    isaretler = [k for k in ("captcha", "robot", "denied", "challenge", "tukendi",
                             "Tükendi", "cf-", "cloudflare") if k in metin]
    print(f"  [{kaynak}] uzunluk={len(metin)}, TL-yazimi={tl}, isaretler={isaretler}")
    m = re.search(r"<title>(.*?)</title>", metin, re.S)
    if m:
        print(f"  [{kaynak}] title: {m.group(1).strip()[:80]!r}")
    ilk = re.findall(r"(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*TL", metin)[:5]
    print(f"  [{kaynak}] ilk TL degerleri: {ilk}")


def incele(baglam, url):
    print(f"\n{'='*70}\nURL: {url[:95]}")

    # 1) Duz HTTP istegi ne goruyor?
    try:
        c = requests.get(url, headers=BASLIKLAR, timeout=30)
        print(f"  [requests] durum={c.status_code}")
        metin_raporu("requests", c.text)
        varmi = "__PRODUCT_DETAIL_APP_INITIAL_STATE__" in c.text
        print(f"  [requests] gomulu degisken metinde var mi: {varmi}")
    except requests.RequestException as h:
        print(f"  [requests] HATA: {h}")

    # 2) Bassiz tarayici uzun bekleyisle ne goruyor?
    sayfa = baglam.new_page()
    try:
        sayfa.goto(url, timeout=60000, wait_until="domcontentloaded")
        try:
            sayfa.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            print("  [tarayici] networkidle beklenirken zaman asimi (trafik surdu)")
        sayfa.wait_for_timeout(3000)
        print(f"  [tarayici] varilan: {sayfa.url[:95]}")
        icerik = sayfa.content()
        metin_raporu("tarayici", icerik)
        anahtarlar = sayfa.evaluate(
            "() => Object.getOwnPropertyNames(window).filter(k => k.includes('__') "
            "|| k.toUpperCase().includes('PRODUCT') || k.toUpperCase().includes('STATE'))")
        print(f"  [tarayici] ilgili window degiskenleri: {anahtarlar[:15]}")
    except Exception as h:
        print(f"  [tarayici] HATA: {h}")
    sayfa.close()


def main():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        tarayici = p.chromium.launch()
        baglam = tarayici.new_context(locale="tr-TR",
                                      user_agent=BASLIKLAR["User-Agent"])
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
