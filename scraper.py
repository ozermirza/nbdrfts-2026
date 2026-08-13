# -*- coding: utf-8 -*-
# FIYAT RADARI - scraper.py (surum 20)
# 20: PopCorner-Trixie magazasi acildi (wb=103069'lu URL GitHub'dan okunuyor,
#     13 Agustos teshisiyle kanitlandi; 32 urun p-no ile eslesir, kesif acik)
# 19: kidsnjoy ?sayfa= dongusu + Trendyol magazalarina taze baglam
# Yenilikler (surum 17'ye gore):
#   - sipnjoylife kesfi EMEKLI: site kidsnjoystore.com'a tasindi (Ticimax).
#     Yeni kidsnjoy_iscisi: 3 kategori sayfasi tarayiciyla acilir,
#     .productItem kartlarindan ad/link/fiyat okur; StokYok urunler atlanir.
#     Her desen artik ayri urun sayfasi (?Desen= modeli bitti).
#   - Liste (etiket) fiyati kaydi: ustu cizili / compare_at / sellingPrice
#     degerleri kategori1 sutununa yazilir; site "-%X etiket" rozeti basar.
#   - Trendyol magaza sayfalari 0 kart donerse 1 kez yeniden denenir
#     (bos kabuk ruleti sigortasi - Mareas icin kritik).

import csv
import html as html_mod
import json
import random
import re
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor

import requests

BASLIKLAR = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "tr-TR,tr;q=0.9",
}
TURKIYE_SAATI = timezone(timedelta(hours=3))
SUTUNLAR = ["tarih", "marka", "seri_adi", "varyant", "kategori1", "hacim",
            "kategori2", "platform", "fiyat", "durum", "url", "satici"]
# kategori1 sutunu = satici etiket/liste fiyati (indirim oncesi), bos olabilir

ANA_DOSYA = "fiyatlar.csv"
YETISKIN_DOSYA = "yetiskin_fiyatlar.csv"

ANA_SATICILAR = {"popcorner", "sipnjoy", "mareas"}
TABAN_FIYAT = 500   # bu tutarin alti hatali sayilir

# ---- SINIFLANDIRMA AYARLARI ----
# Kural sirasi: HARIC -> SERI (bilinen cocuk serisi her zaman 'ana') ->
# YETISKIN kelimeleri -> DAHIL kelimeleri. Hacim KULLANILMAZ.
DAHIL_KELIMELER = ["matara", "termos", "suluk", "bottle", "şişe", "sise"]
HARIC_KELIMELER = ["tritan", "yemek", "food", "beslenme", "mama", "alıştırma", "360°", "Pipetli Su Şişesi 300 ml"]
YETISKIN_KELIMELER = ["tumbler", "mug", "kupa", "yetişkin", "yetiskin"]
SERILER = ["FlipSip", "SippyPals", "WideWonder", "SipSquad", "Lil'Straw",
           "Handlehug", "StrawBuddy"]

KESIF = [
    {"marka": "Trixie", "platform": "popcorner", "tip": "shopify",
     "alan": "popcorner.com.tr", "satici": "popcorner", "vendor": "trixie"},
]

# ---- KIDSNJOY (eski sipnjoylife; Ticimax) ----
# Kullanicinin verdigi 3 kategori taranir. sinif_zorla=None ise sinif
# isim/serilerden; "yetiskin" ise kategori zoruyla yetiskin dosyasina.
KIDSNJOY = {
    "marka": "Sipnjoy", "platform": "kidsnjoy", "satici": "sipnjoy",
    "kategoriler": [
        ("https://kidsnjoystore.com/cocuk-su-termosu-20", None),
        ("https://kidsnjoystore.com/tumbler-24", None),
        ("https://kidsnjoystore.com/yetiskin-28", "yetiskin"),
    ],
}

# ---- TRENDYOL MAGAZALARI ----
MAGAZALAR = [
    {"ad": "PopCorner-Trixie", "marka": "Trixie", "satici": "Pop Corner",
     "taban": "https://www.trendyol.com/sr?wb=103069&lc=103714%2C1193&os=1&mid=849084"},
    {"ad": "SipnJoy", "marka": "Sipnjoy", "satici": "SipnJoy",
     "taban": "https://www.trendyol.com/sr?lc=103714%2C1193&os=1&mid=1095234"},
    {"ad": "Mareas-CoolBottles", "marka": "Cool Bottles", "satici": "Mareas",
     "taban": "https://www.trendyol.com/sr?lc=1193&os=1&mid=391392",
     "seriler": ["The Sport Bottle", "The Tumbler", "The Bottle"]},
]


