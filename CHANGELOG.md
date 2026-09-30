# 版本记录（CHANGELOG）

> 规则：每周只回传「新增的能力」到 ima「公用nas操作技能」库（kb_id `7510180233248137`），
> 条目名《Synology NAS 管理技能包-增量-YYYY-MM-DD.md》；
> 每月做一次整合，重新打整包并 REPLACE 覆盖《Synology NAS 管理技能包.md》。
> 所有内容脱敏，不记录任何真实账号/密码/密钥。

## 2026-09-30 · 套件离线安装封装（install_packages.py）

- **新增 `scripts/install_packages.py`**：纯标准库，复用 `dsm_api.py` 的 DSM 传输层，
  把「套件离线安装 + 建共享文件夹 + 建子目录 + 配置日志归档」封装成可复用脚本。
  子命令：`status`（只读）/ `install` / `create-share` / `create-folder` /
  `set-log-archive` / `setup`（一条龙）。变更操作必须 `--yes` 才执行（只读优先红线）。
- **踩平三个实测坑并写进 `references/package-install.md`**：
  ① 本地 NAS 上传必须绕过本机代理（脚本自动把 `DSM_HOST` 加进 `NO_PROXY`，否则 `ProxyError 10054`）；
  ② FileStation 用「共享根路径」（`/nas管理`）而非磁盘路径（`/volume1/nas管理`），
     但安装套件时的 `path` 必须用磁盘绝对路径；
  ③ 日志归档 `SYNO.LogCenter.Setting.Storage set` 的布尔字段必须传 `true/false`（传 `1/0` 报 120）、且必须用 POST。
- **修正能力边界**：装套件已不必走浏览器——NAS 在线装因连不上 Synology CDN 报 `error 400`，
  改用本地 `.spk` 上传 + `SYNO.Core.Package.Installation`（复合 check+install，磁盘路径）即可；
  SKILL.md 浏览器自动化段落相应更新。建共享文件夹在部分机型仍可能 403，保留浏览器回退。
- **明确局限**：存储空间分析器（StorageAnalyzer）「每周报表」无 Web API（全量 API 注册表无
  StorageAnalyzer 条目），只能进套件 UI 手动建计划，文档已写清手动步骤。
- `VERSION` → `1.0.2`。

## 2026-09-30 · v2026-09-30

- **新增通路：局域网发现**（`references/lan-discovery.md`）
  - `scripts/syno_findhost.py`：Synology Assistant 同款 findhostd 协议客户端（只读）。
    能拿型号 / 序列号 / DSM build / 架构 / MAC / **自定义 HTTP 与 HTTPS 端口**。
    记录完整协议规格（MAGIC + TLV、端口 9997-9999、字段表）与头号坑：
    **套接字必须 bind 在 UDP 9999**，绑临时端口 100% 收不到回应。
  - `scripts/discover_nas.py`：mDNS + SSDP + HTTP 指纹三通道发现，
    **TCP 端口探测默认关闭**（`--portscan` 才开），符合「不主动做端口扫描」红线。
  - 实测结论：两条互补，单用都会漏设备（自定义端口 888/889 的机器端口扫描全漏、
    findhostd 一次命中；没装 DSM 的裸机只回应 SSDP、findhostd 不理）。
- **新增通路：浏览器自动化**（`references/browser-automation.md`）
  - Web API 干不了的四件事：装 DSM（Web Assistant）、装套件
    （`Package.Installation.install` 实测返回 103）、建共享文件夹（`Share.create` 返回 403）、
    绕过磁盘兼容性检查（`Volume.create` 加 `force:true`）。
  - 核心姿势：在已登录页面上下文里 `eval` 调 `SYNO.API.Request`，不用自己管 sid / token。
    **头号坑：`callback` 第一个参数是布尔 success，数据在第二参。**
  - 记录 DSM 7.4 上建 btrfs 卷 + 快照计划的真实 API 契约：
    `Share.Snapshot set_schedule`（date_type/repeat_hour/hour/week_name）与
    `DisasterRecovery.Retention set`（`policyType` 位掩码常量表：`RTT_DEL_OLD=20` /
    `RTT_BY_DAY=64` / `RTT_BY_ADVANCE=128` 等），并区分「保留 N 天」与「保留 N 份」。
  - 安全：浏览器会话等同完整凭据，收尾必须 `agent-browser close`；sid / token 禁止落盘。
