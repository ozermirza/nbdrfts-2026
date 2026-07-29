# -*- coding: utf-8 -*-
# FIYAT RADARI - scraper.py (surum 9)
# Yeni: Trendyol'da uc kanalli okuma:
#   1) API dinleyici (sayfanin kendi arka plan isteginden satici+fiyat)
#   2) envoy deposu (yan paneldeki "diger saticilar")
#   3) DOM fiyat kutusu (buy-box yedegi)
# Boylece one cikan satici + diger saticilar birlikte yakalanir.

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
            "kategori2", "platform", "fiyat", "durum", "url", "satici"]

# Markalarin resmi/ana saticilari (kucuk harf, bosluksuz).
ANA_SATICILAR = {"popcorner", "sipnjoy"}


def normalize_satici(ad):
    return (ad or "").lower().replace(" ", "")


def slugla(metin):
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
    temiz = re.sub(r"\d+\s*x\s*[\d.,]+\s*TL", " ", html)
    m = re.search(r"(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*TL", temiz)
    if m:
        return float(m.group(1).replace(".", "").replace(",", "."))
    return None


def kayit(urun, simdi, fiyat, durum, varyant=None, url=None, satici=""):
    return {
        "tarih": simdi, "marka": urun["marka"], "seri_adi": urun["seri_adi"],
        "varyant": varyant if varyant is not None else varyant_bul(urun["url"]),
        "kategori1": urun["kategori1"], "hacim": urun["hacim"],
        "kategori2": urun["kategori2"], "platform": urun["platform"],
        "fiyat": fiyat if fiyat is not None else "", "durum": durum,
        "url": url or urun["url"].strip(), "satici": satici,
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


def gez(dugum):
    if isinstance(dugum, dict):
        yield dugum
        for v in dugum.values():
            yield from gez(v)
    elif isinstance(dugum, list):
        for v in dugum:
            yield from gez(v)


# ---------------- SIPNJOYLIFE ----------------

def nextdata_katalog(url):
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
    katalog = nextdata_katalog(urunler[0]["url"].strip())
    sonuclar = []
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
            adres = urlparse(u["url"].strip())
            parametre = "Renk" if "Renk" in parse_qs(adres.query) else "Desen"
            taban = f"https://{adres.netloc}{yol}"
            for varyant_adi, fiyat in katalog[eslesme]:
                vurl = taban
                if varyant_adi:
                    vurl += f"?{parametre}={varyant_adi.replace(' ', '-')}"
                sonuclar.append(kayit(u, simdi, fiyat, "ok",
                                      varyant=varyant_adi, url=vurl, satici="sipnjoy"))
            print(f"[nextdata] {u['seri_adi']}: {len(katalog[eslesme])} varyant")
        else:
            f, durum = tek_tek_cek(u)
            if durum == "ok":
                durum = "model_fiyati"
            sonuclar.append(kayit(u, simdi, f, durum, varyant="", satici="sipnjoy"))
            print(f"[nextdata] {u['seri_adi']}: eslesme yok, {durum}")
            time.sleep(random.uniform(2, 4))
    return sonuclar


# ---------------- TRENDYOL ----------------

def _fiyat_alanindan(d):
    """Bir sozlukten guncel fiyati ceker: once discountedPrice, sonra sellingPrice."""
    kaynaklar = [d.get("price")] if isinstance(d.get("price"), dict) else []
    kaynaklar.append(d)
    for p in kaynaklar:
        if not isinstance(p, dict):
            continue
        for alan in ("discountedPrice", "sellingPrice"):
            v = p.get(alan)
            if isinstance(v, dict) and isinstance(v.get("value"), (int, float)):
                return float(v["value"])
            if isinstance(v, (int, float)):
                return float(v)
    return None


def satici_listesi_cikar(veri):
    """Herhangi bir JSON agacindan [(satici, fiyat), ...] cikarir.
    Ilk eleman, bulunabildiyse one cikan (buy-box) saticidir."""
    kazanan = None
    for d in gez(veri):
        if isinstance(d.get("otherMerchants"), list) and "merchant" in d:
            kazanan = d
            break
    if kazanan is None:
        for d in gez(veri):
            if isinstance(d.get("merchant"), dict) and _fiyat_alanindan(d) is not None:
                kazanan = d
                kazanan.setdefault("otherMerchants", [])
                break
    if kazanan is None:
        return None
    liste = []
    ad = (kazanan.get("merchant") or {}).get("name") or ""
    f = _fiyat_alanindan(kazanan)
    if f is not None:
        liste.append((ad, f))
    for o in kazanan.get("otherMerchants", []):
        if not isinstance(o, dict):
            continue
        oad = (o.get("merchant") or {}).get("name") or ""
        of = _fiyat_alanindan(o)
        if of is not None:
            liste.append((oad, of))
    return liste or None


def envoy_depo_listesi(sayfa):
    """Sayfadaki PROPS/STATE depolarindan satici listesi cikarir (yan panel)."""
    try:
        ham = sayfa.evaluate("""() => {
            const out = {};
            for (const k of Object.getOwnPropertyNames(window)) {
                if (k.endsWith('PROPS') || k.includes('STATE') || k.includes('INITIAL')) {
                    try { JSON.stringify(window[k]); out[k] = window[k]; } catch (e) {}
                }
            }
            return JSON.stringify(out);
        }""")
        if not ham or ham == "{}":
            return None
        depolar = json.loads(ham)
    except Exception:
        return None
    for depo in depolar.values():
        liste = satici_listesi_cikar(depo)
        if liste:
            return liste
    return None


def trendyol_dom_fiyat(sayfa):
    """Buy-box yedegi: fiyat kutusundaki TL degerlerinin en kucugu."""
    for secici in ("div[class*='price']", "span.prc-dsc", "[data-testid*='price']"):
        try:
            el = sayfa.locator(secici).first
            if el.count() == 0:
                continue
            metin = re.sub(r"\d+\s*x\s*[\d.,]+\s*TL", " ", el.inner_text(timeout=2000))
            adaylar = [float(m.replace(".", "").replace(",", "."))
                       for m in re.findall(r"(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*TL", metin)]
            if adaylar:
                return min(adaylar)
        except Exception:
            continue
    return None


def dom_satici_bul(sayfa):
    """Buy-box saticisini sayfadaki 'Bu urun X tarafindan gonderilecektir'
    cumlesinden okur."""
    try:
        html = sayfa.content()
    except Exception:
        return ""
    yer = html.find("tarafından gönderilecektir")
    if yer > 0:
        parca = re.sub(r"<[^>]+>", " ", html[max(0, yer - 300):yer])
        parca = re.sub(r"\s+", " ", parca).strip()
        m = re.search(r"Bu ürün\s+(.+?)$", parca)
        if m:
            return m.group(1).strip()
    return ""


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
            sayfa = baglam.new_page()
            yol = urlparse(u["url"].strip()).path.split("/")[-1]
            model = re.sub(r"-p-\d+$", "", yol).replace("-", " ")
            try:
                sayfa.goto(u["url"].strip(), timeout=60000, wait_until="domcontentloaded")
                sayfa.wait_for_timeout(5000)
                if "select-country" in sayfa.url:
                    sonuclar.append(kayit(u, simdi, None, "ulke_kapisi", varyant=model))
                    print(f"[trendyol] {model[:40]}: ulke_kapisi")
                    sayfa.close()
                    time.sleep(random.uniform(2, 4))
                    continue

                # 1) Buy-box: DOM fiyati + sayfadaki satici cumlesi
                #    (bulamazsa bir kez daha bekleyip dener)
                dom_fiyat = trendyol_dom_fiyat(sayfa)
                dom_satici = dom_satici_bul(sayfa)
                if dom_fiyat is None:
                    sayfa.wait_for_timeout(5000)
                    dom_fiyat = trendyol_dom_fiyat(sayfa)
                    dom_satici = dom_satici or dom_satici_bul(sayfa)

                # 2) Yan panel: envoy deposundan diger saticilar
                envoy = envoy_depo_listesi(sayfa) or []

                # 3) Kayitlari kur
                digerler = [f for a, f in envoy
                            if normalize_satici(a) not in ANA_SATICILAR]
                ana = None
                if dom_fiyat is not None:
                    if dom_satici and normalize_satici(dom_satici) not in ANA_SATICILAR:
                        digerler.append(dom_fiyat)  # buy-box baska saticida
                    else:
                        ana = (dom_satici, dom_fiyat)
                else:
                    envoy_ana = [(a, f) for a, f in envoy
                                 if normalize_satici(a) in ANA_SATICILAR]
                    if envoy_ana:
                        ana = envoy_ana[0]

                if ana is not None:
                    sonuclar.append(kayit(u, simdi, ana[1], "ok",
                                          varyant=model, satici=ana[0]))
                if digerler:
                    sonuclar.append(kayit(u, simdi, min(digerler), "ok",
                                          varyant=model, satici="diger satici"))
                if ana is None and not digerler:
                    sonuclar.append(kayit(u, simdi, None, "fiyat_bulunamadi",
                                          varyant=model))
                print(f"[trendyol] {model[:40]}: ana={ana if ana else '-'} "
                      f"diger_min={min(digerler) if digerler else '-'} "
                      f"[satici_dom={dom_satici or '-'}]")
            except Exception:
                sonuclar.append(kayit(u, simdi, None, "baglanti_hatasi", varyant=model))
                print(f"[trendyol] {model[:40]}: baglanti_hatasi")
            sayfa.close()
            time.sleep(random.uniform(2, 4))
        tarayici.close()
    return sonuclar

# ---------------- SHOPIFY (popcorner) ve genel ----------------

def shopify_dokum_al(alan_adi):
    dokum = {}
    try:
        for sayfa_no in range(1, 9):
            url = f"https://{alan_adi}/products.json?limit=250&page={sayfa_no}"
            c = requests.get(url, headers=BASLIKLAR, timeout=20)
            if c.status_code != 200:
                return dokum or None
            urunler = c.json().get("products", [])
            if not urunler:
                break
            for u in urunler:
                for v in u.get("variants", []):
                    if not v.get("price"):
                        continue
                    vt = (v.get("title") or "").strip()
                    etiket = u.get("title", "") if vt.lower() in ("", "default title") else vt
                    vurl = f"https://{alan_adi}/products/{u['handle']}"
                    if vt and vt.lower() != "default title" and v.get("id"):
                        vurl += f"?variant={v['id']}"
                    dokum.setdefault(u["handle"], []).append(
                        (etiket, float(v["price"]), vurl))
            time.sleep(2)
    except (requests.RequestException, ValueError):
        return dokum or None
    return dokum or None


def site_iscisi(alan_adi, urunler, simdi):
    if "trendyol" in alan_adi:
        return trendyol_iscisi(urunler, simdi)
    if "sipnjoylife" in alan_adi:
        return nextdata_iscisi(urunler, simdi)

    satici = "popcorner" if "popcorner" in alan_adi else ""
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
                for etiket, fiyat, vurl in dokum[handle]:
                    sonuclar.append(kayit(u, simdi, fiyat, "ok",
                                          varyant=etiket, url=vurl, satici=satici))
                continue
        f, durum = tek_tek_cek(u)
        sonuclar.append(kayit(u, simdi, f, durum, satici=satici))
        print(f"[{alan_adi}] {u['seri_adi']}: {f} [{durum}]")
        time.sleep(random.uniform(3, 6))
    return sonuclar


def satici_sutunu_garantile():
    try:
        with open("fiyatlar.csv", newline="", encoding="utf-8") as f:
            satirlar = list(csv.reader(f))
    except FileNotFoundError:
        return
    if not satirlar or "satici" in satirlar[0]:
        return
    satirlar[0].append("satici")
    for s in satirlar[1:]:
        s.append("")
    with open("fiyatlar.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(satirlar)
    print("fiyatlar.csv'ye satici sutunu eklendi (gecis islemi).")


def main():
    satici_sutunu_garantile()
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
