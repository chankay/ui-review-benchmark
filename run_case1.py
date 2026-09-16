#!/usr/bin/env python3
"""run_case1.py — UI 验收 Case 1: 差异识别测评
对 3 个页面分别调用 doubao-seed-evolving，输出评分报告。
用法: python run_case1.py [--pages page1,page2,page3]
"""
import argparse, base64, json, os, re, time
from pathlib import Path
from urllib import request as urlreq

HERE = Path(__file__).parent
API_KEY = os.environ.get("ARK_API_KEY", "")  # 从环境变量读取，勿硬编码
BASE_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"
MODEL = "doubao-seed-evolving"
RESULTS = (HERE.parent / "results") if HERE.name == "shots" else (HERE / "results")
RESULTS.mkdir(exist_ok=True, parents=True)

# ---- 答案库（keywords 用于宽松匹配模型输出）----
GROUND_TRUTH = {
    "page1": [
        {"id": 1, "sev": "P0", "desc": "主按钮品牌色偏移 #534AB7→#3B82F6", "kw": ["主按钮", "邀请", "#3b82f6", "蓝"]},
        {"id": 2, "sev": "P1", "desc": "主按钮圆角 8px→20px", "kw": ["圆角", "按钮"]},
        {"id": 3, "sev": "P1", "desc": "页面标题字重 600→400", "kw": ["标题", "字重"]},
        {"id": 4, "sev": "P1", "desc": "卡片内边距 24px→12px", "kw": ["内边距", "间距", "padding"]},
        {"id": 5, "sev": "P2", "desc": "副标题对比度不足 #86868B→#C7C7CC", "kw": ["副标题", "对比度"]},
        {"id": 6, "sev": "P2", "desc": "列表分隔线丢失", "kw": ["分隔线"]},
        {"id": 7, "sev": "P1", "desc": "「进行中」badge 缺失", "kw": ["badge", "进行中", "标签", "徽标"]},
        {"id": 8, "sev": "P2", "desc": "输入框 focus 描边色错误（紫→红）", "kw": ["focus", "聚焦", "输入框", "描边"]},
    ],
    "page2": [
        {"id": 1, "sev": "P0", "desc": "涨跌语义色反转（涨绿跌红→涨红跌绿）", "kw": ["涨", "跌", "语义", "反转"]},
        {"id": 2, "sev": "P0", "desc": "数值列未右对齐", "kw": ["对齐", "右对齐", "tabular"]},
        {"id": 3, "sev": "P1", "desc": "表头字重 500→700", "kw": ["表头", "字重"]},
        {"id": 4, "sev": "P1", "desc": "行内边距 12px→6px 行密度过高", "kw": ["行", "内边距", "间距", "padding", "密度"]},
        {"id": 5, "sev": "P1", "desc": "「接近配额」标签底色丢失", "kw": ["接近配额", "标签", "胶囊", "底色"]},
        {"id": 6, "sev": "P2", "desc": "筛选按钮描边丢失", "kw": ["筛选", "描边"]},
        {"id": 7, "sev": "P2", "desc": "表格分隔线过亮 #2C2C2E→#48484A", "kw": ["分隔线", "过亮"]},
        {"id": 8, "sev": "P2", "desc": "页脚文字对比度不足", "kw": ["页脚", "对比度", "更新于"]},
    ],
    "page3": [
        {"id": 1, "sev": "P0", "desc": "Tab 栏底部安全区缺失 24px→4px", "kw": ["安全区", "底部", "tabbar", "tab 栏", "留白"]},
        {"id": 2, "sev": "P1", "desc": "返回按钮触控热区不足", "kw": ["热区", "返回", "点击", "触控"]},
        {"id": 3, "sev": "P1", "desc": "订单卡片圆角 12px→4px", "kw": ["圆角", "卡片"]},
        {"id": 4, "sev": "P1", "desc": "订单总价层级丢失（未加粗放大）", "kw": ["价格", "加粗", "总价", "层级"]},
        {"id": 5, "sev": "P2", "desc": "商品图占位底色缺失", "kw": ["商品图", "占位", "图标底", "图片"]},
        {"id": 6, "sev": "P2", "desc": "Tab 选中色 品牌紫→蓝", "kw": ["tab", "选中", "导航"]},
        {"id": 7, "sev": "P2", "desc": "「已完成」状态色 绿→灰", "kw": ["已完成", "状态", "灰"]},
    ],
}

SPEC = (HERE / "prompts" / "design-spec.md").read_text(encoding="utf-8")

