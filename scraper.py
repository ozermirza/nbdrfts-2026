# -*- coding: utf-8 -*-
# FIYAT RADARI - scraper.py (surum 12)
# YENI: OTOMATIK KESIF (Faz 1) - popcorner ve sipnjoylife icin urunler.csv
# gerekmez; magazanin tamami taranir, uygun urunler kendiliginden takibe girer,
# kaybolanlar 'satista_degil' olarak isaretlenir, haric.csv ile dislama yapilir.
# Trendyol ve Hepsiburada: eskisi gibi urunler.csv uzerinden.

import csv
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

ANA_SATICILAR = {"popcorner", "sipnjoy"}
TABAN_FIYAT = 500   # bu tutarin alti hatali sayilir

# ---- OTOMATIK KESIF AYARLARI ----
# Urun adinda bunlardan biri gecmeli (kucuk harf karsilastirma):
DAHIL_KELIMELER = ["matara", "termos", "suluk", "bottle", "şişe", "sise"]
# Adinda bunlar gecen urunler otomatik elenir:
HARIC_KELIMELER = ["tritan", "mama", "yemek", "food", "besleme", "beslenme"]
# Seri adi tespiti icin bilinen seriler (bulunamazsa Matara/Termos yazilir):
SERILER = ["FlipSip", "SippyPals", "WideWonder", "SipSquad", "Lil'Straw"]

KESIF = [
    {"marka": "Trixie", "platform": "popcorner", "tip": "shopify",
     "alan": "popcorner.com.tr", "satici": "popcorner", "vendor": "trixie"},
    {"marka": "Sipnjoy", "platform": "sipnjoylife", "tip": "nextdata",
     "taban": "https://www.sipnjoylife.com", "satici": "sipnjoy"},
]

# ---- TRENDYOL MAGAZALARI (buy-box hizlandirici) ----
MAGAZALAR = [
    # {"ad": "PopCorner-Trixie", "satici": "Pop Corner",
    #  "taban": "https://www.trendyol.com/sr?lc=103714%2C1193&os=1&mid=849084"},
    {"ad": "SipnJoy", "marka": "Sipnjoy", "satici": "SipnJoy",
     "taban": "https://www.trendyol.com/sr?lc=103714%2C1193&os=1&mid=1095234"},
]


def normalize_satici(ad):
    return (ad or "").lower().replace(" ", "")


def kucuk(metin):
    return (metin or "").lower().replace("i̇", "i")


def uygun_mu(ad):
    """Kesfedilen urun takibe girsin mi? (dahil + haric kelime filtreleri)"""
    a = kucuk(ad)
    if any(h in a for h in HARIC_KELIMELER):
        return False
    if any(d in a for d in DAHIL_KELIMELER):
        return True
    return any(kucuk(s).replace("'", "") in a.replace("'", "") for s in SERILER)


def kunye(marka, ad):
    """Urun adindan seri / hacim / tur cikarir."""
    a = kucuk(ad)
    m = re.search(r"(\d{3,4})\s*ml", a)
    hacim = f"{m.group(1)}ml" if m else ""
    tur = "termos" if "termos" in a else "matara"
    seri = None
    for s in SERILER:
        if kucuk(s).replace("'", "") in a.replace("'", ""):
            seri = s
            break
    if seri is None:
        seri = "Termos" if tur == "termos" else "Matara"
    return seri, hacim, tur


def haric_listesi():
    try:
        with open("haric.csv", newline="", encoding="utf-8") as f:
            return {(s.get("url") or "").strip() for s in csv.DictReader(f)
                    if (s.get("url") or "").strip()}
    except FileNotFoundError:
        return set()


def onceki_kesif_urunleri():
    """fiyatlar.csv'den, kesif platformlarinin son turda fiyatli gorulen
    urunlerini dondurur: {url: eski_kayit}. Kaybolanlari tespit icin."""
    try:
        with open("fiyatlar.csv", newline="", encoding="utf-8") as f:
            satirlar = list(csv.DictReader(f))
    except FileNotFoundError:
        return {}
    kesif_plat = {k["platform"] for k in KESIF}
    ilgili = [s for s in satirlar if s.get("platform") in kesif_plat]
    if not ilgili:
        return {}
    son_tur = max(s["tarih"] for s in ilgili)
    sonuc = {}
    for s in ilgili:
        if s["tarih"] == son_tur and s.get("url"):
            sonuc.setdefault(s["url"].strip(), s)
    return sonuc