- README / SKILL.md：通路表由三条扩到五条，新增对应快速上手与排错条目。

## 2026-09-30 · 官方部署指南要点入库

- 新增 `references/dsm-deployment-guide.md`：提炼自官方《Synology NAS 部署指南》
  （DSM 6.2，99 页 PDF）。**只重述事实性/可操作知识并附官方链接，未复制原文**——
  官方法律声明禁止未经书面许可摘抄复制。
  - 11 步部署顺序 checklist（帐户 → 硬件 → 装 DSM → 网络 → 存储 → 账号 →
    共享文件夹 → 协议 → 日志 → 安全加固）
  - 选型表：RAID（≦5→RAID5 / ≧6→RAID6 / 无人值守→RAID6+热备）、
    存储池类型、Btrfs vs Ext4、iSCSI Thick/Thin
  - 硬约束：共享文件夹命名规则与保留名、ACL 200 条上限、加密文件夹的密钥陷阱、
    M.2 只能做缓存不能建池、SSD 缓存必须同设备、Hot Spare 三条件、
    链路聚合必须先于 HA、MTU 需全网一致
  - 安全加固 10 项清单（更新策略、邮件通知、IP 封锁、账户保护、防火墙、
    停用 admin/guest、密码强度、2 步验证、改默认端口、安全顾问定期扫描）
  - DSM 6.2 → DSM 7 入口对照表（用户帐号→用户和群组、存储空间管理员→存储管理器、
    iSCSI Manager→SAN Manager 等）
- SKILL.md 新增「新机开荒：部署顺序与选型要点」速查表；README 目录与场景速查同步。

## 2026-09-28 · v2026-09-28

- 新增「脱敏规范（强制）」：包内禁止出现真实账号、密码、密钥；示例一律占位符。
  `pack_skill.py` 内置凭据扫描，命中即中止打包（exit 4）。
- 新增版本化回传：`pack_skill.py` 支持 `--mode full|delta`，
  产物头部带版本日期与生成时刻；`build/.sync_state.json` 记录上次同步时间。
- 新增「只回传新增能力」：`--mode delta --since <日期>` 只打包变更文件，
  无变更时返回 exit 3 跳过回传。
- 回传目标库改为 ima「公用nas操作技能」kb_id `7510180233248137`（原开发库 7506185150271226 保留为素材源）。
- 自动化：周度改为「周增量回传」（automation-1790221817758）；新增月度整合提醒
  （automation-1790567281158，每月 1 日 21:00 打整包覆盖主条目）。

## 2026-09-28 · 分发与安全策略更新

- **公开分发**：GitHub 公开仓库 https://github.com/J-5271/synology-nas-cli1 作为分发主渠道，
  他人可 clone 或下载 Release 的 `.tar.gz`；本地 git 仍是唯一真实来源。
- **版本与发布**：采用语义化版本 tag；CI 负责构建，**主要版本由维护者手动 workflow_dispatch 审批发布**。
- **新增「安全与隐私」章节**：明确无自动遥测、无出站上报、支持完全离线使用、
  第三方 Actions 固定 SHA、Release 附校验和。
- **新增使用报告回传入口**：Synology 文件请求链接（目标目录 `docker/gitea/回传`），
  由使用者主动上传实测记录/改进建议，不做自动收集。
- 实测补充（DS423+ / DSM 7.2.1）：后台任务需用用户身份 `nohup`（`sudo -i sh -c` 起的会被杀）；
  国内网络 Docker Hub 不通，走 `docker.m.daocloud.io`；BusyBox `ps` 要加 `w`。
- 实测补充：Git Bash 调 DSM API 传 `/xxx` 路径会被转成 Windows 路径，需 `export MSYS_NO_PATHCONV=1`。