def normalize_satici(ad):
    return (ad or "").lower().replace(" ", "")


def kucuk(metin):
    return (metin or "").lower().replace("i̇", "i")


def hacim_ml(ad):
    m = re.search(r"(\d{3,4})\s*ml", kucuk(ad))
    return int(m.group(1)) if m else 0


def sinifla(ad):
    """'ana' (cocuk), 'yetiskin' veya None (takip edilmez). Isim uzerinden."""
    a = kucuk(ad)
    if any(h in a for h in HARIC_KELIMELER):
        return None
    if any(kucuk(s).replace("'", "") in a.replace("'", "") for s in SERILER):
        return "ana"
    if any(y in a for y in YETISKIN_KELIMELER):
        return "yetiskin"
    return "ana" if any(d in a for d in DAHIL_KELIMELER) else None


def kunye(marka, ad, ekstra_seriler=None):
    a = kucuk(ad)
    h = hacim_ml(ad)
    hacim = f"{h}ml" if h else ""
    if "tumbler" in a:
        tur = "tumbler"
    elif "mug" in a or "kupa" in a:
        tur = "mug"
    elif "termos" in a:
        tur = "termos"
    else:
        tur = "matara"
    seri = None
    for s in (ekstra_seriler or []) + SERILER:
        if kucuk(s).replace("'", "") in a.replace("'", ""):
            seri = s
            break
    if seri is None:
        seri = tur.capitalize()
    return seri, hacim, tur


def haric_listesi():
    try:
        with open("haric.csv", newline="", encoding="utf-8") as f:
            return {(s.get("url") or "").strip() for s in csv.DictReader(f)
                    if (s.get("url") or "").strip()}
    except FileNotFoundError:
        return set()


def yetiskin_listesi():
    """yetiskin.csv: linki yazilan urun her kosulda yetiskin dosyasina
    zorlanir (? sonrasi atilarak onek karsilastirmasi)."""
    try:
        with open("yetiskin.csv", newline="", encoding="utf-8") as f:
            return {(s.get("url") or "").strip().split("?")[0]
                    for s in csv.DictReader(f)
                    if (s.get("url") or "").strip()}
    except FileNotFoundError:
        return set()


def onceki_kesif_urunleri(dosya):
    try:
        with open(dosya, newline="", encoding="utf-8") as f:
            satirlar = list(csv.DictReader(f))
    except FileNotFoundError:
        return {}
    kesif_plat = {k["platform"] for k in KESIF} | {KIDSNJOY["platform"]}
    ilgili = [s for s in satirlar if s.get("platform") in kesif_plat]
    if not ilgili:
        return {}
    son_tur = max(s["tarih"] for s in ilgili)
    sonuc = {}
    for s in ilgili:
        if s["tarih"] == son_tur and s.get("url") and s.get("durum") != "satista_degil":
            sonuc.setdefault(s["url"].strip(), s)
    return sonuc


def kayit_yap(simdi, marka, seri, varyant, hacim, tur, platform, fiyat, durum,
              url, satici, sinif="ana", liste=None):
    return {
        "tarih": simdi, "marka": marka, "seri_adi": seri, "varyant": varyant,
        "kategori1": liste if liste else "", "hacim": hacim, "kategori2": tur,
        "platform": platform,
        "fiyat": fiyat if fiyat is not None else "", "durum": durum,
        "url": url, "satici": satici, "_sinif": sinif,
    }


def gez(dugum):
    if isinstance(dugum, dict):
        yield dugum
        for v in dugum.values():
            yield from gez(v)
    elif isinstance(dugum, list):
        for v in dugum:
            yield from gez(v)


