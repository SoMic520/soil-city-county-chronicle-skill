<div align="center">

# 🌱 三普县级土壤志撰写与排版 Skill

**从已有三普报告出发，形成证据可追溯、篇幅受控、格式规范的县级土壤志。**

[![Version](https://img.shields.io/badge/version-2026--09--07--r4-2e7d32?style=flat-square)](CHANGELOG.md)
[![Tests](https://img.shields.io/badge/tests-72%20passed-2e7d32?style=flat-square)](scripts/)
[![Python](https://img.shields.io/badge/Python-3.9%2B-3776ab?style=flat-square&logo=python&logoColor=white)](scripts/)
[![Language](https://img.shields.io/badge/language-简体中文-c62828?style=flat-square)](SKILL.md)

[快速开始](#-快速开始) · [平台兼容](#-平台兼容) · [核心能力](#-核心能力) · [篇幅契约](#-篇幅契约) · [质量门槛](#-质量门槛)

</div>

> [!IMPORTANT]
> 这是县级土壤志编纂工作流，不是自动生成县情事实的工具。地方事实、数值、空间规律、历史变化和建议必须来自可定位的报告、表图或正式确认记录。

## ✨ 核心能力

| 模块 | 能做什么 | 关键约束 |
|---|---|---|
| 📚 前期资料 | 盘点总体、工作、类型、属性、数据、退化、耕地质量和适宜性等报告 | 文件名不等于内容已核验 |
| 🔗 证据台账 | 建立章节—主张—来源—指标—图表追溯链 | 缺证据不补写事实 |
| 🧱 六章编纂 | 区域概况、形成分类分布、土壤类型、理化性质、评价利用、保护建议 | 全部土种逐项覆盖 |
| 📏 篇幅控制 | 从适用模板实测基线，按土种、指标、评价模块和建议主题自适应折算 | 自适应但不能差距失控 |
| 🧭 专题适用性 | 区分适用且有材料、适用但缺材料、不适用、尚未明确 | 土特产未开展可有据省略 |
| 📝 规范排版 | 严格映射“第一章—一、—（一）—1.—（1）”标题层级 | 执行县级验收导引与三普排版基准 |
| ✅ 终稿检查 | 检查资料、覆盖、数值、篇幅、版面计划和DOCX结构 | 脚本通过不等于专家验收通过 |

## 🧭 工作流程

```mermaid
flowchart LR
    A[已有三普报告] --> B[资料与版本台账]
    B --> C[口径、证据与冲突核验]
    C --> D[模板计量与篇幅契约]
    D --> E[六章契约与逐土种编纂]
    E --> F[数值、表图和历史可比性审查]
    F --> G[Word规范排版]
    G --> H[全页渲染与终稿归档]
```

## 🚀 快速开始

### 1. 安装

将仓库克隆到Codex个人技能目录：

```powershell
git clone <本仓库地址> "C:\Users\<用户名>\.codex\skills\soil-county-chronicle"
```

### 2. 调用

```text
使用 $soil-county-chronicle，先盘点我提供的三普报告，建立资料、证据和缺口台账，
再确定六章篇幅契约，编写证据充分的章节并按县级验收导引排版。
```

### 3. 初始化项目工作台

```powershell
python scripts/chronicle.py init "D:\项目\县级土壤志工作台"
```

初始化操作拒绝覆盖已有目录。新项目中的资料、专题、篇幅和格式状态均保持未确认，必须根据真实材料填写。

## 🤝 平台兼容

| 平台 | 安装位置 | 支持方式 |
|---|---|---|
| OpenAI Codex | `~/.codex/skills/soil-county-chronicle` | 根目录原生Skill |
| Claude Code | `~/.claude/skills/soil-county-chronicle` | 根目录兼容Agent Skills开放格式 |
| WorkBuddy | `platforms/workbuddy/soil-county-chronicle` | 官方字段与`references/scripts/templates`专用适配 |
| 其他Agent Skills平台 | 平台规定的Skills目录 | 使用根目录，并先确认脚本执行权限 |

WorkBuddy管理界面如要求ZIP，请在本地压缩其专用子目录；仓库本身不上传或分发压缩包。完整说明见[平台兼容矩阵](platforms/README.md)。

## 📏 篇幅契约

县级导引没有规定全国统一总字数。本Skill采用“模板实测＋结构折算＋偏差上限”：

| 控制对象 | 普通项目门槛 |
|---|---:|
| 第一、二章目标 | 模板对应章 ±15% |
| 第三至六章目标 | 按重复结构单元折算，且不偏离模板对应章 ±30% |
| 六章目标合计 | 模板六章合计 ±20% |
| 各章终稿实际值 | 已锁定章目标 ±15% |
| 六章终稿实际合计 | 总目标 ±10%，且模板合计 ±25% |

默认指标是“接受修订后的章内叙述正文有效字符数”。标题、表格、题注、页眉页脚、附件及删除的修订文字不计。详细规则见[篇幅契约](references/length.md)。

```powershell
python scripts/length_profile.py measure-docx "模板.docx"
python scripts/length_profile.py calculate-plan "length-plan.json" --output "待复核计划.json"
python scripts/length_profile.py check-plan "length-plan.json" --final
```

> [!NOTE]
> 土特产专题确属未开展或不适用时，可以依据导引省略；仅仅缺少报告，不能把模块数按0处理。

## ✅ 质量门槛

```powershell
# 工作台记录检查
python scripts/chronicle.py check "D:\项目\县级土壤志工作台"

# 终稿门槛
python scripts/chronicle.py check "D:\项目\县级土壤志工作台" --final

# DOCX只读结构检查
python scripts/chronicle.py docx-check "县级土壤志.docx"

# 全部回归测试
python -m unittest discover -s scripts -p "test_*.py"
```

当前版本在工作区和安装版均通过72项合成回归测试。检查器不会认证台账所填事实，也不能替代目标软件重开、字段更新、全页渲染和专家审查。

## 🗂️ 目录结构

```text
soil-county-chronicle-skill/
├─ SKILL.md                 # Skill入口与强制工作流
├─ agents/openai.yaml       # Codex界面元数据
├─ references/              # 依据、资料、章节、写作、篇幅、排版和质量规则
├─ assets/project/          # 可复制的项目台账与审查模板
├─ scripts/                 # 初始化、记录检查、DOCX检查和篇幅计量
├─ platforms/workbuddy/     # WorkBuddy Open Platform专用适配
├─ tools/                   # 适配构建与跨平台验证
├─ .github/ISSUE_TEMPLATE/  # 问题与规则建议模板
├─ CHANGELOG.md
├─ CONTRIBUTING.md
└─ SECURITY.md
```

## 🧪 设计原则

- **资料先行**：优先读取已有成果报告，再提出最小补件。
- **证据先于成文**：先锁定对象、时期、地类、土层、方法、单位和分母。
- **缺口局部阻断**：缺失只限制受影响的主张和章节，不让整个项目停摆。
- **模板不是事实源**：范文只提供结构和篇幅参照，不提供目标县数据。
- **排版与内容分开验收**：配置通过、DOCX结构通过和逐页视觉通过是三件事。
- **不宣称绝对完美**：用可复核的门槛、日志和回归测试持续收敛问题。

## 🔐 数据安全

仓库不包含县级原始数据库、样点坐标、化验数据、GIS成果、超大参考志稿、项目报告或ZIP发布包。请勿将未脱敏项目资料提交到代码仓库，详见[安全说明](SECURITY.md)。

## 📌 当前版本

`2026-09-07-r4`：新增模板驱动的篇幅契约、只读DOCX有效字符计量、自动计划生成及终稿偏差门槛。完整变化见[CHANGELOG](CHANGELOG.md)。