## 2026-09-28 · 免责声明与仓库更名

- 新增**免责声明**（README.md / SKILL.md 顶部）：个人收集整理、仅供学习交流、
  **禁止商用开发**、无担保、风险自负。
- 公开分发仓库更名为 https://github.com/J-5271/synology-nas-cli1 （原 synology-nas-cli 弃用）。

## 2026-09-28 · 回传方式改为腾讯文档表格

- 回传入口由「NAS 文件请求链接」改为**腾讯文档在线表格（收集表模式，仅允许他人填写提交、不可查看他人记录）**，
  避免公开仓库暴露 NAS 的 QuickConnect ID 与上传入口。
- SKILL.md / README.md 同步更新回传说明与建议表头；链接待创建后填入。

## 2026-09-28 · 新增文件传输脚本 syno.py

- 参考 robinFdr/synology-nas-cli，新增 `scripts/syno.py`：FileStation 上传/下载/列目录，
  支持多文件、stdin 管道、`--no-overwrite`、`--output-dir`、`--no-verify-ssl`；
  纯标准库实现，凭据走 `SYNO_HOST/SYNO_USER/SYNO_PASS`，只做文件传输不碰配置。
- 实测（DS423+ / DSM 7.2.1）：`--list` 列目录通过；`folder_path=/` 返回 401，
  需用具体共享文件夹路径（如 `/home`）。

## 2026-09-28 · 回传表格权限设置说明

- SKILL.md「使用报告回传入口」补充腾讯文档**仅填写**权限的三步设置：
  ① 收集表模式（关闭"允许修改/查看全部记录"）② 列级「填写内容隐藏」③ 锁定表头区域。
- 明确：分享权限选「可编辑」不等于仅填写，必须走收集表模式。

## 2026-09-28 · 回传地址确定

- 回传入口正式启用腾讯文档收集表「nascli更新收集」：
  https://docs.qq.com/form/page/DQ2RsRGRjc3JnRHFi （仅允许填写提交）
  SKILL.md / README.md 已填入该地址，占位符移除。

## 2026-09-29 · 新增第二个收集表 + 首次加载弹须知

- 新增第二个回收入口「未解决问题 / 售前方案咨询」：
  https://docs.qq.com/form/page/DQ1dTRXdjTUZ6SFR4
  与「nascli更新收集」(DQ2RsRGRjc3JnRHFi) 并列，SKILL.md 明确两者分流口径。
- 新增 `scripts/first_run.py`：打印「免责声明 + 两个收集表」，纯输出无副作用。
- SKILL.md 顶部新增「首次加载必弹」区块：每次触发技能先把该段原样输出给用户，再执行任务。

## 2026-09-29 · 更新检查机制（GitHub + 腾讯文档镜像）

- 新增 `scripts/check_update.py`：纯标准库，只访问 `api.github.com` 公开只读接口，
  按「Release → tag → main HEAD」三级 fallback 判断远端最新版本；
  支持 `--json`（自动化消费）、`--mark-seen`（写水位）、`--set-version`（改基线）。
  退出码：`0` 有更新 / `3` 无更新 / `4` 查询失败（打印腾讯文档镜像地址兜底）。
- 新增 `VERSION`（当前 `1.0.0`）与 `.update_state.json`（last_version / last_commit / last_checked）。
- SKILL.md 新增「更新检查（每周一次）」章节：记录 GitHub 更新地址
  （https://github.com/J-5271/synology-nas-cli1）与流程；README 同步加「检查更新」段。
- 新增腾讯文档《synology-nas-cli 版本更新记录》：https://docs.qq.com/aio/DQ05IdUxxR3ZtUndG
  （file_id `CNHuLqGvmRwF`），作为**无法访问 GitHub 用户**的版本镜像，
  记录当前版本、更新地址、更新方式、版本记录表、免责声明与两个收集表。
- 约定：每周检查一次；有更新则同步该文档 + 追加本文件 + 向用户输出主要更新内容。

