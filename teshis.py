# -*- coding: utf-8 -*-
# TESHIS ARACI - surum 18
# Amac: PopCorner Trendyol magazasini (mid=849084) GitHub'dan okumayi
#       YENIDEN denemek. 4 strateji sirayla test edilir, her biri ne
#       gordugunu acikca loglar. Hicbiri calismazsa Faz 4 (yerel robot)
#       kesinlesir.
#
# TEST 1: duz requests ile sr sayfasi (boyut + kart sayisi + duvar tespiti)
# TEST 2: Trendyol arama API'si (apigw sonsuz kaydirma servisi, JSON)
# TEST 3: Playwright + taze baglam + 3 deneme (surum 19 sigortasinin
#         guclendirilmis hali)
# TEST 4: Playwright ile URL varyantlari (lc'siz sr + mobil UA)

import json
import re
import time

import requests

MID = "849084"   # Pop Corner
SR_URL = f"https://www.trendyol.com/sr?wb=103069&lc=103714%2C1193&os=1&mid={MID}"
SR_URL_LCSIZ = f"https://www.trendyol.com/sr?wb=103069&os=1&mid={MID}"
API_URL = ("https://apigw.trendyol.com/discovery-web-searchgw-service/v2/api/"
           f"infinite-scroll/sr?wb=103069&lc=103714,1193&os=1&mid={MID}"
           "&pi=1&culture=tr-TR&storefrontId=1")

UA_MASA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
UA_MOBIL = ("Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36")

BASLIKLAR = {"User-Agent": UA_MASA, "Accept-Language": "tr-TR,tr;q=0.9"}
CEREZLER = {"countryCode": "TR", "language": "tr", "storefrontId": "1"}


def kart_say(icerik):
    return len(re.findall(r'<a id="\d+" class="product-card"', icerik))


def ozet(icerik):
    """Sayfanin gorunur metninden ilk 200 karakter (duvar mesaji var mi?)."""
    metin = re.sub(r"<script.*?</script>", " ", icerik, flags=re.S)
    metin = re.sub(r"<style.*?</style>", " ", metin, flags=re.S)
    metin = re.sub(r"<[^>]+>", " ", metin)
    metin = re.sub(r"\s+", " ", metin).strip()
    return metin[:200]


def ilk_adlar(icerik, adet=5):
    adlar = re.findall(r'data-testid="image-img"[^>]*alt="([^"]+)"', icerik)
    return adlar[:adet]


def test1_requests():
    print("\n===== TEST 1: duz requests (sr sayfasi) =====")
    try:
        r = requests.get(SR_URL, headers=BASLIKLAR, cookies=CEREZLER, timeout=30)
        print(f"durum={r.status_code}  boyut={len(r.text)//1024}KB  "
              f"kart={kart_say(r.text)}")
        print(f"gorunur metin: {ozet(r.text)}")
    except Exception as h:
        print(f"HATA: {h}")


def test2_api():
    print("\n===== TEST 2: arama API'si (apigw, JSON) =====")
    b = dict(BASLIKLAR)
    b["Accept"] = "application/json"
    try:
        r = requests.get(API_URL, headers=b, cookies=CEREZLER, timeout=30)
        print(f"durum={r.status_code}  boyut={len(r.text)//1024}KB")
        try:
            veri = r.json()
        except json.JSONDecodeError:
            print(f"JSON degil. Ilk 200 karakter: {r.text[:200]}")
            return
        # urun listesini agacin icinde ara
        urunler = None
        def bul(d):
            nonlocal urunler
            if urunler is not None:
                return
            if isinstance(d, dict):
                p = d.get("products")
                if isinstance(p, list) and p and isinstance(p[0], dict):
                    urunler = p
                    return
                for v in d.values():
                    bul(v)
            elif isinstance(d, list):
                for v in d:
                    bul(v)
        bul(veri)
        if not urunler:
            print(f"JSON geldi ama urun listesi yok. Ust anahtarlar: "
                  f"{list(veri)[:10]}")
            return
        print(f"URUN LISTESI BULUNDU: {len(urunler)} urun (sayfa 1)")
        for u in urunler[:5]:
            ad = u.get("name") or ""
            no = u.get("id") or ""
            fiyat = ""
            p = u.get("price")
            if isinstance(p, dict):
                fiyat = (p.get("discountedPrice") or p.get("sellingPrice")
                         or p.get("originalPrice") or "")
                if isinstance(fiyat, dict):
                    fiyat = fiyat.get("value") or fiyat.get("text") or ""
            print(f"  p-{no} | {str(ad)[:50]} | fiyat={fiyat}")
        # varyant/desen yapisini gormek icin ilk urunun anahtarlarini bas
        print(f"ilk urunun anahtarlari: {sorted(urunler[0].keys())[:20]}")
    except Exception as h:
        print(f"HATA: {h}")


def playwright_dene(url, ua, etiket, deneme_sayisi=3):
    from playwright.sync_api import sync_playwright
    print(f"\n===== {etiket} =====")
    print(f"url: {url}")
    with sync_playwright() as p:
        tarayici = p.chromium.launch()
        for deneme in range(1, deneme_sayisi + 1):
            baglam = tarayici.new_context(locale="tr-TR", user_agent=ua)
            baglam.add_cookies([
                {"name": "countryCode", "value": "TR",
                 "domain": ".trendyol.com", "path": "/"},
                {"name": "language", "value": "tr",
                 "domain": ".trendyol.com", "path": "/"},
                {"name": "storefrontId", "value": "1",
                 "domain": ".trendyol.com", "path": "/"},
            ])
            sayfa = baglam.new_page()
            try:
                sayfa.goto(url, timeout=60000, wait_until="domcontentloaded")
                try:
                    sayfa.wait_for_selector("a.product-card", timeout=15000)
                except Exception:
                    pass
                sayfa.wait_for_timeout(2000)
                sayfa.evaluate("window.scrollTo(0, 3000)")
                sayfa.wait_for_timeout(3000)
                icerik = sayfa.content()
                kk = kart_say(icerik)
                print(f"deneme {deneme}: boyut={len(icerik)//1024}KB  kart={kk}")
                if kk:
                    for ad in ilk_adlar(icerik):
                        print(f"  kart adi: {ad[:60]}")
                    sayfa.close()
                    baglam.close()
                    break
                print(f"  gorunur metin: {ozet(icerik)}")
                print(f"  son url: {sayfa.url[:100]}")
            except Exception as h:
                print(f"deneme {deneme}: HATA {h}")
            sayfa.close()
            baglam.close()
            time.sleep(5)
        tarayici.close()


def main():
    test1_requests()
    test2_api()
    playwright_dene(SR_URL, UA_MASA,
                    "TEST 3: Playwright + taze baglam + 3 deneme")
    playwright_dene(SR_URL_LCSIZ, UA_MOBIL,
                    "TEST 4: lc'siz URL + mobil UA", deneme_sayisi=2)
    print("\nTeshis bitti.")


if __name__ == "__main__":
    main()
