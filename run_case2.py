#!/usr/bin/env python3
"""run_case2.py — Case 2: grounding 定位测评
输入: v2 Case1 输出的 issues + 实现截图
模型输出 bbox -> 与真实埋点区域计算 IoU -> 生成标注图
"""
import json, os, re, time, base64
from pathlib import Path
from urllib import request as urlreq
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
API_KEY = os.environ.get("ARK_API_KEY", "")  # 从环境变量读取，勿硬编码
BASE_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"
MODEL = "doubao-seed-evolving"
RESULTS = HERE / "results"

# 真实埋点 bbox（按截图实际像素坐标人工标定）
GT_BOXES = {
    "page1": {  # 960x1102
        1: {"bbox": [75, 583, 867, 665], "label": "主按钮品牌色偏移"},
        2: {"bbox": [75, 583, 867, 665], "label": "主按钮圆角偏差"},
        3: {"bbox": [48, 45, 194, 82], "label": "页面标题字重"},
        4: {"bbox": [48, 225, 890, 695], "label": "卡片内边距压缩"},
        5: {"bbox": [48, 100, 707, 128], "label": "副标题对比度"},
        7: {"bbox": [72, 255, 250, 288], "label": "badge缺失(成员概览右侧)"},
    },
    "page2": {  # 1120x558
        1: {"bbox": [875, 48, 1075, 82], "label": "筛选按钮描边丢失"},
        2: {"bbox": [305, 220, 460, 440], "label": "数值列未右对齐"},
        3: {"bbox": [876, 345, 990, 375], "label": "接近配额标签底色丢失"},
    },
    "page3": {  # 750x1240
        1: {"bbox": [576, 200, 644, 228], "label": "已完成状态色变灰"},
        3: {"bbox": [37, 168, 643, 476], "label": "订单卡片圆角"},
        4: {"bbox": [62, 400, 310, 432], "label": "订单总价层级丢失"},
        6: {"bbox": [62, 1130, 108, 1180], "label": "Tab选中色错误"},
        7: {"bbox": [576, 200, 644, 228], "label": "已完成状态色"},
    },
}

PROMPT = """你是一名 UI 验收工程师。这是开发实现的页面截图，分辨率 {w}x{h}。

以下是已经确认的视觉偏差问题清单：

{issues}

请为每个偏差问题在截图中标出边界框。

【输出格式】严格输出 JSON：
{{
  "boxes": [
    {{"issue_id": 1, "bbox_2d": [x_min, y_min, x_max, y_max], "label": "简短标签"}}
  ]
}}

【要求】
- 坐标基于图片实际分辨率 {w}x{h}
- 边界框包住偏差区域及其可见上下文（整个按钮、整行文字等）
- 无法定位的 issue 输出 bbox_2d: null 并说明
- 严格 JSON，无其他内容"""


def b64(p: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


def iou(a, b):
    ax0, ay0, ax1, ay1 = a; bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    area_a = (ax1 - ax0) * (ay1 - ay0)
    area_b = (bx1 - bx0) * (by1 - by0)
    union = area_a + area_b - inter
    return inter / union if union else 0


def main():
    summary = {}
    for page, gts in GT_BOXES.items():
        stem = {"page1": "page1-team-management", "page2": "page2-dark-data-table",
                "page3": "page3-mobile-layout"}[page]
        impl_path = HERE / "shots" / f"{stem}-impl.png"
        v2 = json.load(open(RESULTS / f"{page}-case1-v2-output.json"))
        issues = v2["parsed"].get("issues", [])
        img = Image.open(impl_path)
        w, h = img.size
        # 只测能定位的 issue
        targets = [i for i in issues if i.get("id") in gts]
        if not targets:
            continue
        issue_text = json.dumps(
            [{"id": i["id"], "type": i.get("type"), "component": i.get("component"),
              "impl": i.get("impl")} for i in targets], ensure_ascii=False, indent=1)
        prompt = PROMPT.format(w=w, h=h, issues=issue_text)
        print(f"[run case2] {page} ({len(targets)} issues, {w}x{h}) ...", flush=True)
        body = {
            "model": MODEL,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": b64(impl_path)}},
            ]}],
        }
        req = urlreq.Request(BASE_URL + "/chat/completions", data=json.dumps(body).encode(),
                             headers={"Content-Type": "application/json", "Authorization": "Bearer " + API_KEY})
        t0 = time.time()
        with urlreq.urlopen(req, timeout=600) as r:
            resp = json.load(r)
        elapsed = round(time.time() - t0, 1)
        content = resp["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", content, re.S)
        parsed = json.loads(m.group(0)) if m else {"boxes": []}
        (RESULTS / f"{page}-case2-output.json").write_text(
            json.dumps({"parsed": parsed, "tokens": resp["usage"]["total_tokens"],
                        "elapsed": elapsed}, ensure_ascii=False, indent=2), encoding="utf-8")
        # IoU 评估 + 画标注图
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 28)
        except Exception:
            font = ImageFont.load_default()
        details, ious = [], []
        for b in parsed.get("boxes", []):
            iid = b.get("issue_id")
            bbox = b.get("bbox_2d")
            if not bbox or iid not in gts:
                continue
            score = iou(bbox, gts[iid]["bbox"])
            ious.append(score)
            details.append({"issue_id": iid, "pred": bbox, "gt": gts[iid]["bbox"],
                            "iou": round(score, 3), "label": b.get("label")})
            draw.rectangle(bbox, outline="#E24B4A", width=5)
            tag = f'#{iid} {b.get("label","")}'
            tb = draw.textbbox((bbox[0], max(0, bbox[1] - 36)), tag, font=font)
            draw.rectangle([tb[0] - 4, tb[1] - 2, tb[2] + 4, tb[3] + 2], fill="#E24B4A")
            draw.text((tb[0], tb[1] - 2), tag, fill="white", font=font)
        out_img = HERE / "shots" / f"{stem}-case2-annotated.png"
        img.save(out_img)
        summary[page] = {
            "issues_tested": len(targets), "located": len(details),
            "mean_iou": round(sum(ious) / len(ious), 3) if ious else 0,
            "details": details, "tokens": resp["usage"]["total_tokens"], "elapsed": elapsed,
        }
        print(f"  定位 {len(details)}/{len(targets)}  mean_IoU={summary[page]['mean_iou']}  tokens={summary[page]['tokens']}")
    (RESULTS / "case2-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n==== Case 2 汇总已写入 results/case2-summary.json ====")


if __name__ == "__main__":
    main()