## 2026-09-29 · 同步节奏改为「本地优先 + 每晚统一推送」

- 规则变更：日常改动**只在本地 commit**，不在当次对话里 push；
  推送统一由每晚 22:00 自动化完成（GitHub + 腾讯文档一起同步）。
  例外：用户明确要求「现在推」才手动 push。
- 新增自动化「NAS 技能包每晚推送同步」（`39b991d0-dc49-489e-9a1f-6a1eaf4c4fba`，每天 22:00）：
  提交残留改动 → `git push origin main`（有 tag 再 `--tags`）→ 更新腾讯文档版本记录的
  「发布日期 / 对应提交」并在版本记录表追加一行 → `--mark-seen` → 向用户汇报当天主要更新内容。
  无待推 commit 时跳过，不空跑。
- 调整原周检查自动化（`b3bbeb4b-1351-4127-ac0f-1532f712feef`）为**只查不推**：
  发现远端有本地没有的改动时先 `git fetch` + 列差异，合并需先问用户，不擅自 pull。
- SKILL.md「更新检查」章节重写为「更新与同步节奏：本地优先 + 每晚统一推送」，
  含五阶段表（改 / 存 / 推 / 宣 / 查）；README「版本与同步节奏」同步更新。

## 2026-09-29 · PM 评审与全量代码优化

- **修复** `pack_skill.py` 打包清单漏文件：`DOC_ORDER` 补 README / VERSION / requirements.txt /
  syno.py / check_update.py / first_run.py，回传 ima 的包现在含全部 16 个文件。
- **修复** `syno.py` 下载不校验 API 错误响应：文件不存在时会把 JSON 错误写进下载文件；
  现在检测 Content-Type 为 application/json 即抛错，不再产出伪文件。
- **优化** `syno.py`：多文件上传/下载改为单文件失败不中断、结束统一汇总（exit 1）；
  >512MB 文件上传前警告内存占用；docstring 里 `--out` 改为正确的 `--output-dir`。
- **优化** `dsm_api.py`：登录改 POST 优先（密码不进 URL / 访问日志），POST 不通回退 GET；
  登录失败按错误码给出下一步建议（400/401/403/105/117/102/103）。
- **新增** 各脚本 `--version`：nas_exec / dsm_api / syno / check_update 统一输出 `v<VERSION>`。
- **修复** `nas_exec.py --dry-run` 未设 NAS_HOST 直接报错：dry-run 不连设备，不再强制要求 host。
- **优化** `first_run.py`：弹窗新增「版本与更新」段（GitHub Release + 腾讯文档镜像 +
  check_update 用法），末尾打印当前版本；SKILL.md 必弹区块同步。
- **修复** 文档错误：SKILL.md 下载示例 `--out` → `--output-dir`；
  README 目录表 syno.py 去掉未实现的「进度」字样。
- **修复** CI：Release 打包排除个人水位文件 `.update_state.json`。
- **新增** README「脚本退出码约定」表（0/1/2/3/4 含义统一成文）。

## 2026-09-29 · v1.0.0 首个 Release（标签触发发布）

- `.github/workflows/ci.yml` 发布触发增加**标签方式**：`push.tags: ["v*"]`，
  release job 条件改为 `workflow_dispatch || startsWith(github.ref,'refs/tags/v')`；
  新增「解析版本号」步骤：手动触发取 inputs.version，标签触发取 `GITHUB_REF_NAME`。
  原「手动审批发布」路径保留，两条都可走。
- 打标签 `v1.0.0` 并推送 → CI 自动打包 tar.gz + SHA256 发布到 Release。
- SKILL.md「分发与版本策略」与 README「版本发布」同步更新为两种发布方式。

## 2026-09-29 · v1.0.0 发布实修（两个 CI 坑）

- 坑① `tar czf out.tar.gz .` 在工作区内打包自身 → tar exit 1，首次标签发布失败。
  改为产物写 `$RUNNER_TEMP`，`tar czf ... -C "$GITHUB_WORKSPACE" .`。
