# UI 验收 Case 2 — 偏差标注定位 Prompt（Grounding 考核）

> 使用方法：在 Case 1 之后进行。将【实现截图】单独发给模型，并结合 Case 1 的输出结果，要求模型输出每个偏差的边界框。用于考核 VLM 的 grounding（视觉定位）能力。
> 后处理：用 Python 脚本读取 JSON，在截图上画出边界框 + 编号，生成「标注版截图」用于文章配图。

---

## Prompt 正文

你是一名 UI 验收工程师。这是开发实现的页面截图。以下是已经确认的 N 个视觉偏差问题：

{此处粘贴 Case 1 输出的 issues 列表}

请在截图坐标系内，为每个偏差问题标出边界框。

【输出格式】严格输出 JSON：

```json
{
  "boxes": [
    {
      "issue_id": 1,
      "bbox_2d": [x_min, y_min, x_max, y_max],
      "label": "简短标签，如「主按钮色值偏移」"
    }
  ]
}
```

【要求】
- 坐标基于图片实际分辨率 {WIDTH}x{HEIGHT}（截图时请使用 2x 缩放以获得清晰标注）
- 边界框应包住偏差区域及其可见上下文（如整个按钮、整行文字），不要只框一个像素点
- 如果某个 issue 在图中无法定位（例如抽象问题），bbox_2d 输出 null 并在 label 中说明
- 严格 JSON 输出，无其他内容

---

## 标注渲染脚本（Python）

```python
#!/usr/bin/env python3
"""render_boxes.py — 读取模型输出的 boxes JSON，在截图上画框生成标注图
用法: python render_boxes.py <screenshot.png> <boxes.json> <output.png>
"""
import json, sys
from PIL import Image, ImageDraw, ImageFont

COLORS = {"P0": "#E24B4A", "P1": "#EF9F27", "P2": "#378ADD"}

def main(img_path, boxes_path, out_path, severity_map=None):
    img = Image.open(img_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    data = json.load(open(boxes_path))
    sev = severity_map or {}
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 22)
    except Exception:
        font = ImageFont.load_default()
    for b in data.get("boxes", []):
        if not b.get("bbox_2d"):
            continue
        x0, y0, x1, y1 = b["bbox_2d"]
        color = COLORS.get(sev.get(str(b["issue_id"]), ""), "#E24B4A")
        draw.rectangle([x0, y0, x1, y1], outline=color, width=4)
        tag = f'#{b["issue_id"]} {b["label"]}'
        tb = draw.textbbox((x0, max(0, y0 - 30)), tag, font=font)
        draw.rectangle([tb[0] - 4, tb[1] - 2, tb[2] + 4, tb[3] + 2], fill=color)
        draw.text((tb[0], tb[1] - 2), tag, fill="white", font=font)
    img.save(out_path)
    print(f"saved -> {out_path}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
```

> severity_map 参数：Case 1 输出的 issue_id → 严重度映射 dict，可控制框颜色（红 P0 / 橙 P1 / 蓝 P2）。