def metin_fiyat_liste(metin):
    """Kart metninden (guncel, liste) cikarir. TL ve ₺ (once/sonra)
    bicimleri desteklenir; taksit ve 'TL ve uzeri' elenir. Taban ustu
    degerlerin en dusugu guncel, belirgin yuksek olani etiket fiyatidir."""
    if not metin:
        return None, None
    temiz = re.sub(r"\d+\s*x\s*[\d.,]+\s*(?:TL|₺)", " ", metin)
    temiz = re.sub(r"\d[\d.,]*\s*(?:TL|₺)\s*(ve|üzeri|uzeri)", " ", temiz)
    hamlar = re.findall(r"(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?)\s*(?:TL|₺)", temiz)
    hamlar += re.findall(r"₺\s*(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?)", temiz)
    adaylar = []
    for h in hamlar:
        try:
            adaylar.append(float(h.replace(".", "").replace(",", ".")))
        except ValueError:
            continue
    adaylar = [a for a in adaylar if a >= TABAN_FIYAT]
    if not adaylar:
        return None, None
    guncel, liste = min(adaylar), max(adaylar)
    return guncel, (liste if liste > guncel * 1.01 else None)


# ---------------- KESIF: SHOPIFY (popcorner) ----------------

def shopify_kesif(k, simdi, haric, gorulenler):
    sonuclar = []
    try:
        for sayfa_no in range(1, 17):
            url = f"https://{k['alan']}/products.json?limit=250&page={sayfa_no}"
            c = requests.get(url, headers=BASLIKLAR, timeout=20)
            if c.status_code != 200:
                break
            urunler = c.json().get("products", [])
            if not urunler:
                break
            for u in urunler:
                baslik = u.get("title", "")
                vendor = kucuk(u.get("vendor", ""))
                if k.get("vendor") and k["vendor"] not in vendor:
                    continue
                sinif = sinifla(baslik)
                if sinif is None:
                    continue
                seri, hacim, tur = kunye(k["marka"], baslik)
                for v in u.get("variants", []):
                    if not v.get("price"):
                        continue
                    vt = (v.get("title") or "").strip()
                    etiket = baslik if vt.lower() in ("", "default title") else f"{baslik} {vt}"
                    vurl = f"https://{k['alan']}/products/{u['handle']}"
                    if vt and vt.lower() != "default title" and v.get("id"):
                        vurl += f"?variant={v['id']}"
                    if vurl in haric or vurl in gorulenler:
                        continue
                    fiyat = float(v["price"])
                    if fiyat < TABAN_FIYAT:
                        continue
                    liste = None
                    cap = v.get("compare_at_price")
                    try:
                        if cap and float(cap) > fiyat:
                            liste = float(cap)
                    except (TypeError, ValueError):
                        pass
                    gorulenler.add(vurl)
                    sonuclar.append(kayit_yap(simdi, k["marka"], seri, etiket,
                                              hacim, tur, k["platform"], fiyat,
                                              "ok", vurl, k["satici"],
                                              sinif=sinif, liste=liste))
            time.sleep(2)
    except (requests.RequestException, ValueError) as h:
        print(f"[kesif:{k['platform']}] HATA: {h}")
    print(f"[kesif:{k['platform']}] {len(sonuclar)} kayit kesfedildi")
    return sonuclar


# ---------------- KESIF: TICIMAX (kidsnjoystore) ----------------

