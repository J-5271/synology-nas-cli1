# synology-nas-cli

Synology / 群晖 NAS 管理技能包。唯一真实来源，私有仓库。

## 目录

| 路径 | 内容 |
|---|---|
| `SKILL.md` | 主入口：实测设备档案、脱敏规范、同步策略、ima 回传流程 |
| `CHANGELOG.md` | 版本记录：日期 + 新增能力 |
| `references/cli-commands.md` | DSM CLI 命令（synouser / synoshare / synogroup …） |
| `references/dsm-web-api.md` | DSM Web API 登录与调用 |
| `references/error-codes.md` | 错误码与排查套路 |
| `references/ssh-and-troubleshooting.md` | SSH 连接与故障处理 |
| `scripts/nas_exec.py` | SSH 执行器，内置只读/改配置守卫 |
| `scripts/dsm_api.py` | DSM Web API 客户端 |
| `scripts/pack_skill.py` | 打包（full/delta）+ 凭据扫描，命中凭据 exit 4 |
| `scripts/cos_upload.py` | COS 上传（ima 回传第二步） |

## 版本与同步节奏

- **每周**：`pack_skill.py --mode delta` 打增量，回传 ima「公用nas操作技能」；git commit 记历史。
- **每月**：`pack_skill.py --mode full` 打整包，REPLACE 覆盖 ima 主条目；git 打 tag `vYYYY.MM`。

## 红线

- 包内禁止真实账号 / 密码 / sid / 云密钥，示例一律占位符（`<账号>` / `<密码>` / `$ENV`）。
- 打包前跑凭据扫描，命中即中止（exit 4），不要用 `--allow-secrets`。
- 临时 COS 凭证用完即删，`*cred*.json` 已被 `.gitignore` 排除。
