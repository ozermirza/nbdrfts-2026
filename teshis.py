# -*- coding: utf-8 -*-
# TESHIS ARACI - surum 5
# Amac: v7'de fiyat_bulunamadi veren Trendyol urunlerinde gomulu verinin
# yapisini gormek: satici/fiyat alanlari nerede, bizim sokucu neden bulamiyor?

import json
import re

HEDEFLER = [
    "https://www.trendyol.com/trixie/41-222-bottle-500ml-mrs-cat-p-753701975?boutiqueId=61&merchantId=849084",
    "https://www.trendyol.com/trixie/56-210-paslanmaz-celik-termos-matara-350ml-mr-fox-p-851620590?boutiqueId=61&merchantId=849084",
    "https://www.trendyol.com/trixie/mr-fox-500-ml-paslanmaz-celik-suluk-pipetsiz-su-matarasi-cocuk-su-sisesi-p-754018822?boutiqueId=61&merchantId=849084",
]


def gez_yollu(dugum, yol=""):
    """JSON agacini yol bilgisiyle dolasir: (yol, sozluk) ciftleri uretir."""
    if isinstance(dugum, dict):
        yield yol, dugum
        for k, v in dugum.items():
            yield from gez_yollu(v, f"{yol}.{k}")
    elif isinstance(dugum, list):
        for i, v in enumerate(dugum[:5]):
            yield from gez_yollu(v, f"{yol}[{i}]")


def incele(sayfa, url):
    print(f"\n{'='*70}\nURL: {url[:90]}")
    sayfa.goto(url, timeout=60000, wait_until="domcontentloaded")
    sayfa.wait_for_timeout(6000)
    print(f"Varilan: {sayfa.url[:90]}")
    ham = sayfa.evaluate(
        "() => JSON.stringify(window.__PRODUCT_DETAIL_APP_INITIAL_STATE__ || null)")
    if not ham or ham == "null":
        print("GOMULU VERI YOK! Sayfadaki window degiskenlerinden PRODUCT icerenler:")
        adlar = sayfa.evaluate(
            "() => Object.keys(window).filter(k => k.toUpperCase().includes('PRODUCT')"
            " || k.startsWith('__'))")
        print(" ", adlar[:20])
        # DOM'da fiyat kutusu var mi?
        for secici in ("div[class*='price']", "span.prc-dsc", "[data-testid*='price']"):
            el = sayfa.locator(secici).first
            if el.count() > 0:
                print(f"  DOM {secici}: {el.inner_text(timeout=2000)[:120]!r}")
        return
    veri = json.loads(ham)
    print(f"Gomulu veri VAR, boyut: {len(ham)} karakter")
    # merchant / otherMerchants / fiyat iceren dugumleri raporla
    bulunan = 0
    for yol, d in gez_yollu(veri):
        anahtar_kumesi = set(d.keys())
        if "otherMerchants" in anahtar_kumesi or "merchant" in anahtar_kumesi:
            print(f"\n-- Dugum: {yol[:80]}")
            print(f"   anahtarlar: {sorted(anahtar_kumesi)[:15]}")
            m = d.get("merchant")
            if isinstance(m, dict):
                print(f"   merchant.name: {m.get('name')!r}")
            om = d.get("otherMerchants")
            if isinstance(om, list):
                print(f"   otherMerchants: {len(om)} adet")
            p = d.get("price")
            if isinstance(p, dict):
                print(f"   price anahtarlari: {sorted(p.keys())[:10]}")
                print(f"   price ornegi: {json.dumps(p, ensure_ascii=False)[:300]}")
            bulunan += 1
            if bulunan >= 3:
                break
    if bulunan == 0:
        print("merchant/otherMerchants iceren dugum YOK. 'rice' gecen anahtarlar:")
        ornekler = set()
        for yol, d in gez_yollu(veri):
            for k in d.keys():
                if "rice" in k.lower():
                    ornekler.add(f"{yol[:60]}.{k}")
        for o in sorted(ornekler)[:15]:
            print("  ", o)


def main():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        tarayici = p.chromium.launch()
        baglam = tarayici.new_context(locale="tr-TR")
        baglam.add_cookies([
            {"name": "countryCode", "value": "TR", "domain": ".trendyol.com", "path": "/"},
            {"name": "language", "value": "tr", "domain": ".trendyol.com", "path": "/"},
            {"name": "storefrontId", "value": "1", "domain": ".trendyol.com", "path": "/"},
        ])
        sayfa = baglam.new_page()
        for url in HEDEFLER:
            try:
                incele(sayfa, url)
            except Exception as h:
                print(f"HATA: {h}")
        tarayici.close()


if __name__ == "__main__":
    main()