def kidsnjoy_iscisi(simdi, haric, gorulenler):
    """kidsnjoystore.com (Ticimax): verilen 3 kategori sayfasi tarayiciyla
    acilir, tembel yukleme icin kart sayisi sabitlenene dek kaydirilir,
    .productItem kartlarindan ad/link/fiyat okunur. StokYok atlanir.
    Yetiskin kategorisindeki her urun kategori zoruyla yetiskine gider."""
    from playwright.sync_api import sync_playwright
    sonuclar = []
    try:
        with sync_playwright() as p:
            tarayici = p.chromium.launch()
            baglam = tarayici.new_context(locale="tr-TR",
                                          user_agent=BASLIKLAR["User-Agent"])
            sayfa = baglam.new_page()
            for kurl, sinif_zorla in KIDSNJOY["kategoriler"]:
                kat_gorulen = set()
                kat_kayit = kat_stoksuz = 0
                for sno in range(1, 8):
                    surl = kurl if sno == 1 else f"{kurl}?sayfa={sno}"
                    ham = []
                    try:
                        sayfa.goto(surl, timeout=60000,
                                   wait_until="domcontentloaded")
                        sayfa.wait_for_timeout(4000)
                        onceki = -1
                        for _ in range(4):
                            sayfa.evaluate(
                                "window.scrollTo(0, document.body.scrollHeight)")
                            sayfa.wait_for_timeout(1500)
                            adet = sayfa.eval_on_selector_all(
                                ".productItem", "els => els.length")
                            if adet == onceki:
                                break
                            onceki = adet
                        ham = sayfa.eval_on_selector_all(
                            ".productItem",
                            """els => els.map(e => {
                                const a = e.querySelector('a.detailUrl[title]')
                                       || e.querySelector('a[title][href]');
                                return {stokYok: (e.className || '').includes('StokYok'),
                                        baslik: a ? (a.getAttribute('title') || '') : '',
                                        href: a ? a.href : '',
                                        metin: (e.innerText || '').slice(0, 300)};
                            })""")
                    except Exception as h:
                        print(f"[kesif:kidsnjoy] {surl}: HATA {h}")
                        break
                    yeni_gorulen = 0
                    for kk in ham:
                        if not kk["href"]:
                            continue
                        url = kk["href"].split("?")[0]
                        if url in kat_gorulen:
                            continue          # onceki sayfanin tekrari
                        kat_gorulen.add(url)
                        yeni_gorulen += 1
                        if kk["stokYok"]:
                            kat_stoksuz += 1
                            continue
                        if url in haric or url in gorulenler:
                            continue
                        ad = (kk["baslik"] or kk["metin"].split("\n")[0]).strip()
                        sinif = sinif_zorla or sinifla(ad)
                        if sinif is None:
                            continue
                        guncel, liste = metin_fiyat_liste(kk["metin"])
                        if guncel is None:
                            continue
                        gorulenler.add(url)
                        seri, hacim, tur = kunye(KIDSNJOY["marka"], ad)
                        sonuclar.append(kayit_yap(simdi, KIDSNJOY["marka"],
                                                  seri, ad, hacim, tur,
                                                  KIDSNJOY["platform"], guncel,
                                                  "ok", url,
                                                  KIDSNJOY["satici"],
                                                  sinif=sinif, liste=liste))
                        kat_kayit += 1
                    print(f"[kesif:kidsnjoy] {kurl.rsplit('/', 1)[-1]} "
                          f"sayfa {sno}: {len(ham)} kart, {yeni_gorulen} yeni")
                    if not ham or yeni_gorulen == 0:
                        break
                    time.sleep(random.uniform(1, 2))
                print(f"[kesif:kidsnjoy] {kurl.rsplit('/', 1)[-1]}: "
                      f"toplam {kat_kayit} kayit, {kat_stoksuz} stoksuz")
            tarayici.close()
    except Exception as h:
        print(f"[kesif:kidsnjoy] HATA: {h}")
    print(f"[kesif:kidsnjoy] toplam {len(sonuclar)} kayit kesfedildi")
    return sonuclar


# ---------------- TRENDYOL ----------------

def kart_bilgileri(icerik):
    """Magaza sayfasindan {urun_no: (fiyat, ad, url, liste)} cikarir.
    liste = ustu cizili (indirim oncesi) fiyat, yoksa None."""
    sonuc = {}
    parcalar = re.split(r'<a id="(\d+)" class="product-card"', icerik)
    for i in range(1, len(parcalar) - 1, 2):
        no, govde = parcalar[i], parcalar[i + 1]
        m = re.search(r'href="(/[^"]+-p-' + no + r'[^"]*)"', govde)
        url = ("https://www.trendyol.com" + m.group(1).split("?")[0]) if m else ""
        m = re.search(r'data-testid="image-img"[^>]*alt="([^"]+)"', govde)
        ad = html_mod.unescape(m.group(1)).strip() if m else ""
        if not ad:
            m = re.search(r'class="product-name[^"]*"[^>]*>([^<]{3,120})<', govde)
            ad = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
        guncel, eskiler = None, []
        for m in re.finditer(r'class="([^"]*price[^"]*)"[^>]*>\s*([\d.,]+)\s*TL', govde):
            sinif_adi, ham = m.group(1), m.group(2)
            deger = float(ham.replace(".", "").replace(",", "."))
            if "strikethrough" in sinif_adi or "old" in sinif_adi:
                eskiler.append(deger)
                continue
            if "price-section" in sinif_adi:
                guncel = deger
                break
            if guncel is None:
                guncel = deger
        liste = max(eskiler) if eskiler else None
        if liste is not None and guncel is not None and liste <= guncel:
            liste = None
        if guncel is not None:
            sonuc[no] = (guncel, ad, url, liste)
    return sonuc


