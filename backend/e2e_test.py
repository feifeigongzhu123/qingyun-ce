# -*- coding: utf-8 -*-
"""用无头 Chromium 实测静态页：数据加载 + 查询 + 历年展开 + 截图。"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8080/"
SHOT = r"D:\AI\ZCode\青云策\backend\e2e_shot.png"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 1000})
    logs = []
    page.on("console", lambda m: logs.append((m.type, m.text)))
    page.on("pageerror", lambda e: logs.append(("pageerror", str(e))))

    page.goto(URL, wait_until="load")
    # 等数据加载完成（年份下拉被填充）
    page.wait_for_function("document.querySelectorAll('#year option').length > 0", timeout=30000)
    print("年份选项:", page.eval_on_selector_all("#year option", "els => els.map(e=>e.value)"))

    page.fill("#score", "560")
    page.click('#reselect .chip[data-s="化学"]')
    page.click('#reselect .chip[data-s="生物"]')
    page.click("#go")
    page.wait_for_selector("#rows tr.main", timeout=15000)

    print("SUMMARY:", page.inner_text("#summary").replace("\n", " "))
    rows = page.query_selector_all("#rows tr.main")
    print("主行数:", len(rows))
    bands = page.eval_on_selector_all("#rows tr.main .band", "els => els.map(e=>e.textContent)")
    from collections import Counter
    print("展示档位分布:", dict(Counter(bands)))

    # 展开第一行看历年
    rows[0].click()
    page.wait_for_timeout(300)
    hcells = page.query_selector_all(".hist-row .hcell")
    print("第一行历年格子数:", len(hcells))
    if hcells:
        print("历年样例:", [c.inner_text().replace("\n", " ") for c in hcells])

    # 测试分差切换 ±30
    page.click('#margin button[data-v="30"]')
    page.click("#go")
    page.wait_for_selector("#rows tr.main")
    print("±30 SUMMARY:", page.inner_text("#summary").replace("\n", " "))

    # 测试排除中外合作
    page.click("#fexcoop")
    page.click("#go")
    page.wait_for_selector("#rows tr.main")
    coop_tags = page.eval_on_selector_all("#rows tr.main .tag.tcoop", "els => els.length")
    print("排除中外合作后 前100中中外合作标签数:", coop_tags)

    page.screenshot(path=SHOT, full_page=True)
    print("截图已保存:", SHOT)
    print("控制台日志:", logs)
    browser.close()
