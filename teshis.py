# -*- coding: utf-8 -*-
# TESHIS ARACI - surum 17
# Amac: kidsnjoy kategori sayfalamasinin parametresini bulmak

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def main():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        tarayici = p.chromium.launch()
        baglam = tarayici.new_context(locale="tr-TR", user_agent=UA)
        sayfa = baglam.new_page()
        sayfa.goto("https://kidsnjoystore.com/cocuk-su-termosu-20", timeout=60000)
        sayfa.wait_for_timeout(5000)
        adet = sayfa.eval_on_selector_all(".productItem", "els => els.length")
        print("sayfa 1 kart:", adet)
        linkler = sayfa.eval_on_selector_all(
            "a[href]", "els => [...new Set(els.map(e => e.href))]")
        for l in linkler:
            if any(k in l.lower() for k in ("sayfa", "page", "pg=", "pageno")):
                print("sayfalama linki:", l)
        toplam = sayfa.eval_on_selector_all(
            ".pagination, .paging, [class*='agin']",
            "els => els.map(e => (e.innerText || '').slice(0, 120))")
        print("sayfalama kutusu:", toplam)
        tarayici.close()


if __name__ == "__main__":
    main()
