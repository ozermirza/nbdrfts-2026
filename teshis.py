# -*- coding: utf-8 -*-
# TESHIS ARACI - surum 14
# Amac: sipnjoylife neden NEXT_DATA vermiyor?

import re
import requests

BASLIKLAR = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "tr-TR,tr;q=0.9",
}


def main():
    r = requests.get("https://www.sipnjoylife.com", headers=BASLIKLAR, timeout=30)
    print("durum kodu:", r.status_code)
    print("boyut:", len(r.text), "karakter")
    print("NEXT_DATA var mi:", "__NEXT_DATA__" in r.text)
    print("nuxt var mi:", "__NUXT__" in r.text)
    print("cloudflare/challenge ipucu:",
          any(k in r.text.lower() for k in ("cloudflare", "challenge", "captcha",
                                            "attention required", "just a moment")))
    print("\n--- ILK 600 KARAKTER ---")
    print(r.text[:600])
    print("\n--- script id gecen satirlar ---")
    for m in re.findall(r'<script[^>]*id="[^"]*"[^>]*>', r.text)[:8]:
        print(m[:120])


if __name__ == "__main__":
    main()