PROMPT = """你是一名资深的 UI 设计验收工程师。我会给你两张截图：
1. 第一张是设计稿（设计基准）
2. 第二张是开发实现的页面截图

请以设计稿为基准，对实现截图进行逐区域视觉验收，找出所有偏差。

【硬性要求】
- 只报告你在截图中真实看到的差异，禁止推测或臆造截图中不存在的偏差
- 如果某个区域完全一致，不要为了凑数而报告
- 每个偏差必须给出：类型、位置（精确到组件）、设计稿表现 vs 实现表现、优先级、修改建议
- 优先级依据：P0=阻断发布（误导用户/数据不可读），P1=明显不一致（字重/间距/缺失/圆角），P2=轻微偏差（对比度/描边/次要色）
- 涉及颜色时给出你判断的近似色值
- 涉及业务语义（如涨跌颜色方向）时，按「涨=绿、跌=红」的中国市场惯例判断
- 移动端页面需额外关注安全区、触控热区等移动端特有问题

【输出格式】严格输出以下 JSON，不要输出其他内容：

{
  "summary": "一句话总体结论",
  "verdict": "fail 或 pass",
  "issues": [
    {
      "id": 1,
      "type": "色彩偏差|字重错误|间距偏差|元素缺失|圆角偏差|对比度不足|对齐错误|语义色错误|状态样式丢失|描边丢失|安全区问题|触控热区问题",
      "component": "偏差所在组件/区域",
      "design": "设计稿中的表现",
      "impl": "实现截图中的表现",
      "severity": "P0|P1|P2",
      "color_design": "设计稿近似色值（如涉及颜色，否则 null）",
      "color_impl": "实现近似色值（如涉及颜色，否则 null）",
      "fix_suggestion": "一句话修改建议，含具体规格"
    }
  ],
  "not_found_areas": ["检查过且确认无差异的区域"],
  "confidence_note": "对不确定的偏差做备注"
}

【设计规范】（作为验收依据）
""" + SPEC


def b64(p: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


def call_api(images: list[str]) -> tuple[dict, dict]:
    body = {
        "model": MODEL,
        "messages": [{
            "role": "user",
            "content": [{"type": "text", "text": PROMPT}] +
                       [{"type": "image_url", "image_url": {"url": u}} for u in images],
        }],
    }
    req = urlreq.Request(
        BASE_URL + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + API_KEY},
    )
    t0 = time.time()
    with urlreq.urlopen(req, timeout=300) as r:
        resp = json.load(r)
    elapsed = time.time() - t0
    content = resp["choices"][0]["message"]["content"]
    usage = resp.get("usage", {})
    m = re.search(r"\{.*\}", content, re.S)
    parsed = json.loads(m.group(0)) if m else {"raw": content}
    return parsed, {"usage": usage, "elapsed": round(elapsed, 1), "raw": content}


def match_issue(issue: dict, gt: dict) -> bool:
    text = json.dumps(issue, ensure_ascii=False).lower()
    return any(k in text for k in gt["kw"])


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


PAGE_FILES = {
    "page1": "page1-team-management",
    "page2": "page2-dark-data-table",
    "page3": "page3-mobile-layout",
}


def main(pages: list[str]):
    report = {}
    for page in pages:
        stem = PAGE_FILES.get(page, page)
        design = HERE / "shots" / f"{stem}-design.png"
        impl = HERE / "shots" / f"{stem}-impl.png"
        if not (design.exists() and impl.exists()):
            print(f"[skip] {page}: 截图缺失")
            continue
        print(f"[run] {page} ...", flush=True)
        try:
            parsed, meta = call_api([b64(design), b64(impl)])
        except Exception as e:
            print(f"[error] {page}: {e}")
            report[page] = {"error": str(e)}
            continue
        (RESULTS / f"{page}-case1-output.json").write_text(
            json.dumps({"parsed": parsed, **meta}, ensure_ascii=False, indent=2), encoding="utf-8")
        score = evaluate(page, parsed)
        score["tokens"] = meta["usage"].get("total_tokens")
        score["elapsed_s"] = meta["elapsed"]
        report[page] = score
        print(f"  检出 {score['recall']}  误报 {score['false_positives']}  "
              f"tokens={score['tokens']}  耗时={score['elapsed_s']}s")
        if score["missed"]:
            print("  漏检:", "; ".join(score["missed"]))
    (RESULTS / "case1-summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n==== 汇总已写入 results/case1-summary.json ====")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", default="page1,page2,page3")
    ids = ap.parse_args().pages.split(",")
    main([p if p.startswith("page") else f"page{p}" for p in ids])
