#!/usr/bin/env python3
"""run_case1_v2.py — 改进版 harness：逐区域 checklist 核对
两轮对比用于文章「harness 工程对 VLM 表现的影响」章节。
用法: python run_case1_v2.py --pages page1,page2,page3
"""
import argparse, base64, json, os, re, time
from pathlib import Path
from urllib import request as urlreq

HERE = Path(__file__).parent
API_KEY = os.environ.get("ARK_API_KEY", "")  # 从环境变量读取，勿硬编码
BASE_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"
MODEL = "doubao-seed-evolving"
RESULTS = HERE / "results"
RESULTS.mkdir(exist_ok=True, parents=True)

from run_case1 import GROUND_TRUTH, match_issue

SPEC = (HERE / "prompts" / "design-spec.md").read_text(encoding="utf-8")

# 每页的核对区域 checklist —— 强制逐区扫过，防「整体相似即互信」
CHECKLISTS = {
    "page1": [
        "页头区：标题字重与字号、副标题颜色深浅",
        "第一张卡片：标题、标题右侧状态标签（是否存在、样式）、三行列表（每行的分隔线、文字色值）、主按钮（背景色、圆角、文字）",
        "第二张卡片：标题、表单标签、输入框（边框圆角、当前值）、表单下方提示文字颜色",
        "整体：卡片间距、卡片内边距、所有文字色值逐一核对",
    ],
    "page2": [
        "页头区：标题颜色、筛选按钮（描边、圆角、文字色）",
        "表头行：每列字重、颜色",
        "数据行逐行核对（共 4 行）：每行的数值列对齐方向、环比列的颜色与正负号语义（涨应为绿色、跌应为红色）、状态列标签的底色与形状",
        "行分隔线亮度、页脚文字颜色",
        "整体：行内边距（行高是否被压缩）、深色背景下所有文字的对比度",
    ],
    "page3": [
        "状态栏与导航栏：返回箭头大小、标题",
        "第一张订单卡：状态标签颜色（已完成应为绿色系）、商品图容器底色、价格文字、底部总价文字的字号字重、按钮",
        "第二张订单卡：同上逐项",
        "卡片：圆角、内边距、卡片间距离",
        "底部 Tab 栏：选中项颜色（应为品牌紫）、未选中项颜色、**Tab 栏距屏幕底部的留白是否充足（全面屏安全区，应有明显留白而非紧贴底边）**",
        "整体：所有可点击元素的尺寸是否足够（触控热区不小于 44x44pt）",
    ],
}

PROMPT_TEMPLATE = """你是一名资深的 UI 设计验收工程师。给你两张截图：
1. 第一张是设计稿（设计基准）
2. 第二张是开发实现的页面截图

请**逐个区域**按下方 checklist 顺序核对，每个区域都必须给出结论（一致 / 存在偏差），禁止跳过任何一项。哪怕两图整体看起来相似，也要逐项比对具体属性值（色值、字号、字重、间距、圆角、对齐方向、有无底色）。

【核对 checklist】
{checklist}

【语义判断规则】
- 涨跌数据：中国市场惯例「涨=绿色、跌=红色」。若实现中 +12.4% 显示为红色或 -3.2% 显示为绿色，属于 P0 语义色错误
- 数值列（金额/用量）：必须右对齐，左对齐属于 P0
- 状态标签：必须有胶囊底色，裸文字属于样式丢失
- 移动端：底部导航距屏幕底边留白不足属于 P0 安全区问题；可点击元素过小属于触控热区问题

【优先级】P0=阻断发布（语义错误/数据不可读/安全区缺失）；P1=明显不一致（字重/间距/缺失/圆角/对齐）；P2=轻微偏差（对比度/描边/次要色）

【硬性要求】
- 只报告真实可见的差异，禁止臆造；核对一致的区域要如实记入 not_found_areas
- 涉及颜色给出近似色值

【输出格式】严格输出 JSON：

{{
  "summary": "总体结论",
  "verdict": "fail 或 pass",
  "checklist_results": [
    {{"area": "核对区域名", "conclusion": "一致 或 存在偏差"}}
  ],
  "issues": [
    {{
      "id": 1,
      "type": "色彩偏差|字重错误|间距偏差|元素缺失|圆角偏差|对比度不足|对齐错误|语义色错误|状态样式丢失|描边丢失|安全区问题|触控热区问题",
      "component": "偏差所在组件/区域",
      "design": "设计稿表现（含具体值）",
      "impl": "实现表现（含具体值）",
      "severity": "P0|P1|P2",
      "color_design": "近似色值或 null",
      "color_impl": "近似色值或 null",
      "fix_suggestion": "修改建议（含具体规格）"
    }}
  ],
  "not_found_areas": ["确认无差异的区域"],
  "confidence_note": "不确定项备注"
}}

【设计规范】
""" + SPEC


