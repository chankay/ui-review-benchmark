#!/usr/bin/env python3
"""run_case3.py — Case 3: 修复闭环测评
Step 1: 从 v2 输出提取修复建议，故意只给 6/8 条（埋雷）
Step 2: 脚本按建议自动修改 HTML（模拟 Coding Agent 产出）
Step 3: 重截图 -> 复检 prompt -> 统计漏网检出
"""
import base64, json, os, re, subprocess, time
from pathlib import Path
from urllib import request as urlreq

HERE = Path(__file__).parent
API_KEY = os.environ.get("ARK_API_KEY", "")  # 从环境变量读取，勿硬编码
BASE_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"
MODEL = "doubao-seed-evolving"
RESULTS = HERE / "results"
PAGES_DIR = HERE / "pages"
SHOTS = HERE / "shots"

# 埋雷：page1 8 条建议中故意扣下 #4(内边距) 和 #7(badge) 不给 -> 复检时应发现这 2 条漏网
WITHHOLD = {4, 7}

FIX_PROMPT = """你是前端工程师。以下是 UI 验收报告，请生成修复这些问题的 CSS 覆盖代码。

【验收报告】
{report}

【要求】
- 只修复报告中列出的问题，不要改动其他任何样式
- 输出格式：严格 JSON
{{
  "fixes": [
    {{"issue_id": 1, "css_selector": "目标选择器", "css_property": "属性", "css_value": "值"}}
  ]
}}
- 每个问题一条 fix，css_selector 用实现页面的实际类名"""


def b64(p):
    return "data:image/png;base64," + base64.b64encode(Path(p).read_bytes()).decode()


def api_call(content_parts, timeout=600):
    body = {"model": MODEL, "messages": [{"role": "user", "content": content_parts}]}
    req = urlreq.Request(BASE_URL + "/chat/completions", data=json.dumps(body).encode(),
                         headers={"Content-Type": "application/json", "Authorization": "Bearer " + API_KEY})
    t0 = time.time()
    with urlreq.urlopen(req, timeout=timeout) as r:
        resp = json.load(r)
    return resp, round(time.time() - t0, 1)


def apply_fixes(html_path: Path, fixes: list):
    """把 fixes 以 <style id=hotfix> 追加到 HTML head，模拟 Coding Agent 的修改"""
    css = "\n".join(
        f"{f['css_selector']} {{ {f['css_property']}: {f['css_value']} !important; }}"
        for f in fixes if f.get("css_selector") and f.get("css_property"))
    html = html_path.read_text(encoding="utf-8")
    html = re.sub(r'<style id="hotfix">.*?</style>\n?', '', html, flags=re.S)  # 幂等
    html = html.replace("</head>", f'<style id="hotfix">\n{css}\n</style>\n</head>')
    html_path.write_text(html, encoding="utf-8")
    return len(fixes)


def screenshot(page_html: Path, selector: str, out: Path, width=960, height=800, focus_click=False):
    script = f"""
import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={{"width": {width}, "height": {height}}}, device_scale_factor=2)
        await page.goto("{page_html.as_uri()}")
        await page.wait_for_timeout(300)
        {"await page.focus('.impl .form-input'); await page.wait_for_timeout(300)" if focus_click else ""}
        await page.locator("{selector}").screenshot(path="{out}")
        await browser.close()

asyncio.run(run())
"""
    subprocess.run(["/Users/cc/.workbuddy/binaries/python/envs/default/bin/python", "-c", script], check=True)


RECHECK_PROMPT = """这是修复后的页面截图。请对照以下验收报告（修复前的输出）逐项复核：

【上轮验收报告】
{report}

请输出复核结果 JSON：
{{
  "recheck_summary": "总体结论",
  "verdict": "pass 或 fail",
  "fixed": [{{"issue_id": 1, "verified": true, "evidence": "截图中的修复后表现"}}],
  "unfixed": [{{"issue_id": 4, "verified": false, "evidence": "仍然存在的问题表现"}}],
  "regressions": [{{"description": "新引入的偏差", "severity": "P0|P1|P2"}}]
}}

【要求】
- 逐项核对，不得凭报告说 fixed 就认定 fixed——必须以截图实际表现为准
- 报告未提及但截图上新出现的问题记入 regressions
- 上轮报告中未列出、但确实存在的旧问题（修复指令遗漏项），如你在截图中观察到，请记入 unfixed 并在 evidence 中注明「报告外发现」
- 严格 JSON 输出"""


