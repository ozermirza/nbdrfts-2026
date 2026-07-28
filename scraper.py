# -*- coding: utf-8 -*-
# FIYAT RADARI - scraper.py (surum 5)
# Yenilikler (surum 4 uzerine):
#  - Trendyol: uc katmanli, taksit-gecirmez fiyat sokucu (gomulu veri > DOM > genel kalip)
#  - fiyat_bul: taksit yazimlari temizlenir, kurussuz fiyatlar (2.090 TL) taninir

import csv
import difflib
import json
import random
import re
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor

import requests

BASLIKLAR = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "tr-TR,tr;q=0.9",
}
TURKIYE_SAATI = timezone(timedelta(hours=3))
SUTUNLAR = ["tarih", "marka", "seri_adi", "varyant", "kategori1", "hacim",
            "kategori2", "platform", "fiyat", "durum", "url"]


def slugla(metin):
    """Metni link-benzeri hale getirir: 'Çocuk Suluğu' -> 'cocuk-sulugu'"""
    harfler = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosucgiosu")
    metin = metin.translate(harfler).lower()
    return re.sub(r"[^a-z0-9]+", "-", metin).strip("-")


def varyant_bul(url):
    p = parse_qs(urlparse(url).query)
    for anahtar in ("Desen", "Renk", "desen", "renk"):
        if anahtar in p:
            return p[anahtar][0]
    return ""


def fiyat_bul(html):
    """JSON-LD, olmazsa bilinen kaliplar, olmazsa taksitten arindirilmis TL yazimi."""
    for blok in re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.S
    ):
        try:
            veri = json.loads(blok.strip())
        except json.JSONDecodeError:
            continue
        for aday in (veri if isinstance(veri, list) else [veri]):
            if not isinstance(aday, dict):
                continue
            offers = aday.get("offers")
            if isinstance(offers, list) and offers:
                offers = offers[0]
            if isinstance(offers, dict):
                ham = offers.get("price") or offers.get("lowPrice")
                if ham:
                    return float(str(ham).replace(",", "."))
    m = re.search(
        r'"(?:discountedPrice|sellingPrice|price)"\s*:\s*\{[^{}]*"value"\s*:\s*([0-9]+(?:[.,][0-9]+)?)',
        html,
    ) or re.search(r'"(?:discountedPrice|sellingPrice|price)"\s*:\s*([0-9]+(?:[.,][0-9]+)?)', html)
    if m:
        return float(m.group(1).replace(",", "."))
    temiz = re.sub(r"\d+\s*x\s*[\d.,]+\s*TL", " ", html)  # taksit yazimlarini sil
    m = re.search(r"(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*TL", temiz)
    if m:
        return float(m.group(1).replace(".", "").replace(",", "."))
    return None


def kayit(urun, simdi, fiyat, durum, varyant=None, url=None):
    return {
        "tarih": simdi, "marka": urun["marka"], "seri_adi": urun["seri_adi"],
        "varyant": varyant if varyant is not None else varyant_bul(urun["url"]),
        "kategori1": urun["kategori1"], "hacim": urun["hacim"],
        "kategori2": urun["kategori2"], "platform": urun["platform"],
        "fiyat": fiyat if fiyat is not None else "", "durum": durum,
        "url": url or urun["url"].strip(),
    }


def tek_tek_cek(urun):
    try:
        c = requests.get(urun["url"].strip(), headers=BASLIKLAR, timeout=20)
        if c.status_code != 200:
            return None, f"http_{c.status_code}"
        f = fiyat_bul(c.text)
        return f, ("ok" if f is not None else "fiyat_bulunamadi")
    except requests.RequestException:
        return None, "baglanti_hatasi"


# ---------------- SIPNJOYLIFE: varyant sokucu ----------------

def gez(dugum):
    """JSON agacindaki tum sozlukleri dolasan yardimci (recursive gezgin)."""
    if isinstance(dugum, dict):
        yield dugum
        for v in dugum.values():
            yield from gez(v)
    elif isinstance(dugum, list):
        for v in dugum:
            yield from gez(v)


