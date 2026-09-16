# 平台兼容

本仓库维护一个规范源，并按平台差异提供适配入口。

| 平台 | 使用目录 | 状态 | 说明 |
|---|---|---|---|
| OpenAI Codex | 仓库根目录 | 原生支持 | 根目录`SKILL.md`及`agents/openai.yaml` |
| Claude Code | 仓库根目录 | 兼容Agent Skills | 克隆到`.claude/skills/soil-county-chronicle` |
| WorkBuddy Open Platform | `platforms/workbuddy/soil-county-chronicle` | 专用适配 | 使用WorkBuddy要求的中英文描述、版本、作者和`templates/`结构 |
| 其他Agent Skills实现 | 仓库根目录 | 结构兼容 | 需确认平台是否支持`SKILL.md`、引用文件和Python脚本 |

WorkBuddy专用目录由`tools/build_workbuddy_adapter.py`从根目录规范源生成。仓库不分发ZIP；如果WorkBuddy管理界面要求上传ZIP，请在本地仅压缩`platforms/workbuddy/soil-county-chronicle`目录，不要把生成的压缩包提交回仓库。

相关文档：

- [WorkBuddy Skill结构](https://open.workbuddy.cn/en/docs/skill)
- [Claude Code Skills](https://code.claude.com/docs/en/skills)