def main():
    summary = {}
    for page in ["page1"]:
        stem = "page1-team-management"
        html_path = PAGES_DIR / f"{stem}.html"
        v2 = json.load(open(RESULTS / f"{page}-case1-v2-output.json"))
        issues = v2["parsed"]["issues"]

        # Step 1: 提取建议（埋雷：扣下 WITHHOLD）
        given = [i for i in issues if i.get("id") not in WITHHOLD]
        withheld = [i for i in issues if i.get("id") in WITHHOLD]
        print(f"[step1] 修复建议 {len(given)}/{len(issues)} 条（故意扣下: {[i['id'] for i in withheld]}）")
        report_text = json.dumps(
            [{"id": i["id"], "component": i.get("component"), "impl": i.get("impl"),
              "fix_suggestion": i.get("fix_suggestion")} for i in given],
            ensure_ascii=False, indent=1)

        resp, elapsed = api_call([{"type": "text", "text": FIX_PROMPT.format(report=report_text)}])
        content = resp["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", content, re.S)
        fixes = json.loads(m.group(0)).get("fixes", []) if m else []
        (RESULTS / f"{page}-case3-fixes.json").write_text(
            json.dumps({"fixes": fixes, "withheld": [i["id"] for i in withheld],
                        "tokens": resp["usage"]["total_tokens"]}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"  生成 {len(fixes)} 条 fix")

        # Step 2: 应用修复并重截图（focus 态）
        n = apply_fixes(html_path, fixes)
        print(f"[step2] 应用 {n} 条修复到 HTML")
        fixed_shot = SHOTS / f"{stem}-case3-fixed-focus.png"
        screenshot(html_path, "#impl", fixed_shot, focus_click=True)
        print(f"  重截图 -> {fixed_shot.name}")

        # Step 3: 复检
        print("[step3] 复检 ...")
        full_report = json.dumps(issues, ensure_ascii=False, indent=1)
        resp2, elapsed2 = api_call([
            {"type": "text", "text": RECHECK_PROMPT.format(report=full_report)},
            {"type": "image_url", "image_url": {"url": b64(fixed_shot)}},
        ])
        content2 = resp2["choices"][0]["message"]["content"]
        m2 = re.search(r"\{.*\}", content2, re.S)
        recheck = json.loads(m2.group(0)) if m2 else {}
        (RESULTS / f"{page}-case3-recheck.json").write_text(
            json.dumps({"recheck": recheck, "tokens": resp2["usage"]["total_tokens"],
                        "elapsed": elapsed2}, ensure_ascii=False, indent=2), encoding="utf-8")

        # 评分
        unfixed_ids = {u.get("issue_id") for u in recheck.get("unfixed", [])}
        caught_withheld = [i for i in WITHHOLD if i in unfixed_ids]
        false_fixed = [u for u in recheck.get("unfixed", []) if u.get("issue_id") not in WITHHOLD]
        summary[page] = {
            "fixes_applied": len(fixes),
            "withheld_ids": sorted(WITHHOLD),
            "withheld_caught": sorted(caught_withheld),
            "withheld_missed": sorted(set(WITHHOLD) - set(caught_withheld)),
            "false_unfixed": false_fixed,
            "regressions": recheck.get("regressions", []),
            "verdict": recheck.get("verdict"),
            "tokens_total": resp["usage"]["total_tokens"] + resp2["usage"]["total_tokens"],
        }
        print(f"  埋雷检出: {sorted(caught_withheld)} / {sorted(WITHHOLD)}")
        print(f"  误报漏修: {len(false_fixed)}  回归: {len(recheck.get('regressions', []))}")

    (RESULTS / "case3-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n==== Case 3 汇总已写入 results/case3-summary.json ====")


if __name__ == "__main__":
    main()
