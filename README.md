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

## 这是什么（简要概述）

> **一句话**：一套把「群晖 NAS 日常运维」变成**命令行 + 有安全守卫**的技能包，
> 让 AI 助手（或你自己）能直接查状态、传文件、管共享文件夹，而**默认不改设备配置**。

Synology / 群晖 NAS 管理技能包。唯一真实来源是**本地 git 仓库**；
GitHub 公开仓库 <https://github.com/J-5271/synology-nas-cli1> 是**只读分发镜像**。

### 三条通路，按场景选

| 通路 | 脚本 | 前提 | 能干什么 | 典型场景 |
|---|---|---|---|---|
| **SSH + root** | `nas_exec.py` | DSM 开启 SSH，账号在 administrators 组 | 跑任意 DSM 命令、读 `/etc/VERSION`、用官方 CLI（synouser / synoshare / synonet…） | 巡检、批量改用户与共享、装 Docker |
| **DSM Web API** | `dsm_api.py` | **不用开 SSH**，能访问 DSM 网页即可 | 查系统信息、共享文件夹、用户、SSH 开关状态、探查 1600+ 注册 API | 客户环境不让开 SSH、只要读状态 |
| **FileStation 传输** | `syno.py` | 同上（Web API 通道） | 上传 / 下载 / 列目录，支持多文件与管道 | 传脚本、取日志、导备份 |

### 设计取舍（为什么值得用）

- **只读优先**：改配置的命令默认被守卫拦下（exit 2），必须用户明确确认后加 `--yes` 才执行。
  破坏性操作（`rm` / `mkfs` / `reboot` / 改网络）另有一层拦截。
- **凭据不落盘**：全部走环境变量（`NAS_*` / `DSM_*` / `SYNO_*`），脚本不写日志、不缓存。
- **零遥测**：没有任何出站上报，完全离线可用。
- **纯标准库**：除 SSH 密码登录需要 `paramiko` 外无第三方依赖；用 SSH key 连都不用装。
- **能自检更新**：`check_update.py` 对比 GitHub Release / tag / commit，访问不了 GitHub 有腾讯文档镜像。

### 不适合

- 想要一键图形化管理的（这是命令行/AI 驱动的工具包，不是控制面板替代品）
- 商用交付、付费服务、二次分发获利（**明确禁止**，见免责声明）
- 指望"照抄就能跑"：机型 / DSM 版本差异很大，全部命令请先 `--help` 或 `--dry-run` 核实

---

⚠️ 分发仓库是公开的：真实 IP、主机名、序列号、账号、客户名**一律不得入库**，一律占位符。
注意 git **历史**也会留痕——带敏感信息的旧 commit 需要重写（filter-repo），不是删文件就行。

## 安装

```bash
# 方式一：直接 clone（跟随最新提交）。目标目录随意，可放在任意位置（目录名任意）
git clone https://github.com/J-5271/synology-nas-cli1.git <任意目录>/synology-nas-cli

# 方式二：用 Release 里的稳定版（推荐）
# 下载 synology-nas-cli-vX.Y.Z.tar.gz + 同名 .sha256，校验后解压到
# <你放置技能包的目录>/synology-nas-cli/（目录名随意）
sha256sum -c synology-nas-cli-vX.Y.Z.sha256
```

## 使用说明（快速上手）

### 0. 准备（一次性）

```bash
pip install paramiko        # 仅 SSH「密码登录」需要；用 SSH key 或只走 Web API 可跳过
python3 scripts/first_run.py   # 先看使用须知（免责声明 + 两个收集表 + 更新入口）
```

技能包可放在用户级 `~/.workbuddy/skills/`、项目级 `<项目>/.workbuddy/skills/`，或任意目录；WorkBuddy 会自动识别前两者，放在别处时其它 agent 可用绝对路径直接调用脚本，脚本通过 `__file__` 自动定位自身，无需固定路径。

> **被其它 agent / 外部程序调用**：脚本靠 `__file__` 自定位根目录，不依赖 CWD 与固定安装路径。
> - 其它 agent 可用绝对路径直接调用 `scripts/*.py`（如 `python /opt/skills/synology-nas-cli/scripts/nas_exec.py --health`）。
> - 若脚本被复制到临时目录运行、无法靠 `__file__` 定位真实根目录，可设环境变量
>   `SYNO_SKILL_ROOT=/真实技能包目录` 重定向（用于读取 `VERSION` / `.update_state.json` / `references` 等）。
> - 凭据仍走环境变量（`SYNO_HOST` 等），不落盘。

### 1. 通路 A：SSH（能力最全）

DSM 侧：控制面板 → 终端机和 SNMP → 终端机 → 勾选「启用 SSH 服务」。
账号必须在 **administrators** 群组，否则 `sudo -i` 提不了权。

