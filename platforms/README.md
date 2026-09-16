# 平台兼容

本仓库维护一个规范源，并按平台差异提供适配入口。

| 平台 | 使用目录 | 状态 | 说明 |
|---|---|---|---|
| OpenAI Codex | 仓库根目录 | 原生支持 | 根目录`SKILL.md`及`agents/openai.yaml` |
| Claude Code | 仓库根目录 | 兼容Agent Skills | 克隆到`.claude/skills/soil-city-county-chronicle` |
| WorkBuddy Open Platform | `platforms/workbuddy/soil-city-county-chronicle` | 专用适配 | 使用WorkBuddy要求的中英文描述、版本、作者和`templates/`结构 |
| 其他Agent Skills实现 | 仓库根目录 | 结构兼容 | 需确认平台是否支持`SKILL.md`、引用文件和Python脚本 |

WorkBuddy专用目录由`tools/build_workbuddy_adapter.py`从根目录规范源生成。GitHub Release提供自动构建的通用Skill ZIP和WorkBuddy ZIP；ZIP不提交到Git源码树。也可运行`tools/build_release_archive.py`在本地生成同结构包。

相关文档：

- [WorkBuddy Skill结构](https://open.workbuddy.cn/en/docs/skill)
- [Claude Code Skills](https://code.claude.com/docs/en/skills)
