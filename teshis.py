# -*- coding: utf-8 -*-
# TESHIS ARACI - surum 15
# Amac: kidsnjoystore.com urun listesi yapisini gormek

import re
import requests

BASLIKLAR = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "tr-TR,tr;q=0.9",
}


def main():
    ana = requests.get("https://kidsnjoystore.com", headers=BASLIKLAR, timeout=30).text
    print("ana sayfa:", len(ana), "karakter")
    linkler = sorted(set(re.findall(
        r'href="(https?://kidsnjoystore\.com/[^"]*(?:termos|suluk|matara|urun|kategori)[^"]*)"',
        ana, re.I)))
    for l in linkler[:10]:
        print("aday liste linki:", l)
    hedef = linkler[0] if linkler else "https://kidsnjoystore.com"
    liste = requests.get(hedef, headers=BASLIKLAR, timeout=30).text
    print("\nliste sayfasi:", hedef, "->", len(liste), "karakter")
    print("productItem adedi:", liste.count("productItem"))
    i = liste.find('class="productItem')
    if i > 0:
        print("\n--- ILK URUN KARTI (1500 kr) ---")
        print(liste[max(0, i - 200):i + 1300])


if __name__ == "__main__":
    main()