def cv_fiyat(p):
    if not isinstance(p, dict):
        return None
    for anahtar in ("discounted", "sellingPrice", "current", "value", "price"):
        v = p.get(anahtar)
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
        if isinstance(v, dict) and isinstance(v.get("value"), (int, float)):
            return float(v["value"])
    for anahtar, v in p.items():
        if anahtar.lower().startswith("old"):
            continue
        if isinstance(v, str):
            m = re.search(r"([\d.]+(?:,\d+)?)\s*TL", v)
            if m:
                return float(m.group(1).replace(".", "").replace(",", "."))
    adaylar = [float(v) for kk, v in p.items()
               if isinstance(v, (int, float)) and v > 0
               and not kk.lower().startswith("old")]
    return min(adaylar) if adaylar else None


def trendyol_winner_fiyat(icerik):
    """(fiyat, liste) doner: indirim varsa liste = sellingPrice."""
    mD = re.search(
        r'"winnerVariant".{0,3000}?"discountedPrice"\s*:\s*\{\s*"value"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
        icerik, re.S)
    mS = re.search(
        r'"winnerVariant".{0,3000}?"sellingPrice"\s*:\s*\{\s*"value"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
        icerik, re.S)
    d = float(mD.group(1)) if mD else None
    s = float(mS.group(1)) if mS else None
    if d is not None and s is not None and s > d:
        return d, s
    return (d if d is not None else s), None


def trendyol_ldjson_fiyat(icerik):
    for blok in re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', icerik, re.S
    ):
        try:
            veri = json.loads(blok.strip())
        except json.JSONDecodeError:
            continue
        for aday in gez(veri):
            offers = aday.get("offers")
            for o in (offers if isinstance(offers, list) else [offers]):
                if isinstance(o, dict) and (o.get("price") or o.get("lowPrice")):
                    try:
                        return float(str(o.get("price") or o.get("lowPrice"))
                                     .replace(",", "."))
                    except ValueError:
                        continue
    return None


def trendyol_dom_fiyat(sayfa):
    adaylar = []
    for secici in ("div[class*='price']", "span[class*='prc']",
                   "[data-testid*='price']"):
        try:
            for el in sayfa.locator(secici).all()[:8]:
                try:
                    metin = el.inner_text(timeout=1500)
                except Exception:
                    continue
                metin = re.sub(r"\d+\s*x\s*[\d.,]+\s*TL", " ", metin)
                metin = re.sub(r"\d[\d.,]*\s*TL\s*(ve|üzeri|uzeri)", " ", metin)
                for m in re.findall(r"(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*TL", metin):
                    adaylar.append(float(m.replace(".", "").replace(",", ".")))
        except Exception:
            continue
        if adaylar:
            break
    return min(adaylar) if adaylar else None


def dom_satici_bul(icerik):
    yer = icerik.find("tarafından gönderilecektir")
    if yer < 0:
        return ""
    parca = icerik[max(0, yer - 800):yer]
    parca = re.sub(r"<[^>]+>", " ", parca)
    parca = parca.replace("&nbsp;", " ").replace("\xa0", " ")
    parca = re.sub(r"\s+", " ", parca).strip()
    m = re.search(r"Bu ürün\s+(.+?)\s*$", parca)
    if m:
        return m.group(1).strip()
    m = re.search(r"([A-Za-zÇĞİÖŞÜçğıöşü0-9][\w &'.\-ÇĞİÖŞÜçğıöşü]{1,50})\s*$", parca)
    return m.group(1).strip() if m else ""


def urun_no(url):
    m = re.search(r"-p-(\d+)", url)
    return m.group(1) if m else None


def model_adi(url):
    yol = urlparse(url.strip()).path.split("/")[-1]
    return re.sub(r"-p-\d+$", "", yol).replace("-", " ")


def eski_kayit(u, simdi, fiyat, durum, varyant=None, satici="", liste=None):
    return {
        "tarih": simdi, "marka": u["marka"], "seri_adi": u["seri_adi"],
        "varyant": varyant if varyant is not None else "",
        "kategori1": liste if liste else "", "hacim": u["hacim"],
        "kategori2": u.get("kategori2", ""), "platform": u["platform"],
        "fiyat": fiyat if fiyat is not None else "", "durum": durum,
        "url": u["url"].strip(), "satici": satici, "_sinif": "ana",
    }


