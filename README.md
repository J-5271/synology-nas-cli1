# synology-nas-cli

Synology / 群晖 NAS 管理技能包。唯一真实来源是**本地 git 仓库**；
GitHub 公开仓库 <https://github.com/J-5271/synology-nas-cli> 是**只读分发镜像**。

⚠️ 分发仓库是公开的：真实 IP、主机名、序列号、账号、客户名**一律不得入库**，一律占位符。
注意 git **历史**也会留痕——带敏感信息的旧 commit 需要重写（filter-repo），不是删文件就行。

## 安装

```bash
# 方式一：直接 clone（跟随最新提交）
git clone https://github.com/J-5271/synology-nas-cli.git ~/.workbuddy/skills/synology-nas-cli

# 方式二：用 Release 里的稳定版（推荐）
# 下载 synology-nas-cli-vX.Y.Z.tar.gz + 同名 .sha256，校验后解压到
# ~/.workbuddy/skills/synology-nas-cli/
sha256sum -c synology-nas-cli-vX.Y.Z.sha256
```

## 版本发布

- 日常改动照常 commit 到本地仓库。
- 主要版本由维护者手动审批发布：GitHub Actions → `CI` → **Run workflow** → 填 `vX.Y.Z`。
  自动打包 tar.gz + SHA256，发布到 Release。

## 反馈与回传

- 改进建议 / 问题：GitHub Issue 或 PR。
- 实测记录、命令输出、文档：上传到 Synology **文件请求链接**
  <http://jiegy.quickconnect.cn/sharing/Y4sPpU0iP>（无需 DSM 账号，上传前请先脱敏）。
- 本包**不做任何自动遥测**，无出站上报，可完全离线使用。

## 目录

| 路径 | 内容 |
|---|---|
| `SKILL.md` | 主入口：实测设备档案、脱敏规范、同步策略、ima 回传流程 |
| `CHANGELOG.md` | 版本记录：日期 + 新增能力 |
| `DEPENDENCIES.md` | 依赖清单：< 1 MB 入库，≥ 1 MB 只记地址 |
| `CONTRIBUTING.md` | 协作规范：分支 + PR、提交前校验、内容红线 |
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