```bash
export NAS_HOST=<NAS的IP> NAS_USER=<管理员账号> NAS_PASS='<密码>' NAS_PORT=22

python3 scripts/nas_exec.py --health                  # ① 先跑只读探针，确认连通
python3 scripts/nas_exec.py "cat /etc/VERSION; df -h"  # ② 任意只读命令
python3 scripts/nas_exec.py --dry-run "<命令>"          # ③ 只想看会执行什么：不连设备、不过守卫
python3 scripts/nas_exec.py - <<'EOS'                  # ④ 多行脚本从 stdin 读，最保真
for t in synouser synoshare synonet; do
  /usr/syno/sbin/$t --help | head -20
done
EOS
```

**改配置会被拦**：`nas_exec.py "<改配置命令>"` 不加 `--yes` 直接返回 2 并提示，
不会连设备。确认无误后追加 `--yes` 才真正执行。

想免密登录：`python3 scripts/nas_exec.py --install-key --yes`（会改写 NAS 上的 `authorized_keys`，同样受守卫约束）。

### 2. 通路 B：DSM Web API（不用开 SSH）

```bash
export DSM_HOST="http://<nas>:5000" DSM_ACCOUNT=<账号> DSM_PASSWORD='<密码>'
export DSM_VERIFY_SSL=0        # 仅自签名证书时

python3 scripts/dsm_api.py info                        # 系统 + SSH 状态 + 共享文件夹
python3 scripts/dsm_api.py apis Share                  # 按关键字查注册了哪些 API
python3 scripts/dsm_api.py call SYNO.Core.Share list 1 only_visible=false
python3 scripts/dsm_api.py logout                      # 用完登出（sid 等同完整会话凭据）
```

HTTP 下密码明文上行，只在内网/可信链路用；能走 HTTPS（默认 5001）就走 HTTPS。

### 3. 通路 C：FileStation 文件传输

```bash
export SYNO_HOST="http://<nas>:5000" SYNO_USER=<账号> SYNO_PASS='<密码>'

python3 scripts/syno.py --list /volume1/video            # 列目录（只读）
python3 scripts/syno.py a.mp4 b.mp4 --remote /volume1/video   # 多文件上传
ls *.m4a | python3 scripts/syno.py --remote /volume1/audio    # 管道上传
python3 scripts/syno.py --download /volume1/video/a.mp4 --output-dir .  # 下载
python3 scripts/syno.py a.mp4 --no-overwrite --remote /x/y    # 不覆盖已存在文件
```

> 坑：`--list /` 根路径会返回 401，要用具体共享文件夹路径（`/volume1`、`/home`）。

### 4. 场景速查

| 我想… | 用什么 |
|---|---|
| 看这台 NAS 型号 / DSM 版本 / 磁盘 | `nas_exec.py --health` 或 `dsm_api.py info` |
| 不改任何东西，先看命令长什么样 | `nas_exec.py --dry-run "<命令>"` |
| 建用户 / 建共享文件夹 / 改权限 | `nas_exec.py "/usr/syno/sbin/synouser --add …" --yes`（守卫会先拦一次） |
| 查这台 DSM 支持哪些 API | `dsm_api.py apis <关键字>` |
| 传脚本到 NAS、取日志回来 | `syno.py` 上传 / 下载 |
| 看看有没有新版本 | `check_update.py` |
| 提交实测记录 / 求助 | 见下方「反馈与回传」两个收集表 |

### 5. 排错

- SSH 连不上 → 返回 255，检查：SSH 是否启用、端口、账号是否在 administrators 组
- `sudo -i` 提不了权 → `NAS_USER` 不是 root 且没设 `NAS_PASS`，或账号不在 administrators 组
- DSM 登录失败 → 脚本会按错误码给下一步建议（400 查凭据 / 401 账号被禁 / 403 锁定或 OTP）
- API 报 102 → API 名写错或该 DSM 没注册，不是权限问题，去 `dsm_api.py apis` 查注册表
- 命令报 `0x0300 ACCESS DENIED` → 没提权，见 `references/error-codes.md`

## 版本发布

- 日常改动照常 commit 到本地仓库。
- 发布时机由维护者掌握，二选一：
  ```bash
  git tag -a vX.Y.Z -m "发布说明" && git push origin vX.Y.Z   # 推标签即自动发布
  ```
  或 GitHub Actions → `CI` → **Run workflow** → 填 `vX.Y.Z`（手动审批）。
- 两种都会自动打包 tar.gz + SHA256 并发布到 Release。
- 本机装了 `gh` CLI 时（需先 `gh auth login`）也可手动查发布：
  `gh release view v1.0.0 -R J-5271/synology-nas-cli1`

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
| `scripts/check_ci.py` | 校验 `.github/workflows/*.yml` 可解析（需 PyYAML，未装则跳过） |
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