def nextdata_katalog(url):
    """Sayfadaki __NEXT_DATA__ icinden tum urunleri cikarir:
    {urun_slug: [(varyant_adi, fiyat), ...]}"""
    try:
        html = requests.get(url, headers=BASLIKLAR, timeout=30).text
    except requests.RequestException:
        return None
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None
    try:
        veri = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None

    katalog = {}
    for d in gez(veri):
        if not (isinstance(d.get("variants"), list) and d.get("name") and d["variants"]):
            continue
        varyantlar = []
        for v in d["variants"]:
            if not isinstance(v, dict):
                continue
            ad = ""
            vv = v.get("variantValues")
            if isinstance(vv, list) and vv and isinstance(vv[0], dict):
                ad = vv[0].get("name", "") or ""
            fiy = None
            pr = v.get("prices")
            if isinstance(pr, list) and pr and isinstance(pr[0], dict):
                fiy = pr[0].get("discountPrice") or pr[0].get("sellPrice")
            if fiy is not None:
                varyantlar.append((ad, float(fiy)))
        if varyantlar:
            katalog[slugla(d["name"])] = varyantlar
    return katalog or None


def nextdata_iscisi(urunler, simdi):
    """sipnjoylife tarzi siteler: katalogu bir kez cek, urunleri eslestir,
    her varyanti ayri satir yaz. Olmazsa klasik yonteme don."""
    katalog = nextdata_katalog(urunler[0]["url"].strip())
    sonuclar = []

    # Ayni urunun farkli ?Desen= linkleri tek sayfadir: yol bazinda tekille
    tekil = {}
    for u in urunler:
        yol = urlparse(u["url"].strip()).path
        tekil.setdefault(yol, u)

    for yol, u in tekil.items():
        url_slug = yol.strip("/")
        eslesme = None
        if katalog:
            puanli = [(difflib.SequenceMatcher(None, url_slug, k).ratio(), k)
                      for k in katalog]
            puan, anahtar = max(puanli)
            if puan > 0.5:
                eslesme = anahtar
        if eslesme:
            for varyant_adi, fiyat in katalog[eslesme]:
                sonuclar.append(kayit(u, simdi, fiyat, "ok", varyant=varyant_adi))
            print(f"[nextdata] {u['seri_adi']}: {len(katalog[eslesme])} varyant alindi")
        else:
            f, durum = tek_tek_cek(u)
            if durum == "ok":
                durum = "model_fiyati"  # varyant eslesmedi, genel fiyat alindi
            sonuclar.append(kayit(u, simdi, f, durum, varyant=""))
            print(f"[nextdata] {u['seri_adi']}: eslesme yok, {durum}")
            time.sleep(random.uniform(2, 4))
    return sonuclar


# ---------------- TRENDYOL: cerezli bassiz tarayici + katmanli sokucu ----------------

def trendyol_fiyat_sok(sayfa):
    """Uc katmanli fiyat sokucu. (fiyat, kaynak) doner."""
    # KATMAN 1: sayfaya gomulu resmi urun verisi (en guvenilir)
    try:
        ham = sayfa.evaluate(
            "() => JSON.stringify(window.__PRODUCT_DETAIL_APP_INITIAL_STATE__ || null)")
        if ham and ham != "null":
            for d in gez(json.loads(ham)):
                for alan in ("discountedPrice", "sellingPrice"):
                    v = d.get(alan)
                    if isinstance(v, dict) and isinstance(v.get("value"), (int, float)):
                        return float(v["value"]), f"gomulu_{alan}"
    except Exception:
        pass
    # KATMAN 2: fiyatin durdugu HTML elemanini hedefle
    for secici in ("span.prc-dsc", "[data-testid*='price']", "[class*='price-view']"):
        try:
            el = sayfa.locator(secici).first
            if el.count() > 0:
                m = re.search(r"(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*TL",
                              el.inner_text(timeout=2000))
                if m:
                    return float(m.group(1).replace(".", "").replace(",", ".")), "dom"
        except Exception:
            continue
    # KATMAN 3: taksitten arindirilmis genel TL taramasi
    f = fiyat_bul(sayfa.content())
    return (f, "genel_kalip") if f is not None else (None, None)