def trendyol_iscisi(urunler, simdi):
    from playwright.sync_api import sync_playwright
    sonuclar = []
    haric_kume = haric_listesi()

    no_map = {}
    for u in urunler:
        n = urun_no(u["url"])
        if n:
            no_map[n] = u
    islenen = set()

    def isle(n, fiyat, satici, varyant_adi=None, liste=None):
        if (n in no_map and n not in islenen and fiyat is not None
                and fiyat >= TABAN_FIYAT):
            u = no_map[n]
            sonuclar.append(eski_kayit(u, simdi, fiyat, "ok",
                                       varyant=varyant_adi or model_adi(u["url"]),
                                       satici=satici, liste=liste))
            islenen.add(n)
            return 1
        return 0

    with sync_playwright() as p:
        tarayici = p.chromium.launch()
        baglam = tarayici.new_context(locale="tr-TR", user_agent=BASLIKLAR["User-Agent"])
        baglam.add_cookies([
            {"name": "countryCode", "value": "TR", "domain": ".trendyol.com", "path": "/"},
            {"name": "language", "value": "tr", "domain": ".trendyol.com", "path": "/"},
            {"name": "storefrontId", "value": "1", "domain": ".trendyol.com", "path": "/"},
        ])

        for mag in MAGAZALAR:
            # her magaza taze tarayici baglamiyla acilir (oturum isaretlenmesine karsi)
            mag_baglam = tarayici.new_context(locale="tr-TR",
                                              user_agent=BASLIKLAR["User-Agent"])
            mag_baglam.add_cookies([
                {"name": "countryCode", "value": "TR", "domain": ".trendyol.com", "path": "/"},
                {"name": "language", "value": "tr", "domain": ".trendyol.com", "path": "/"},
                {"name": "storefrontId", "value": "1", "domain": ".trendyol.com", "path": "/"},
            ])
            for pi in range(1, 16):
                ayrac = "&" if "?" in mag["taban"] else "?"
                url = f"{mag['taban']}{ayrac}pi={pi}"
                cv_cevaplar = []
                sayfa = mag_baglam.new_page()

                def topla(yanit):
                    try:
                        if "color-variants" in yanit.url:
                            cv_cevaplar.append(yanit.text())
                    except Exception:
                        pass
                sayfa.on("response", topla)

                kartlar = {}
                for deneme in (1, 2):   # bos kabuk ruleti sigortasi
                    try:
                        sayfa.goto(url, timeout=60000, wait_until="domcontentloaded")
                        try:
                            sayfa.wait_for_selector("a.product-card", timeout=15000)
                        except Exception:
                            pass
                        sayfa.wait_for_timeout(1500)
                        sayfa.evaluate("window.scrollTo(0, 3000)")
                        sayfa.wait_for_timeout(2500)
                        kartlar = kart_bilgileri(sayfa.content())
                    except Exception as h:
                        print(f"    HATA: {h}")
                    if kartlar:
                        break
                    if deneme == 1:
                        sayfa.wait_for_timeout(3000)
                sayfa.close()

                yeni = 0
                for n, (f, ad, curl, lst) in kartlar.items():
                    if n in no_map:
                        yeni += isle(n, f, mag["satici"], liste=lst)
                        continue
                    ad_g = ad or model_adi(curl)
                    sinif = sinifla(ad_g)
                    if (f is not None and f >= TABAN_FIYAT and curl
                            and curl not in haric_kume and n not in islenen
                            and sinif is not None):
                        seri, hacim, tur = kunye(mag.get("marka", ""), ad_g,
                                                 mag.get("seriler"))
                        sonuclar.append(kayit_yap(simdi, mag.get("marka", ""),
                                                  seri, ad_g, hacim, tur,
                                                  "Trendyol", f, "ok", curl,
                                                  mag["satici"], sinif=sinif,
                                                  liste=lst))
                        islenen.add(n)
                        yeni += 1
                    elif n not in islenen:
                        print(f"    [atlandi] p-{n} fiyat={f} sinif={sinif} "
                              f"ad={ad_g[:45]}")
                for govde_cv in cv_cevaplar:
                    try:
                        veri = json.loads(govde_cv)
                    except json.JSONDecodeError:
                        continue
                    for liste_cv in veri.values():
                        if not isinstance(liste_cv, list):
                            continue
                        for it in liste_cv:
                            if isinstance(it, dict):
                                yeni += isle(str(it.get("id") or ""),
                                             cv_fiyat(it.get("price")),
                                             mag["satici"],
                                             varyant_adi=it.get("name"))
                print(f"[magaza:{mag['ad']}] sayfa {pi}: {len(kartlar)} kart, "
                      f"{len(cv_cevaplar)} varyant cevabi, {yeni} yeni eslesme "
                      f"(toplam {len(islenen)}/{len(no_map)})")
                if not kartlar:
                    break
                time.sleep(random.uniform(2, 3))
            mag_baglam.close()

        kalanlar = [no_map[n] for n in no_map if n not in islenen]
        if kalanlar:
            print(f"[trendyol] magazada bulunamayan {len(kalanlar)} urun, "
                  f"detaydan okunuyor...")
        for u in kalanlar:
            sayfa = baglam.new_page()
            model = model_adi(u["url"])
            try:
                sayfa.goto(u["url"].strip(), timeout=60000, wait_until="domcontentloaded")
                sayfa.wait_for_timeout(5000)
                if "select-country" in sayfa.url:
                    sonuclar.append(eski_kayit(u, simdi, None, "ulke_kapisi",
                                               varyant=model))
                    print(f"[trendyol-detay] {model[:40]}: ulke_kapisi")
                    sayfa.close()
                    time.sleep(random.uniform(2, 4))
                    continue
                no = urun_no(u["url"])
                if no and no not in sayfa.url:
                    sonuclar.append(eski_kayit(u, simdi, None, "urun_bulunamadi",
                                               varyant=model))
                    print(f"[trendyol-detay] {model[:40]}: urun_bulunamadi "
                          f"(baska sayfaya yonlendirildi)")
                    sayfa.close()
                    time.sleep(random.uniform(2, 4))
                    continue
                icerik = sayfa.content()
                fiyat, liste = trendyol_winner_fiyat(icerik)
                kaynak = "winner"
                if fiyat is None:
                    fiyat = trendyol_ldjson_fiyat(icerik)
                    kaynak = "ldjson"
                if fiyat is None:
                    fiyat = trendyol_dom_fiyat(sayfa)
                    kaynak = "dom"
                if fiyat is not None and fiyat < TABAN_FIYAT:
                    print(f"[trendyol-detay] {model[:40]}: supheli fiyat "
                          f"{fiyat} elendi")
                    fiyat = None
                satici = dom_satici_bul(icerik)
                if fiyat is not None:
                    sonuclar.append(eski_kayit(u, simdi, fiyat, "ok",
                                               varyant=model, satici=satici,
                                               liste=liste))
                else:
                    sonuclar.append(eski_kayit(u, simdi, None, "fiyat_bulunamadi",
                                               varyant=model))
                print(f"[trendyol-detay] {model[:40]}: {fiyat} "
                      f"[{kaynak}, satici={satici or '-'}]")
            except Exception:
                sonuclar.append(eski_kayit(u, simdi, None, "baglanti_hatasi",
                                           varyant=model))
                print(f"[trendyol-detay] {model[:40]}: baglanti_hatasi")
            sayfa.close()
            time.sleep(random.uniform(2, 4))

        tarayici.close()
    return sonuclar