- 坑② `--notes` 里写了空行 → workflow YAML 解析失败，GitHub 只给一个
  **conclusion=failure 且 jobs 数为 0** 的 run（看上去像 CI 挂了，实际文件没被解析）。
  已改为单行 notes。
- 新增 `scripts/check_ci.py`：本地/ CI 解析 `.github/workflows/*.yml`（依赖 PyYAML，
  未装则跳过），把这类问题挡在提交前；CI verify 增加该步骤；CONTRIBUTING 提交前必做同步。

- **v1.0.0 已发布**：tag `v1.0.0`（commit `b3f88f9`），Release 含
  `synology-nas-cli-v1.0.0.tar.gz`（57,965 B）与同名 `.sha256`，已下载校验一致。

## 2026-09-29 · README 补「简要概述 + 使用说明」

- README 新增「这是什么（简要概述）」：一句话定位、三条通路对照表（SSH / DSM Web API /
  FileStation 各自前提与典型场景）、五条设计取舍（只读优先、凭据不落盘、零遥测、
  纯标准库、可自检更新）、以及「不适合」清单（含禁止商用）。
- README 新增「使用说明（快速上手）」：0 准备 → 1 SSH 通路 → 2 Web API 通路 →
  3 FileStation 传输 → 4 场景速查表 → 5 排错（255 / sudo 提权 / 登录错误码 / API 102 /
  0x0300），全部示例用占位符。
- SKILL.md 顶部加指引：新用户先看 README 的概述与快速上手，本文件为完整参考。

## 2026-09-29 · v1.0.1 发布（把 README 概述/使用说明纳入 Release 包）

- 仅文档性发布：`VERSION` → `1.0.1`；把 v1.0.0 之后 main 上新增的
  README「简要概述 + 使用说明」一并纳入下载包。
- 打标签 `v1.0.1` 并推送 → CI 自动打包 tar.gz + SHA256 发布到 Release。
- 腾讯文档《版本更新记录》同步当前版本为 v1.0.1，版本记录表追加一行。

## 2026-09-29 · 路径无关 + 与其它 agent 兼容优化

- 7 个脚本（check_ci / check_update / dsm_api / first_run / nas_exec / pack_skill / syno）
  的 `SKILL_ROOT` 解析增加 `SYNO_SKILL_ROOT` 环境变量覆盖，`__file__` 两层父目录兜底；
  技能包放在任意目录、被其它 agent 以绝对路径直接调用脚本均可用，不依赖固定安装路径。
- `pack_skill.py` 生成内容里去掉写死的 `~/.workbuddy/skills/synology-nas-cli/`，改用 `SKILL_ROOT` 变量。
- README / SKILL.md / CONTRIBUTING 删除"必须放在固定目录"的强制说法，改为
  "目录名随意 / 任意位置"；README 新增「被其它 agent 调用」说明
 （`__file__` 自定位、临时目录运行时设 `SYNO_SKILL_ROOT` 重定向、凭据走环境变量不落盘）。
- ci.yml release `--notes` 安装建议改为"解压到任意目录"。
- 未改动 CI 结构与脱敏扫描；`py_compile` / `pack_skill --no-state`（脱敏 exit 0）/
  `nas_exec --dry-run` 均通过验收。

## 2026-09-27 · v2026-09-27

- 新增「细粒度权限：synoshare 做不到」：ACL 删除位 D/DC 拆分、两条规则、
  CREATOR OWNER、系统共享文件夹不支持 Windows ACL、ACL 上限 200、权限检查器验证。
- 新增「技能包维护与 ima 同步」：三步回传流程、bucket appid 坑、
  403 InvalidAccessKeyId 处置（重取凭证）。
- `pack_skill.py` 打包含自身与 `cos_upload.py`；`cos_upload.py` 支持多 host 回退 + URLError 捕获。
- cli-commands.md 补 synoshare 权限粒度注解；三份 references 补维护记录。
- 实测设备档案：本周无新增实测设备（DS918+ / DSM 7.3-81180 不变）。
