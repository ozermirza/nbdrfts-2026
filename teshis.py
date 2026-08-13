# -*- coding: utf-8 -*-
# TESHIS ARACI - surum 20
# Amac: HB'nin GitHub'dan xvfb ile okunmasinin ISTIKRAR SINAVI.
# hb_robot.py surum 5'in magaza tarama mantiginin aynisiyla iki magaza
# (SipnJoy + Mareas/CoolBottles) taranir, sonuclar deneme_hb.csv'ye
# EKLENIR (her tetiklemede ustune yazar, turlar karsilastirilir).
# NOT: teshis.yml'de xvfb-run + contents:write + commit adimi olmali.

import csv
import random
import re
import time
from datetime import datetime, timezone, timedelta

TABAN_FIYAT = 500
TURKIYE_SAATI = timezone(timedelta(hours=3))
CIKTI = "deneme_hb.csv"

MAGAZALAR = [
    {"ad": "SipnJoy",
     "taban": ("https://www.hepsiburada.com/magaza/sipnjoy"
               "?filtreler=MainCategory.Id:367285,21005100&tab=allproducts")},
    {"ad": "Mareas-CoolBottles",
     "taban": ("https://www.hepsiburada.com/magaza/mareas"
               "?markalar=coolbottles&tab=allproducts")},
]


def hb_urun_kodu(url):
    m = re.search(r"(HB[A-Z0-9]{8,})", (url or "").upper())
    return m.group(1) if m else None


def metin_fiyat(metin):
    """hb_robot.py ile ayni: taksit/kupon/uzeri kaliplari elenir,
    taban ustu en dusuk deger alinir."""
    if not metin:
        return None
    temiz = re.sub(r"\d+\s*x\s*[\d.,]+\s*TL", " ", metin)
    temiz = re.sub(r"\d[\d.,]*\s*TL\s*(ve|üzeri|uzeri)", " ", temiz)
    adaylar = [float(m.replace(".", "").replace(",", "."))
               for m in re.findall(r"(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*TL", temiz)]
    adaylar = [a for a in adaylar if a >= TABAN_FIYAT]
    return min(adaylar) if adaylar else None


def magaza_tara(sayfa, mag):
    """hb_robot.py magaza_tara'nin aynisi; {kod: (fiyat, ad, url)} dondurur."""
    kartlar = {}
    for no in range(1, 6):
        ek = f"&sayfa={no}" if no > 1 else ""
        try:
            sayfa.goto(mag["taban"] + ek, timeout=60000,
                       wait_until="domcontentloaded")
            sayfa.wait_for_timeout(4000)
            sayfa.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            sayfa.wait_for_timeout(2500)
        except Exception as h:
            print(f"  [{mag['ad']}] sayfa {no}: acilamadi ({h})")
            break
        if "erişim engellendi" in sayfa.content().lower():
            print(f"  [{mag['ad']}] sayfa {no}: ENGELLENDI")
            break
        ham = sayfa.eval_on_selector_all(
            "a[href*='-pm-HB'], a[href*='-p-HB']",
            """els => els.map(e => {
                const kap = e.closest('li') || e.closest('article') || e;
                const img = kap.querySelector('img[alt]');
                return {href: e.href,
                        baslik: e.getAttribute('title')
                                || (img ? img.getAttribute('alt') : '') || '',
                        metin: (kap.innerText || '').slice(0, 400)};
            })""")
        yeni = 0
        for k in ham:
            kod = hb_urun_kodu(k["href"])
            if not kod or kod in kartlar:
                continue
            url = k["href"].split("?")[0]
            ad = (k["baslik"] or k["metin"].split("\n")[0]).strip()
            f = metin_fiyat(k["metin"])
            kartlar[kod] = (f, ad, url)
            yeni += 1
        print(f"  [{mag['ad']}] sayfa {no}: {len(ham)} baglanti, {yeni} yeni "
              f"(toplam {len(kartlar)})")
        if yeni == 0:
            break
        time.sleep(random.uniform(2, 3))
    return kartlar


def main():
    from playwright.sync_api import sync_playwright
    simdi = datetime.now(TURKIYE_SAATI).strftime("%Y-%m-%d %H:%M")
    satirlar = []
    with sync_playwright() as p:
        tarayici = p.chromium.launch(headless=False)   # xvfb sanal ekranda
        baglam = tarayici.new_context(
            locale="tr-TR",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0.0.0 Safari/537.36"))
        sayfa = baglam.new_page()
        for mag in MAGAZALAR:
            print(f"\n===== {mag['ad']} =====")
            kartlar = magaza_tara(sayfa, mag)
            fiyatli = sum(1 for f, _, _ in kartlar.values() if f is not None)
            print(f"  SONUC [{mag['ad']}]: {len(kartlar)} kart, "
                  f"{fiyatli} fiyatli")
            for kod, (f, ad, url) in kartlar.items():
                satirlar.append({"tarih": simdi, "magaza": mag["ad"],
                                 "kod": kod, "ad": ad,
                                 "fiyat": f if f is not None else "",
                                 "url": url})
            time.sleep(random.uniform(3, 5))
        tarayici.close()

    try:
        with open(CIKTI, encoding="utf-8") as f:
            bos = not f.read().strip()
    except FileNotFoundError:
        bos = True
    with open(CIKTI, "a", encoding="utf-8", newline="") as f:
        y = csv.DictWriter(f, fieldnames=["tarih", "magaza", "kod", "ad",
                                          "fiyat", "url"],
                           lineterminator="\n")
        if bos:
            y.writeheader()
        y.writerows(satirlar)
    print(f"\nTeshis bitti: {len(satirlar)} satir {CIKTI} dosyasina eklendi.")


if __name__ == "__main__":
    main()