def b64(p: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


def call_api(images: list[str], prompt: str) -> tuple[dict, dict]:
    body = {
        "model": MODEL,
        "messages": [{
            "role": "user",
            "content": [{"type": "text", "text": prompt}] +
                       [{"type": "image_url", "image_url": {"url": u}} for u in images],
        }],
    }
    req = urlreq.Request(
        BASE_URL + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + API_KEY},
    )
    t0 = time.time()
    with urlreq.urlopen(req, timeout=600) as r:
        resp = json.load(r)
    elapsed = time.time() - t0
    content = resp["choices"][0]["message"]["content"]
    usage = resp.get("usage", {})
    m = re.search(r"\{.*\}", content, re.S)
    parsed = json.loads(m.group(0)) if m else {"raw": content}
    return parsed, {"usage": usage, "elapsed": round(elapsed, 1), "raw": content}


def evaluate(page: str, parsed: dict) -> dict:
    gts = GROUND_TRUTH[page]
    issues = parsed.get("issues", [])
    detected, missed, false_pos = [], [], []
    used = set()
    for gt in gts:
        hit = next((i for i in issues if id(i) not in used and match_issue(i, gt)), None)
        if hit:
            used.add(id(hit))
            detected.append(gt)
        else:
            missed.append(gt)
    for i in issues:
        if id(i) not in used and not any(match_issue(i, gt) for gt in gts):
            false_pos.append(i)
    return {
        "total_gt": len(gts),
        "detected": len(detected),
        "recall": f"{len(detected)}/{len(gts)}",
        "missed": [f"#{g['id']} {g['desc']}" for g in missed],
        "false_positives": len(false_pos),
        "fp_detail": [f"{i.get('component','?')}: {i.get('type','?')}" for i in false_pos],
    }


def main(pages: list[str]):
    report = {}
    for page in pages:
        stem = {"page1": "page1-team-management", "page2": "page2-dark-data-table",
                "page3": "page3-mobile-layout"}.get(page, page)
        design = HERE / "shots" / f"{stem}-design.png"
        impl = HERE / "shots" / f"{stem}-impl.png"
        if not (design.exists() and impl.exists()):
            print(f"[skip] {page}: 截图缺失")
            continue
        prompt = PROMPT_TEMPLATE.format(checklist="\n".join(f"{n+1}. {c}" for n, c in enumerate(CHECKLISTS[page])))
        print(f"[run v2] {page} ...", flush=True)
        try:
            parsed, meta = call_api([b64(design), b64(impl)], prompt)
        except Exception as e:
            print(f"[error] {page}: {e}")
            report[page] = {"error": str(e)}
            continue
        (RESULTS / f"{page}-case1-v2-output.json").write_text(
            json.dumps({"parsed": parsed, **meta}, ensure_ascii=False, indent=2), encoding="utf-8")
        score = evaluate(page, parsed)
        score["tokens"] = meta["usage"].get("total_tokens")
        score["elapsed_s"] = meta["elapsed"]
        report[page] = score
        print(f"  检出 {score['recall']}  误报 {score['false_positives']}  "
              f"tokens={score['tokens']}  耗时={score['elapsed_s']}s")
        if score["missed"]:
            print("  漏检:", "; ".join(score["missed"]))
        if score["fp_detail"]:
            print("  误报明细:", "; ".join(score["fp_detail"]))
    (RESULTS / "case1-v2-summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n==== v2 汇总已写入 results/case1-v2-summary.json ====")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", default="page1,page2,page3")
    ids = ap.parse_args().pages.split(",")
    main([p if p.startswith("page") else f"page{p}" for p in ids])