def kayit_yap(simdi, marka, seri, varyant, hacim, tur, platform, fiyat, durum,
              url, satici):
    return {
        "tarih": simdi, "marka": marka, "seri_adi": seri, "varyant": varyant,
        "kategori1": "", "hacim": hacim, "kategori2": tur, "platform": platform,
        "fiyat": fiyat if fiyat is not None else "", "durum": durum,
        "url": url, "satici": satici,
    }


def gez(dugum):
    if isinstance(dugum, dict):
        yield dugum
        for v in dugum.values():
            yield from gez(v)
    elif isinstance(dugum, list):
        for v in dugum:
            yield from gez(v)


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
                başlik = u.get("title", "")
                vendor = kucuk(u.get("vendor", ""))
                if k.get("vendor") and k["vendor"] not in vendor:
                    continue
                if not uygun_mu(başlik):
                    continue
                seri, hacim, tur = kunye(k["marka"], başlik)
                for v in u.get("variants", []):
                    if not v.get("price"):
                        continue
                    vt = (v.get("title") or "").strip()
                    etiket = başlik if vt.lower() in ("", "default title") else f"{başlik} {vt}"
                    vurl = f"https://{k['alan']}/products/{u['handle']}"
                    if vt and vt.lower() != "default title" and v.get("id"):
                        vurl += f"?variant={v['id']}"
                    if vurl in haric:
                        continue
                    fiyat = float(v["price"])
                    if fiyat < TABAN_FIYAT:
                        continue
                    gorulenler.add(vurl)
                    sonuclar.append(kayit_yap(simdi, k["marka"], seri, etiket,
                                              hacim, tur, k["platform"], fiyat,
                                              "ok", vurl, k["satici"]))
            time.sleep(2)
    except (requests.RequestException, ValueError) as h:
        print(f"[kesif:{k['platform']}] HATA: {h}")
    print(f"[kesif:{k['platform']}] {len(sonuclar)} kayit kesfedildi")
    return sonuclar


# ---------------- KESIF: NEXT_DATA (sipnjoylife) ----------------

def slug_bul(d):
    """Urun kaydinin derinliklerinde link/slug arar (metaData, translations...)."""
    for kap_adi in ("metaData", "translations", "seo"):
        kap = d.get(kap_adi)
        if kap is None:
            continue
        for ic in gez(kap):
            for alan in ("slug", "seoUrl", "url", "handle", "path"):
                v = ic.get(alan)
                if isinstance(v, str) and v.strip():
                    return v.strip().strip("/").split("/")[-1]
    return None


def slugla(metin):
    harfler = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosucgiosu")
    metin = metin.translate(harfler).lower()
    return re.sub(r"[^a-z0-9]+", "-", metin).strip("-")


def nextdata_kesif(k, simdi, haric, gorulenler):
    sonuclar = []
    try:
        html = requests.get(k["taban"], headers=BASLIKLAR, timeout=30).text
    except requests.RequestException as h:
        print(f"[kesif:{k['platform']}] HATA: {h}")
        return sonuclar
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        print(f"[kesif:{k['platform']}] NEXT_DATA bulunamadi")
        return sonuclar
    try:
        veri = json.loads(m.group(1))
    except json.JSONDecodeError:
        return sonuclar

    for d in gez(veri):
        if not (isinstance(d.get("variants"), list) and d.get("name") and d["variants"]):
            continue
        ad = d["name"]
        if not uygun_mu(ad):
            continue
        seri, hacim, tur = kunye(k["marka"], ad)
        slug = slug_bul(d) or slugla(ad)
        taban_url = f"{k['taban']}/{slug}"
        for v in d["variants"]:
            if not isinstance(v, dict):
                continue
            vad = ""
            vv = v.get("variantValues")
            if isinstance(vv, list) and vv and isinstance(vv[0], dict):
                vad = vv[0].get("name", "") or ""
            fiy = None
            pr = v.get("prices")
            if isinstance(pr, list) and pr and isinstance(pr[0], dict):
                fiy = pr[0].get("discountPrice") or pr[0].get("sellPrice")
            if fiy is None:
                continue
            fiyat = float(fiy)
            if fiyat < TABAN_FIYAT:
                continue
            vurl = taban_url + (f"?Desen={vad.replace(' ', '-')}" if vad else "")
            if vurl in haric:
                continue
            gorulenler.add(vurl)
            sonuclar.append(kayit_yap(simdi, k["marka"], seri,
                                      vad or ad, hacim, tur, k["platform"],
                                      fiyat, "ok", vurl, k["satici"]))
    print(f"[kesif:{k['platform']}] {len(sonuclar)} kayit kesfedildi")
    return sonuclar