def trendyol_iscisi(urunler, simdi):
    from playwright.sync_api import sync_playwright
    sonuclar = []
    with sync_playwright() as p:
        tarayici = p.chromium.launch()
        baglam = tarayici.new_context(locale="tr-TR", user_agent=BASLIKLAR["User-Agent"])
        baglam.add_cookies([
            {"name": "countryCode", "value": "TR", "domain": ".trendyol.com", "path": "/"},
            {"name": "language", "value": "tr", "domain": ".trendyol.com", "path": "/"},
            {"name": "storefrontId", "value": "1", "domain": ".trendyol.com", "path": "/"},
        ])
        for u in urunler:
            fiyat, durum, kaynak = None, "ok", None
            sayfa = baglam.new_page()
            try:
                sayfa.goto(u["url"].strip(), timeout=60000, wait_until="domcontentloaded")
                sayfa.wait_for_timeout(5000)
                if "select-country" in sayfa.url:
                    durum = "ulke_kapisi"
                else:
                    fiyat, kaynak = trendyol_fiyat_sok(sayfa)
                    durum = "ok" if fiyat is not None else "fiyat_bulunamadi"
            except Exception:
                durum = "baglanti_hatasi"
            sayfa.close()
            sonuclar.append(kayit(u, simdi, fiyat, durum))
            print(f"[trendyol] {u['seri_adi']} {varyant_bul(u['url'])}: {fiyat} "
                  f"[{durum}, kaynak={kaynak}]")
            time.sleep(random.uniform(2, 4))
        tarayici.close()
    return sonuclar


# ---------------- SHOPIFY (popcorner) ve genel isci ----------------

def shopify_dokum_al(alan_adi):
    dokum = {}
    try:
        for sayfa_no in range(1, 5):
            url = f"https://{alan_adi}/products.json?limit=250&page={sayfa_no}"
            c = requests.get(url, headers=BASLIKLAR, timeout=20)
            if c.status_code != 200:
                return dokum or None
            urunler = c.json().get("products", [])
            if not urunler:
                break
            for u in urunler:
                for v in u.get("variants", []):
                    if v.get("price"):
                        dokum.setdefault(u["handle"], []).append(
                            (v.get("title", "") or "", float(v["price"])))
            time.sleep(2)
    except (requests.RequestException, ValueError):
        return dokum or None
    return dokum or None


def site_iscisi(alan_adi, urunler, simdi):
    if "trendyol" in alan_adi:
        return trendyol_iscisi(urunler, simdi)
    if "sipnjoylife" in alan_adi:
        return nextdata_iscisi(urunler, simdi)

    sonuclar = []
    dokum = shopify_dokum_al(alan_adi) if any("/products/" in u["url"] for u in urunler) else None
    if dokum:
        print(f"[{alan_adi}] Shopify dokumu: {len(dokum)} urun")
    for u in urunler:
        url = u["url"].strip()
        if dokum is not None:
            parcalar = urlparse(url).path.split("/products/")
            handle = parcalar[1].split("/")[0].split("?")[0] if len(parcalar) > 1 else ""
            if handle in dokum:
                for varyant_adi, fiyat in dokum[handle]:
                    sonuclar.append(kayit(u, simdi, fiyat, "ok", varyant=varyant_adi))
                continue
        f, durum = tek_tek_cek(u)
        sonuclar.append(kayit(u, simdi, f, durum))
        print(f"[{alan_adi}] {u['seri_adi']}: {f} [{durum}]")
        time.sleep(random.uniform(3, 6))
    return sonuclar


def main():
    with open("urunler.csv", newline="", encoding="utf-8") as f:
        urunler = [u for u in csv.DictReader(f) if (u.get("url") or "").strip()]

    gruplar = {}
    for u in urunler:
        gruplar.setdefault(urlparse(u["url"].strip()).netloc, []).append(u)

    simdi = datetime.now(TURKIYE_SAATI).strftime("%Y-%m-%d %H:%M")
    print(f"{len(urunler)} satir, {len(gruplar)} site, paralel tarama basliyor...")

    tum = []
    with ThreadPoolExecutor(max_workers=len(gruplar)) as havuz:
        for is_ in [havuz.submit(site_iscisi, a, g, simdi) for a, g in gruplar.items()]:
            tum.extend(is_.result())

    try:
        with open("fiyatlar.csv", "r", encoding="utf-8") as f:
            bos = f.readline().strip() == ""
    except FileNotFoundError:
        bos = True
    with open("fiyatlar.csv", "a", newline="", encoding="utf-8") as f:
        y = csv.DictWriter(f, fieldnames=SUTUNLAR)
        if bos:
            y.writeheader()
        y.writerows(tum)
    print(f"\nBitti: {len(tum)} kayit eklendi.")


if __name__ == "__main__":
    main()
