#!/usr/bin/env python3
"""capture_focus.py — page1 focus 态截图 + 无差异对照组截图
产出:
  shots/page1-team-management-impl-focus.png   (点击输入框后 focus 态)
  shots/clean/page1-...-impl.png               (无差异对照组)
"""
import shutil
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
OUT = HERE.parent / "shots"
CLEAN = OUT / "clean"
CLEAN.mkdir(exist_ok=True, parents=True)

SRC = HERE.parent / "pages" / "page1-team-management.html"
CLEAN_HTML = CLEAN / "page1-team-management-clean.html"

# 生成无差异版：删除所有偏差 CSS 规则
src = SRC.read_text(encoding="utf-8")
import re
clean = re.sub(r'/\* 偏差\d[^*]*\*/\n', '', src)
clean = re.sub(r'/\* 偏差\d+.*?\*/\n\.impl [^{]*\{[^}]*\}\n', '', clean)
CLEAN_HTML.write_text(clean, encoding="utf-8")
print(f"无差异对照组 HTML -> {CLEAN_HTML}")

with sync_playwright() as pw:
    browser = pw.chromium.launch()

    # 1) focus 态截图：原 impl 页面，点击输入框后截图卡片区域
    page = browser.new_page(viewport={"width": 960, "height": 800}, device_scale_factor=2)
    page.goto(SRC.as_uri())
    page.wait_for_timeout(300)
    # 聚焦输入框触发 :focus
    page.focus(".impl .form-input")
    page.wait_for_timeout(300)
    page.locator("#impl").screenshot(path=str(OUT / "page1-team-management-impl-focus.png"))
    print("focus 态截图 -> page1-team-management-impl-focus.png")
    page.close()

    # 2) 无差异对照组（设计稿基准自身也可作为 impl 输入）
    page2 = browser.new_page(viewport={"width": 960, "height": 800}, device_scale_factor=2)
    page2.goto(CLEAN_HTML.as_uri())
    page2.wait_for_timeout(300)
    page2.locator("#impl").screenshot(path=str(CLEAN / "page1-team-management-impl.png"))
    print("无差异对照组截图 -> clean/page1-team-management-impl.png")
    page2.close()

    browser.close()
print("done")
