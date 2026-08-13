# -*- coding: utf-8 -*-
# TESHIS ARACI - surum 19
# Amac: Hepsiburada Mareas magazasini (Cool Bottles) GitHub'dan okumayi
#       denemek. Bilinen durum: HB veri merkezi IP'lerine 403 basar,
#       yerelde sadece GORUNUR pencere geciyor. Yeni koz: TEST 4'te
#       sanal ekran (xvfb) ile "gorunur" tarayici denenir.
#       NOT: TEST 4 icin teshis.yml'de calistirma satiri
#       "xvfb-run --auto-servernum python teshis.py" olmali.
#
# TEST 1: duz requests (durum kodu + duvar tespiti)
# TEST 2: Playwright headless + cerez + masaustu UA
# TEST 3: Playwright headless + mobil UA
# TEST 4: Playwright headed (xvfb sanal ekranda gorunur pencere)

import re
import time

import requests

MAGAZA_URL = ("https://www.hepsiburada.com/magaza/mareas"
              "?markalar=coolbottles&tab=allproducts")

UA_MASA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
UA_MOBIL = ("Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36")


def kart_say(icerik):
    """HB magaza kartlari: '-pm-HB' (ve olasi '-p-HB') linkleri."""
    return len(set(re.findall(r'href="[^"]*-pm?-(HB[A-Z0-9]{8,})', icerik)))


def ozet(icerik):
    metin = re.sub(r"<script.*?</script>", " ", icerik, flags=re.S)
    metin = re.sub(r"<style.*?</style>", " ", metin, flags=re.S)
    metin = re.sub(r"<[^>]+>", " ", metin)
    metin = re.sub(r"\s+", " ", metin).strip()
    return metin[:200]


def test1_requests():
    print("\n===== TEST 1: duz requests =====")
    try:
        r = requests.get(MAGAZA_URL, timeout=30,
                         headers={"User-Agent": UA_MASA,
                                  "Accept-Language": "tr-TR,tr;q=0.9"})
        print(f"durum={r.status_code}  boyut={len(r.text)//1024}KB  "
              f"kart={kart_say(r.text)}")
        print(f"gorunur metin: {ozet(r.text)}")
    except Exception as h:
        print(f"HATA: {h}")


def playwright_dene(etiket, ua, headless, deneme_sayisi=2):
    from playwright.sync_api import sync_playwright
    print(f"\n===== {etiket} =====")
    try:
        with sync_playwright() as p:
            tarayici = p.chromium.launch(headless=headless)
            for deneme in range(1, deneme_sayisi + 1):
                baglam = tarayici.new_context(locale="tr-TR", user_agent=ua)
                sayfa = baglam.new_page()
                try:
                    sayfa.goto(MAGAZA_URL, timeout=60000,
                               wait_until="domcontentloaded")
                    sayfa.wait_for_timeout(5000)
                    sayfa.evaluate("window.scrollTo(0, 3000)")
                    sayfa.wait_for_timeout(3000)
                    icerik = sayfa.content()
                    kk = kart_say(icerik)
                    engel = ("erişim engellendi" in icerik.lower()
                             or "captcha" in icerik.lower())
                    print(f"deneme {deneme}: boyut={len(icerik)//1024}KB  "
                          f"kart={kk}  engel={'EVET' if engel else 'yok'}")
                    if kk:
                        adlar = re.findall(r'title="([^"]{10,80})"', icerik)
                        for ad in adlar[:5]:
                            print(f"  kart adi: {ad}")
                        sayfa.close(); baglam.close()
                        break
                    print(f"  gorunur metin: {ozet(icerik)}")
                    print(f"  son url: {sayfa.url[:100]}")
                except Exception as h:
                    print(f"deneme {deneme}: HATA {h}")
                sayfa.close(); baglam.close()
                time.sleep(5)
            tarayici.close()
    except Exception as h:
        print(f"BASLATILAMADI: {h}")
        if not headless:
            print("  (xvfb yok gibi — teshis.yml'de xvfb-run kullanildigindan"
                  " emin olun)")


def main():
    test1_requests()
    playwright_dene("TEST 2: Playwright headless + masaustu UA",
                    UA_MASA, headless=True)
    playwright_dene("TEST 3: Playwright headless + mobil UA",
                    UA_MOBIL, headless=True)
    playwright_dene("TEST 4: Playwright GORUNUR (xvfb sanal ekran)",
                    UA_MASA, headless=False)
    print("\nTeshis bitti.")


if __name__ == "__main__":
    main()