# ---------------- TRENDYOL (urunler.csv uzerinden, degisiklik yok) ----------------

def _sayi_cek(d, alanlar):
    for alan in alanlar:
        v = d.get(alan)
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, dict) and isinstance(v.get("value"), (int, float)):
            return float(v["value"])
    return None


def kart_bilgileri(icerik):
    """Magaza sayfasindan {urun_no: (fiyat, ad, url)} cikarir."""
    sonuc = {}
    parcalar = re.split(r'<a id="(\d+)" class="product-card"', icerik)
    for i in range(1, len(parcalar) - 1, 2):
        no, govde = parcalar[i], parcalar[i + 1]
        m = re.search(r'href="(/[^"]+-p-' + no + r'[^"]*)"', govde)
        url = ("https://www.trendyol.com" + m.group(1).split("?")[0]) if m else ""
        m = re.search(r'class="product-name[^"]*"[^>]*>([^<]{3,120})<', govde)
        ad = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
        guncel = None
        for m in re.finditer(r'class="([^"]*price[^"]*)"[^>]*>\s*([\d.,]+)\s*TL', govde):
            sinif, ham = m.group(1), m.group(2)
            if "strikethrough" in sinif or "old" in sinif:
                continue
            deger = float(ham.replace(".", "").replace(",", "."))
            if "price-section" in sinif:
                guncel = deger
                break
            if guncel is None:
                guncel = deger
        if guncel is not None:
            sonuc[no] = (guncel, ad, url)
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
    m = re.search(
        r'"winnerVariant".{0,3000}?"discountedPrice"\s*:\s*\{\s*"value"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
        icerik, re.S)
    if m:
        return float(m.group(1))
    m = re.search(
        r'"winnerVariant".{0,3000}?"sellingPrice"\s*:\s*\{\s*"value"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
        icerik, re.S)
    return float(m.group(1)) if m else None


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


def eski_kayit(u, simdi, fiyat, durum, varyant=None, satici=""):
    return {
        "tarih": simdi, "marka": u["marka"], "seri_adi": u["seri_adi"],
        "varyant": varyant if varyant is not None else "",
        "kategori1": u.get("kategori1", ""), "hacim": u["hacim"],
        "kategori2": u.get("kategori2", ""), "platform": u["platform"],
        "fiyat": fiyat if fiyat is not None else "", "durum": durum,
        "url": u["url"].strip(), "satici": satici,
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

    def isle(n, fiyat, satici, varyant_adi=None):
        if (n in no_map and n not in islenen and fiyat is not None
                and fiyat >= TABAN_FIYAT):
            u = no_map[n]
            sonuclar.append(eski_kayit(u, simdi, fiyat, "ok",
                                       varyant=varyant_adi or model_adi(u["url"]),
                                       satici=satici))
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
            for pi in range(1, 16):
                ayrac = "&" if "?" in mag["taban"] else "?"
                url = f"{mag['taban']}{ayrac}pi={pi}"
                cv_cevaplar = []
                sayfa = baglam.new_page()

                def topla(yanit):
                    try:
                        if "color-variants" in yanit.url:
                            cv_cevaplar.append(yanit.text())
                    except Exception:
                        pass
                sayfa.on("response", topla)

                kartlar = {}
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
                sayfa.close()

                yeni = 0
                for n, (f, ad, curl) in kartlar.items():
                    if n in no_map:
                        yeni += isle(n, f, mag["satici"])
                    elif (f is not None and f >= TABAN_FIYAT and curl
                          and curl not in haric_kume and uygun_mu(ad or "")):
                        seri, hacim, tur = kunye(mag.get("marka", ""), ad)
                        sonuclar.append(kayit_yap(simdi, mag.get("marka", ""),
                                                  seri, ad, hacim, tur,
                                                  "Trendyol", f, "ok", curl,
                                                  mag["satici"]))
                        islenen.add(n)
                        yeni += 1
                for govde in cv_cevaplar:
                    try:
                        veri = json.loads(govde)
                    except json.JSONDecodeError:
                        continue
                    for liste in veri.values():
                        if not isinstance(liste, list):
                            continue
                        for it in liste:
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
                if len(islenen) == len(no_map):
                    break
                time.sleep(random.uniform(2, 3))
            if len(islenen) == len(no_map):
                break

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
                fiyat = trendyol_winner_fiyat(icerik)
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
                                               varyant=model, satici=satici))
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