# ---------------- ARSIVLEME + DOSYAYA YAZMA ----------------

def arsivle(dosya):
    """Ay degistiginde onceki ay(lar)in kayitlarini arsiv/ altina tasir."""
    import os
    ay = datetime.now(TURKIYE_SAATI).strftime("%Y-%m")
    try:
        with open(dosya, newline="", encoding="utf-8") as f:
            satirlar = list(csv.DictReader(f))
    except FileNotFoundError:
        return
    eskiler = [s for s in satirlar if (s.get("tarih") or "")[:7] < ay]
    if not eskiler:
        return
    os.makedirs("arsiv", exist_ok=True)
    gruplu = {}
    for s in eskiler:
        gruplu.setdefault(s["tarih"][:7], []).append(s)
    for ayk, liste in gruplu.items():
        hedef = f"arsiv/{dosya.rsplit('.', 1)[0]}-{ayk}.csv"
        try:
            with open(hedef, "r", encoding="utf-8") as f:
                bos = f.readline().strip() == ""
        except FileNotFoundError:
            bos = True
        with open(hedef, "a", newline="", encoding="utf-8") as f:
            y = csv.DictWriter(f, fieldnames=SUTUNLAR)
            if bos:
                y.writeheader()
            y.writerows(liste)
    kalanlar = [s for s in satirlar if (s.get("tarih") or "")[:7] >= ay]
    with open(dosya, "w", newline="", encoding="utf-8") as f:
        y = csv.DictWriter(f, fieldnames=SUTUNLAR)
        y.writeheader()
        y.writerows(kalanlar)
    print(f"[arsiv] {dosya}: {len(eskiler)} kayit arsive tasindi")


