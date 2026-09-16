# UI Review Benchmark

用 VLM（Doubao-Seed-2.1-pro-0915）做 UI 设计验收的完整测评素材与脚本。

配套文章：《UI 设计验收助手实测：我把设计稿和截图都喂给 Seed-2.1-pro，检出率从 43% 拉到 70%》

## 测评内容

| Case | 内容 | 核心结果 |
|------|------|---------|
| Case 1 | 设计稿 vs 实现截图的差异识别 | 自由模式 43% → checklist harness **70%**，全程零误报 |
| Case 2 | 偏差定位标注（grounding） | 13/13 定位成功，数据表格页平均 IoU 0.56 |
| Case 3 | 修复闭环（识别→修改→复检） | 埋雷检出 + 主动发现报告外偏差 |

## 目录结构

```
├── pages/          3 个测试页面（每个含设计稿基准 + 埋偏差实现版，共 23 处埋点）
│   ├── page1-team-management.html    桌面浅色页，8 处埋点
│   ├── page2-dark-data-table.html    深色数据表格，8 处埋点（含涨跌语义色反转 P0）
│   └── page3-mobile-layout.html      移动端 375px，7 处埋点（含安全区缺失 P0）
├── prompts/        测评 prompt 与设计规范
│   ├── design-spec.md                设计规范（验收依据）
│   ├── case1-diff-review-prompt.md   差异识别 prompt（结构化 JSON 输出）
│   ├── case2-grounding-prompt.md     定位标注 prompt + IoU 渲染脚本
│   └── case3-fix-loop-prompt.md      修复闭环 prompt + 评分口径
├── shots/          Playwright 截图脚本与全部截图
│   ├── capture.py                    批量截图（设计稿/实现版）
│   ├── capture_focus.py              focus 态 + 无差异对照组截图
│   └── clean/                        无差异对照组（测「减少编造」用）
├── results/        原始测评输出（JSON）与两轮对比报告
├── run_case1.py    Case 1 执行脚本（含评分器）
├── run_case1_v2.py Case 1 checklist harness 版
├── run_case2.py    Case 2 执行脚本（IoU 评估 + 标注图渲染）
└── run_case3.py    Case 3 执行脚本（修复应用 + 复检评分）
```

## 复现步骤

```bash
# 1. 安装依赖
pip install playwright pillow
playwright install chromium

# 2. 配置 API Key（火山方舟，模型 doubao-seed-evolving）
export ARK_API_KEY="your-api-key"

# 3. 生成截图
cd shots && python capture.py && python capture_focus.py

# 4. 跑测评
cd ..
python run_case1.py   --pages page1,page2,page3   # 自由模式
python run_case1_v2.py --pages page1,page2,page3   # checklist 模式
python run_case2.py                                # grounding 定位
python run_case3.py                                # 修复闭环
```

## 埋点设计说明

23 处偏差覆盖三个层级：

1. **像素级**：色值偏移、字重错误、间距压缩、圆角丢失
2. **组件级**：元素缺失、样式退化（胶囊标签变裸文字）、对齐错误
3. **语义级**（像素 diff 工具无法发现）：
   - 涨跌语义色反转（违反素材自身声明的语义色规则；A股真实惯例为红涨绿跌）
   - 移动端安全区缺失（设计规范中故意未写，考核模型经验知识）
   - focus 交互态颜色错误（需交互后截图才能呈现）

其中 page1 的无差异对照组（`shots/clean/`）用于考核模型是否会「为找茬而编造」——实测两轮零误报。

## 主要发现

- **harness 决定表现下限**：同一模型同一素材，仅将「整体对比」改为「逐区域 checklist」，检出率 43% → 70%
- **零误报**：模型严格执行「禁止臆造」约束，不确定的偏差主动写入 confidence_note 而非硬报
- **能力边界**：深色背景小字号彩色文字存在读数错误（把设计稿的绿/红误读为中性白），harness 工程无法解决
- **产物核验在线**：复检环节逐项核对截图实际表现，主动发现报告外偏差

## License

MIT