# ---------------- HEPSIBURADA (degisiklik yok: 403 verir, yerel robot tasir) ----

def hb_iscisi(urunler, simdi):
    sonuclar = []
    for u in urunler:
        try:
            c = requests.get(u["url"].strip(), headers=BASLIKLAR, timeout=20)
            durum = "ok" if c.status_code == 200 else f"http_{c.status_code}"
            f = None
        except requests.RequestException:
            f, durum = None, "baglanti_hatasi"
        sonuclar.append(eski_kayit(u, simdi, None, durum))
        print(f"[www.hepsiburada.com] {u['seri_adi']}: None [{durum}]")
        time.sleep(random.uniform(2, 4))
    return sonuclar


def main():
    simdi = datetime.now(TURKIYE_SAATI).strftime("%Y-%m-%d %H:%M")
    haric = haric_listesi()
    oncekiler = onceki_kesif_urunleri()
    print(f"Kesif: haric listesi {len(haric)} url, onceki tur {len(oncekiler)} urun")

    # urunler.csv sadece Trendyol + Hepsiburada icin okunur
    with open("urunler.csv", newline="", encoding="utf-8") as f:
        tum_satirlar = [u for u in csv.DictReader(f) if (u.get("url") or "").strip()]
    trendyol_urunleri = [u for u in tum_satirlar if "trendyol" in u["url"].lower()]
    hb_urunleri = [u for u in tum_satirlar if "hepsiburada" in u["url"].lower()]

    gorulenler = set()
    tum = []

    with ThreadPoolExecutor(max_workers=4) as havuz:
        isler = []
        for k in KESIF:
            if k["tip"] == "shopify":
                isler.append(havuz.submit(shopify_kesif, k, simdi, haric, gorulenler))
            elif k["tip"] == "nextdata":
                isler.append(havuz.submit(nextdata_kesif, k, simdi, haric, gorulenler))
        isler.append(havuz.submit(trendyol_iscisi, trendyol_urunleri, simdi))
        isler.append(havuz.submit(hb_iscisi, hb_urunleri, simdi))
        for is_ in isler:
            tum.extend(is_.result())

    # Kaybolanlar: onceki turda olup bu kesifte gorunmeyenler
    kayip = 0
    for url, eski in oncekiler.items():
        if url not in gorulenler and url not in haric:
            tum.append({
                "tarih": simdi, "marka": eski["marka"], "seri_adi": eski["seri_adi"],
                "varyant": eski["varyant"], "kategori1": eski.get("kategori1", ""),
                "hacim": eski["hacim"], "kategori2": eski.get("kategori2", ""),
                "platform": eski["platform"], "fiyat": "", "durum": "satista_degil",
                "url": url, "satici": eski.get("satici", ""),
            })
            kayip += 1
    if kayip:
        print(f"[kesif] {kayip} urun bu turda gorunmedi -> satista_degil")

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
