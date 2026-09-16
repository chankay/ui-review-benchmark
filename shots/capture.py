#!/usr/bin/env python3
"""capture.py — Playwright 批量截图脚本
用法:
  python capture.py                # 截全部页面（默认偏差版）
  python capture.py --variant impl # 只截实现版
  python capture.py --variant design
输出目录: ../shots/<page>-<variant>.png（2x 缩放，1440/560/375 逻辑宽度）
依赖: pip install playwright && playwright install chromium
"""
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
OUT = HERE.parent / "shots"
OUT.mkdir(exist_ok=True, parents=True)

PAGES = [
    ("page1-team-management.html", "#design", "design", 960, 800),
    ("page1-team-management.html", "#impl", "impl", 960, 800),
    ("page2-dark-data-table.html", "#design", "design", 1120, 700),
    ("page2-dark-data-table.html", "#impl", "impl", 1120, 700),
    ("page3-mobile-layout.html", "#design", "design", 790, 1330),
    ("page3-mobile-layout.html", "#impl", "impl", 790, 1330),
]

def main(variant: str):
    targets = [p for p in PAGES if variant in ("all", p[2])]
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for html, selector, name, w, h in targets:
            page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=2)
            page.goto((HERE.parent / "pages" / html).as_uri())
            page.wait_for_timeout(400)
            el = page.locator(selector)
            page_name = html.replace(".html", "")
            out_file = OUT / f"{page_name}-{name}.png"
            el.screenshot(path=str(out_file))
            print(f"captured {out_file.name}")
            page.close()
        browser.close()

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=["all", "design", "impl"], default="all")
    main(ap.parse_args().variant)
