# synology-nas-cli

> ## 免责声明
>
> 本技能包为**个人收集整理**的学习与运维笔记，内容来自 Synology 官方文档、官方知识库
> 以及个人设备上的实测记录，**仅供个人学习与技术交流使用**。
>
> - **禁止商用开发**：不得用于任何商业开发、商业交付、付费服务或二次分发获利。
> - **无担保**：不同机型 / DSM 版本差异很大，不保证内容适用于你的设备。
> - **风险自负**：因参考或使用本包造成的任何数据丢失、设备损坏或服务中断，
>   整理者不承担任何责任。执行任何写操作前请自行备份，并先在测试环境验证。
> - 商标与版权归各自权利人所有；若内容涉及侵权，请联系删除。

Synology / 群晖 NAS 管理技能包。唯一真实来源是**本地 git 仓库**；
GitHub 公开仓库 <https://github.com/J-5271/synology-nas-cli1> 是**只读分发镜像**。

⚠️ 分发仓库是公开的：真实 IP、主机名、序列号、账号、客户名**一律不得入库**，一律占位符。
注意 git **历史**也会留痕——带敏感信息的旧 commit 需要重写（filter-repo），不是删文件就行。

## 安装

```bash
# 方式一：直接 clone（跟随最新提交）
git clone https://github.com/J-5271/synology-nas-cli1.git ~/.workbuddy/skills/synology-nas-cli

# 方式二：用 Release 里的稳定版（推荐）
# 下载 synology-nas-cli-vX.Y.Z.tar.gz + 同名 .sha256，校验后解压到
# ~/.workbuddy/skills/synology-nas-cli/
sha256sum -c synology-nas-cli-vX.Y.Z.sha256
```

## 版本发布

- 日常改动照常 commit 到本地仓库。
- 主要版本由维护者手动审批发布：GitHub Actions → `CI` → **Run workflow** → 填 `vX.Y.Z`。
  自动打包 tar.gz + SHA256，发布到 Release。

## 检查更新

```bash
python3 scripts/check_update.py            # 有无更新 + 主要更新内容
python3 scripts/check_update.py --json     # 机器可读
python3 scripts/check_update.py --mark-seen   # 记录当前水位
```

- GitHub 更新地址：<https://github.com/J-5271/synology-nas-cli1>（Release 页可下载带 SHA256 的稳定包）
- **访问不了 GitHub？**看腾讯文档《synology-nas-cli 版本更新记录》：
  <https://docs.qq.com/aio/DQ05IdUxxR3ZtUndG> —— 同步记录当前版本与历史更新内容。
- 维护者每周检查一次；有更新会同步到该文档。

## 使用须知（安装后先看这个）

首次加载技能会自动输出「免责声明 + 两个收集表」；也可手动查看：

```bash
python3 scripts/first_run.py
```

## 反馈与回传

- 改进建议 / 问题：GitHub Issue 或 PR。
- **使用报告 / 更新收集**（实测记录、命令输出、改进建议）：
  <https://docs.qq.com/form/page/DQ2RsRGRjc3JnRHFi>
- **未解决问题 / 售前方案咨询**（卡住了、要方案、要选型建议）：
  <https://docs.qq.com/form/page/DQ1dTRXdjTUZ6SFR4>
- 两个均为腾讯文档收集表，**仅允许填写提交**，填写前请先脱敏。
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
| `scripts/first_run.py` | 打印使用须知（免责声明 + 两个收集表入口） |
| `scripts/syno.py` | FileStation 上传/下载/列目录（多文件、管道、不覆盖开关、失败不中断汇总） |
| `scripts/pack_skill.py` | 打包（full/delta）+ 凭据扫描，命中凭据 exit 4 |
| `scripts/cos_upload.py` | COS 上传（ima 回传第二步） |
| `scripts/check_update.py` | 检查 GitHub 是否有新版本（Release / tag / commit 三级 fallback） |
| `VERSION` | 本地版本基线 |
| `.update_state.json` | 更新检查水位（last_version / last_commit） |

## 版本与同步节奏

> **改动只在本地做，推送统一在每晚 22:00 自动执行**（GitHub + 腾讯文档一起同步）。
> 日常改完只需 `git commit`，不要顺手 `git push`。

- **每天 22:00**：把当天本地 commit 推到 GitHub，同步腾讯文档《版本更新记录》，并汇报当天主要更新内容。
- **每周日 21:30**：只检查远端有没有本地没有的改动（例如他人 PR 被合并），**不推送**。
- **每月**：`pack_skill.py --mode full` 打整包，REPLACE 覆盖 ima 主条目；git 打 tag `vYYYY.MM`。
- **ima 周增量**：`pack_skill.py --mode delta` 打增量，回传 ima「公用nas操作技能」。

## 红线

- 包内禁止真实账号 / 密码 / sid / 云密钥，示例一律占位符（`<账号>` / `<密码>` / `$ENV`）。
- 打包前跑凭据扫描，命中即中止（exit 4），不要用 `--allow-secrets`。
- 临时 COS 凭证用完即删，`*cred*.json` 已被 `.gitignore` 排除。

## 脚本退出码约定

| 码 | 含义 |
|---|---|
| 0 | 成功（`check_update.py` 为「有更新」） |
| 1 | 通用错误（部分文件失败、上传失败等） |
| 2 | 用法错误 / 守卫拦截（`nas_exec.py` 改配置未加 `--yes`） |
| 3 | 无变更（`pack_skill.py --mode delta` 无新增；`check_update.py` 无更新） |
| 4 | 安全类（`pack_skill.py` 脱敏扫描命中；`check_update.py` 查询失败） |

查当前版本：`python3 scripts/nas_exec.py --version`（`dsm_api.py` / `syno.py` 同样支持）。
