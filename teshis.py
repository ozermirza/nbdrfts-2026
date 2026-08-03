# -*- coding: utf-8 -*-
# TESHIS ARACI - surum 9
# Amac: sipnjoylife NEXT_DATA katalogunda urun kaydinin alan adlarini gormek
# (link hangi alanda saklaniyor?)

import json
import re

import requests

BASLIKLAR = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "tr-TR,tr;q=0.9",
}


def gez(dugum):
    if isinstance(dugum, dict):
        yield dugum
        for v in dugum.values():
            yield from gez(v)
    elif isinstance(dugum, list):
        for v in dugum:
            yield from gez(v)


def main():
    html = requests.get("https://www.sipnjoylife.com", headers=BASLIKLAR,
                        timeout=30).text
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        print("NEXT_DATA yok!")
        return
    veri = json.loads(m.group(1))
    sayac = 0
    for d in gez(veri):
        if isinstance(d.get("variants"), list) and d.get("name") and d["variants"]:
            sayac += 1
            if sayac <= 3:
                print(f"\n=== URUN {sayac}: {d.get('name')!r}")
                print("alan adlari:", sorted(d.keys()))
                for alan in ("url", "slug", "handle", "seoUrl", "link", "path",
                             "productUrl", "seo"):
                    if alan in d:
                        print(f"  {alan} = {json.dumps(d[alan], ensure_ascii=False)[:200]}")
    print(f"\nToplam urun kaydi: {sayac}")


if __name__ == "__main__":
    main()
