# -*- coding: utf-8 -*-
# FIYAT RADARI - scraper.py (surum 3)
# Yenilikler:
#  1) Siteler paralel taranir (her siteye bir isci) -> toplam sure ciddi kisalir
#  2) Shopify siteleri (popcorner) icin tek istekte toplu fiyat cekme,
#     basarisiz olursa otomatik olarak tek tek yonteme geri donus

import csv
import json
import re
import random
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor

import requests

BASLIKLAR = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9",
}
TURKIYE_SAATI = timezone(timedelta(hours=3))


def varyant_bul(url):
    """Linkteki ?Desen=... / ?Renk=... bilgisini ayiklar, yoksa bos doner."""
    p = parse_qs(urlparse(url).query)
    for anahtar in ("Desen", "Renk", "desen", "renk"):
        if anahtar in p:
            return p[anahtar][0]
    return ""


def fiyat_bul(html):
    """Sayfa HTML'inden fiyat bulur: once JSON-LD, sonra yedek kaliplar."""
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
    return float(m.group(1).replace(",", ".")) if m else None


def tek_tek_cek(urun):
    """Klasik yontem: urun sayfasina git, fiyati oku."""
    url = urun["url"].strip()
    try:
        cevap = requests.get(url, headers=BASLIKLAR, timeout=20)
        if cevap.status_code != 200:
            return None, f"http_{cevap.status_code}"
        fiyat = fiyat_bul(cevap.text)
        return fiyat, ("ok" if fiyat is not None else "fiyat_bulunamadi")
    except requests.RequestException:
        return None, "baglanti_hatasi"


def shopify_dokum_al(alan_adi):
    """Shopify magazasinin tum urun dokumunu ceker.
    Basarili olursa {urun_handle: en_dusuk_fiyat} sozlugu doner, olmazsa None."""
    dokum = {}
    try:
        for sayfa in range(1, 5):  # 250'lik sayfalarla en fazla 1000 urun
            url = f"https://{alan_adi}/products.json?limit=250&page={sayfa}"
            cevap = requests.get(url, headers=BASLIKLAR, timeout=20)
            if cevap.status_code != 200:
                return None if not dokum else dokum
            urunler = cevap.json().get("products", [])
            if not urunler:
                break
            for u in urunler:
                fiyatlar = [float(v["price"]) for v in u.get("variants", []) if v.get("price")]
                if fiyatlar:
                    dokum[u["handle"]] = min(fiyatlar)
            time.sleep(2)
    except (requests.RequestException, ValueError):
        return None if not dokum else dokum
    return dokum if dokum else None


def site_iscisi(alan_adi, urunler, simdi):
    """Tek bir sitenin tum urunlerini isleyen isci. Her site icin
    bu fonksiyonun ayri bir kopyasi ayni anda calisir."""
    sonuclar = []

    # Shopify kestirmesini dene (linkte /products/ geciyorsa Shopify'dir)
    dokum = None
    if any("/products/" in u["url"] for u in urunler):
        dokum = shopify_dokum_al(alan_adi)
        if dokum:
            print(f"[{alan_adi}] Shopify dokumu alindi: {len(dokum)} urun tek istekte")

    for urun in urunler:
        url = urun["url"].strip()
        fiyat, durum = None, "ok"

        if dokum is not None:
            # Linkten urun kimligini (handle) ayikla: /products/<handle>
            parcalar = urlparse(url).path.split("/products/")
            handle = parcalar[1].split("/")[0].split("?")[0] if len(parcalar) > 1 else ""
            fiyat = dokum.get(handle)
            durum = "ok" if fiyat is not None else "dokumde_yok"
            if fiyat is None:  # dokumde bulunamadiysa klasik yonteme dus
                fiyat, durum = tek_tek_cek(urun)
        else:
            fiyat, durum = tek_tek_cek(urun)
            time.sleep(random.uniform(3, 6))  # ayni siteye nezaket beklemesi

        sonuclar.append({
            "tarih": simdi,
            "marka": urun["marka"],
            "seri_adi": urun["seri_adi"],
            "varyant": varyant_bul(url),
            "kategori1": urun["kategori1"],
            "hacim": urun["hacim"],
            "kategori2": urun["kategori2"],
            "platform": urun["platform"],
            "fiyat": fiyat if fiyat is not None else "",
            "durum": durum,
            "url": url,
        })
        print(f"[{alan_adi}] {urun['marka']} {urun['seri_adi']} {varyant_bul(url)}: {fiyat} [{durum}]")
    return sonuclar


def main():
    with open("urunler.csv", newline="", encoding="utf-8") as f:
        urunler = [u for u in csv.DictReader(f) if (u.get("url") or "").strip()]

    # Urunleri sitelerine gore grupla: {"www.trendyol.com": [...], ...}
    gruplar = {}
    for u in urunler:
        gruplar.setdefault(urlparse(u["url"].strip()).netloc, []).append(u)

    simdi = datetime.now(TURKIYE_SAATI).strftime("%Y-%m-%d %H:%M")
    print(f"{len(urunler)} urun, {len(gruplar)} site, paralel taramaya basliyor...")

    # Her siteye bir isci ata, hepsini ayni anda calistir
    tum_sonuclar = []
    with ThreadPoolExecutor(max_workers=len(gruplar)) as havuz:
        isler = [havuz.submit(site_iscisi, alan, grup, simdi) for alan, grup in gruplar.items()]
        for is_ in isler:
            tum_sonuclar.extend(is_.result())

    sutunlar = ["tarih", "marka", "seri_adi", "varyant", "kategori1", "hacim",
                "kategori2", "platform", "fiyat", "durum", "url"]
    try:
        with open("fiyatlar.csv", "r", encoding="utf-8") as f:
            dosya_bos = f.readline().strip() == ""
    except FileNotFoundError:
        dosya_bos = True
    with open("fiyatlar.csv", "a", newline="", encoding="utf-8") as f:
        yazici = csv.DictWriter(f, fieldnames=sutunlar)
        if dosya_bos:
            yazici.writeheader()
        yazici.writerows(tum_sonuclar)

    print(f"\nBitti: {len(tum_sonuclar)} kayit fiyatlar.csv'ye eklendi.")


if __name__ == "__main__":
    main()
