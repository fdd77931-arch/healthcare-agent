---
name: 循迹
description: 一套以行动分层记录页为原型的温和临床视觉系统
colors:
  ink: "#173b36"
  primary: "#176b5d"
  primary-deep: "#0f554a"
  surface: "#ffffff"
  canvas: "#edf5f2"
  line: "#c9dcd6"
  muted: "#4f6f69"
  warning: "#9a5b16"
  danger: "#a23f35"
typography:
  display:
    fontFamily: "Georgia, Songti SC, serif"
    fontSize: "clamp(2.45rem, 9vw, 5.3rem)"
    fontWeight: 400
    lineHeight: 0.98
    letterSpacing: "-0.035em"
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, PingFang SC, Microsoft YaHei, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.7
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, PingFang SC, Microsoft YaHei, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 650
    lineHeight: 1.4
    letterSpacing: "0.04em"
rounded:
  control: "12px"
  panel: "20px"
  pill: "999px"
spacing:
  xs: "6px"
  sm: "12px"
  md: "20px"
  lg: "32px"
  xl: "56px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "13px 20px"
    height: "48px"
  button-primary-hover:
    backgroundColor: "{colors.primary-deep}"
    textColor: "{colors.surface}"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "14px 16px"
  result-panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "24px"
---

# Design System: 循迹

## Overview

**Creative North Star: “诊室里的行动记录页”**

循迹借用的是医生记录与分诊路径的秩序，而不是医院蓝色或聊天机器人的气泡。页面由可阅读的留白、墨绿文字、鼠尾草画布和一条随流程推进的“循迹线”构成；它看起来像一份有人认真整理过的行动记录。

表达只集中在路径线与宋体感标题。所有输入、状态和结果保持熟悉、清楚、低负担。

**Key Characteristics:**

- 一条纵向路径线串起当前阶段、提问与结论。
- 白色记录面铺在鼠尾草画布上，不使用玻璃、霓虹或装饰性渐变。
- 结果先给行动等级，再呈现理由、未知项和升级信号。
- 不使用左右对话气泡，不模拟人格化医生。

## Colors

深墨绿承担阅读与信任，饱和度克制的诊室绿只用于行动；风险色严格按语义出现。

**The Quiet Canvas Rule.** 鼠尾草色属于整页环境，白色属于需要阅读或输入的记录面；不要把主色拆成散落的装饰斑点。

**The Risk Means Risk Rule.** 橙棕只表达需要尽快处理，砖红只表达急症和急救入口。

## Typography

**Display Font:** Georgia（中文回退 `"Songti SC"` 与系统衬线）

**Body Font:** 系统无衬线（优先使用平台中文界面字体）

**Character:** 标题像记录页上的编辑性题签，正文像可信的临床说明。衬线只用于关键标题和结论，不进入长段正文或控件。

### Hierarchy

- **Display**（400，响应式 2.45–5.3rem，行高 0.98）：仅用于首屏主张。
- **Headline**（400，1.8–2.5rem，行高 1.15）：状态标题与行动结论。
- **Title**（650，1–1.15rem，行高 1.45）：结果分组。
- **Body**（400，1rem，行高 1.7）：说明与回答，最大 70ch。
- **Label**（650，0.8125rem，字距 0.04em）：字段标签与阶段标记，不全大写。

**The Serif Is a Signal Rule.** 衬线字体只标记“现在最重要的判断”，不用于按钮、标签和辅助文字。

## Layout

移动端为单列流程：品牌、首屏主张、当前记录面依次出现，表单下方保留紧凑的“行动建议，不是诊断”边界；急救入口停靠在顶部安全区，且布局为它预留空间。桌面在 900px 后成为不对称双栏，左侧保持完整产品边界与路径解释，右侧承载唯一操作面，急救入口回到右下角。内容宽度上限为 1180px，正文行长控制在 65–70ch。

间距采用 6、12、20、32、56px 节奏；同组信息紧密，状态之间留出明显停顿。结果内容在宽屏下可分两列，但行动标题始终跨列领先。

## Elevation & Depth

深度来自色面叠加、1px 低对比边界和带垂直偏移的柔和阴影。阴影只用于主记录面与固定急救入口，避免每个信息块都浮起。

## Shapes

控件使用 12px 圆角，主记录面使用 20px 圆角，小型状态标签可用胶囊形。圆角不是装饰：只标记可交互控件、完整记录面与状态标签，普通文本分组用间距和细线组织。

## Components

- **Primary button:** 48px 高的实心墨绿按钮，动作名称保持稳定；加载时保留宽度并禁用。
- **Text field:** 白色或近白输入面、清晰边界；聚焦时使用双层主色焦点，不依赖阴影猜测状态。
- **Process rail:** 细线与圆点表达开始、追问、行动三个真实阶段；当前圆点为实心。
- **Result block:** 先呈现行动等级和时间窗，再用线性分组展示科室、理由、未知项与升级信号。
- **Emergency action:** 固定 `tel:120`，始终使用固定文案，不从 API 拼接号码；单列布局停靠顶部安全区，双栏布局固定在右下角。

## Do's and Don'ts

### Do

- 用行动动词命名按钮和结果。
- 错误说明具体发生了什么，并同时给出“重试”与“返回修改”路径。
- 保持用户输入直到请求成功。
- 在急症结果出现时把焦点移到标题。

### Don't

- 不使用聊天气泡、头像、机器人拟人文案。
- 不以“AI 诊断”或准确率承诺换取信任。
- 不用渐变、玻璃、发光边框或成排图标卡片制造医疗感。
- 不隐藏产品边界、未知信息或升级信号。