def dosyaya_ekle(dosya, kayitlar):
    if not kayitlar:
        return
    try:
        with open(dosya, "r", encoding="utf-8") as f:
            bos = f.readline().strip() == ""
    except FileNotFoundError:
        bos = True
    with open(dosya, "a", newline="", encoding="utf-8") as f:
        y = csv.DictWriter(f, fieldnames=SUTUNLAR)
        if bos:
            y.writeheader()
        y.writerows(kayitlar)


def main():
    simdi = datetime.now(TURKIYE_SAATI).strftime("%Y-%m-%d %H:%M")
    arsivle(ANA_DOSYA)
    arsivle(YETISKIN_DOSYA)
    haric = haric_listesi()
    onceki_ana = onceki_kesif_urunleri(ANA_DOSYA)
    onceki_yet = onceki_kesif_urunleri(YETISKIN_DOSYA)
    print(f"Kesif: haric listesi {len(haric)} url, onceki tur "
          f"{len(onceki_ana)} ana + {len(onceki_yet)} yetiskin urun")

    with open("urunler.csv", newline="", encoding="utf-8") as f:
        tum_satirlar = [u for u in csv.DictReader(f) if (u.get("url") or "").strip()]
    trendyol_urunleri = [u for u in tum_satirlar if "trendyol" in u["url"].lower()]

    gorulenler = set()
    tum = []

    with ThreadPoolExecutor(max_workers=3) as havuz:
        isler = []
        for k in KESIF:
            if k["tip"] == "shopify":
                isler.append(havuz.submit(shopify_kesif, k, simdi, haric, gorulenler))
        isler.append(havuz.submit(kidsnjoy_iscisi, simdi, haric, gorulenler))
        isler.append(havuz.submit(trendyol_iscisi, trendyol_urunleri, simdi))
        for is_ in isler:
            tum.extend(is_.result())

    # kayit siniflarina gore ayir (yetiskin.csv istisnalari uygulanir)
    yetiskin_zorla = yetiskin_listesi()
    ana_kayitlar, yetiskin_kayitlar = [], []
    for kayit in tum:
        sinif = kayit.pop("_sinif", "ana")
        u = (kayit.get("url") or "").split("?")[0]
        if any(u.startswith(p) for p in yetiskin_zorla):
            sinif = "yetiskin"
        (yetiskin_kayitlar if sinif == "yetiskin" else ana_kayitlar).append(kayit)

    # bu turda gorunmeyenler -> satista_degil (bir kez yazilir)
    for oncekiler, hedef in ((onceki_ana, ana_kayitlar),
                             (onceki_yet, yetiskin_kayitlar)):
        kayip = 0
        for url, eski in oncekiler.items():
            if url not in gorulenler and url not in haric:
                hedef.append({
                    "tarih": simdi, "marka": eski["marka"],
                    "seri_adi": eski["seri_adi"], "varyant": eski["varyant"],
                    "kategori1": "", "hacim": eski["hacim"],
                    "kategori2": eski.get("kategori2", ""),
                    "platform": eski["platform"], "fiyat": "",
                    "durum": "satista_degil", "url": url,
                    "satici": eski.get("satici", ""),
                })
                kayip += 1
        if kayip:
            print(f"[kesif] {kayip} urun bu turda gorunmedi -> satista_degil")

    dosyaya_ekle(ANA_DOSYA, ana_kayitlar)
    dosyaya_ekle(YETISKIN_DOSYA, yetiskin_kayitlar)
    print(f"\nBitti: {len(ana_kayitlar)} ana + {len(yetiskin_kayitlar)} "
          f"yetiskin kayit eklendi.")


if __name__ == "__main__":
    main()
