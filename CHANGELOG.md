# 版本记录（CHANGELOG）

> **已于 2026-11-01 并入整包 v2026.10**（2026-10 全部周增量已合并进主干，本地 tag `v2026.10`）
>
> 上一轮整包：**2026-10-02 并入 v2026.09**（2026-09 全部周增量已合并进主干，本地 tag `v2026.09`）

## 2026-11-11 · 安装约束补记：Skill 包只支持两级目录

纯文档 + 打包方式修正，技能内容无改动（仍为 v1.6.0）。

- **背景**：安装/加载时报「目录层级超限 — Skill 包仅支持两级目录结构（根目录/二级目录/文件）」。
  根因是仓库里有三类**三级**路径混进了安装目录：
  | 路径 | 层级 | 性质 | 处理 |
  |---|---|---|---|
  | `scripts/__pycache__/*.pyc` | 根/scripts/__pycache__/文件 | Python 自动生成的字节码 | 删除；运行脚本时会再生成，建议 `PYTHONDONTWRITEBYTECODE=1` |
  | `build/delta/*.md` | 根/build/delta/文件 | 增量聚合产物（2026-10-04 的旧包） | 移出仓库 |
  | `.github/workflows/ci.yml` | 根/.github/workflows/文件 | GitHub CI 配置，**不属于技能内容** | 见下 |
- **`.github` 的处理**：GitHub Actions 要求工作流必须在 `.github/workflows/`，没法拍平。
  因此采取「仓库 ≠ 安装包」：CI 打包时本来就带 `--exclude='.git*'`（连 `.github` 一起排掉），
  Release 里的 tar.gz 天然合规（已实测：0 个三级条目、无 `.github`）。
  `README.md` 的「安装」一节点名了三件事——clone 后要 `rm -rf .github`、手工打 zip 要
  `git archive … ':(exclude).github'`、`build/delta` 与 `__pycache__` 不要打进包。
- 合规包现有结构只有 `references/*.md` 与 `scripts/*` 两类二级目录，共 48 个文件条目。

## 2026-11-09 · v1.6.0 生态项目索引与能力边界

把「要不要把一堆群晖开源项目整合成一个专家」这个问题沉淀成了一份可复用的决策文档，
并顺带把 10 个社区项目**重新抓了一遍真实数据**。代码无改动。

- **新增 `references/ecosystem-boundaries.md`** —— 三层内容：
  1. **四层架构**（核心 Skill / 项目知识库 / 推荐路由 / 可选执行器），说明「专家」应该是编排层，
     不是把 arc、NVMe 解锁、Docker 模板、spksrc 一股脑打进来的大杂烩；
  2. **能力边界表**：明确划出去的四类（引导器、NVMe 建池、套件迁移、SPK 编译、Docker 模板、
     内网穿透），以及为什么不做——改引导介质或分区表，失败即开不了机或丢池，与本包
     「管理已装好的 NAS」定位正交；
  3. **实测项目索引**：10 个项目带当天星标 / 语言 / 许可证 / 最近提交 / 风险分级。
- **纠了三处流传的数字**（这类错误会直接进方案，危险性不比技术坑小）：
  - `RROrg/rr` 实测 **8,764** 星，是 `AuxXxilium/arc`（3,571）的 **2.4 倍**；
    很多清单只提 arc「约 3.4k」，容易让人误判社区主流。
  - `erwinkramer/synology-nas-bootstrapper` 只有 **18 星**，却被列进「高星项目」并列 3k+ 的项目；
    实测最近提交 1.7 个月前，许可证 `NOASSERTION`。
  - `SynoCommunity/spksrc` 与上面那个 bootstrapper 的 GitHub 许可证字段都是 `NOASSERTION`
    （仓库里没有标准 LICENSE 文件），**不能当依赖用**。
  - 根因是那些清单引的是第三方聚合站（ecosyste.ms / git-stars / relatedrepos）的二手数据，
    星标与许可证都会滞后或标错。结论写进文档：**要写进方案的数字，自己抓一遍。**
- **给了一张自检门槛**：核心能力已在 10–20 个高频场景稳定、有推荐库与风险分级、
  能区分「只回答」和「可执行」、有版本兼容表与回归测试、第三方只索引不内嵌——五条缺一条先别做专家。
- **顺带把本包自己的 7 项优化清单对了一遍**（版本探测 / 安全模型 / 诊断树 / 推荐表 / 审计日志 /
  测试矩阵 / 文档免责），指出下一步最该补的是「诊断总入口」和「测试矩阵」，
  而「审计日志」要先在「不落盘」与「可审计」之间定原则。
- 版本号 `1.5.0` → `1.6.0`。

## 2026-11-09 · v1.5.0 第三方硬盘兼容性 + 简介收口

一次「补能力 + 减冗余」的版本，代码无改动。

- **新增 `references/drive-compatibility.md`** —— 群晖「硬盘未验证」怎么办。
  素材是 `007revad/Synology_HDD_db` v3.6.131 源码逐行通读 + 一份 DSM 7.4 实操记录。
  **本篇不是纯实测，已在文首标注**：脚本行为、库路径、参数开关均对源码核对（带行号），
  但未在真机执行，落地前先在测试机跑一遍。
  - **两条路径必须分清**，这是最容易混的地方：`synosetkeyvalue … support_disk_compatibility no`
    只是让 DSM **不检查**，盘仍是未验证状态（NVMe 建卷依旧受限）；`syno_hdd_db.sh` 改
    `/var/lib/disk-compatibility/*_host.db`、标成 `compatibility: support` 才是让 DSM **认**。
    25 系列（DS925+/DS1825+）新机首次装机要**先用前者打通安装、再用后者补库**，顺序不能反。
  - **源码级坑：`-f` 是双向开关**（`syno_hdd_db.sh` 第 2216–2240 行）。带 `-f` 写 `no`，
    **不带 `-f` 会主动把 `support_disk_compatibility` 写回 `yes`**。所以「首次手动 `-fr`、
    开机任务写 `-nr`」这个流行组合，第二次运行就把关掉的检查重新打开了——
    盘已入库时无害，但会让人误以为「不开 `-f` 也能保持免检查」。反过来，开机任务长期带 `-f`
    等于永久放弃数据去重与群晖盘固件升级（README 原文有写，但没人注意）。
  - 另三个坑：脚本**只写 `/etc.defaults/synoinfo.conf`**（手动法要写两个文件，一个管重启后、
    一个管当前会话）；`synosetkeyvalue` 三个参数容易被粘成两段（`…compatibilityno`），
    要用 `synogetkeyvalue` 回读确认；脚本**不能放 M.2 卷**，DSM 升级后 M.2 卷在脚本运行前不可用，
    开机任务会静默失败。
  - 官方口径也收进来了：DSM 7.3 已解除 2025 Plus 机型在 7.2.2 下的大部分限制，只留两条
    （第三方 NVMe 不能建缓存/卷、未验证盘仍大量告警），两条都能被本方案解决。
    附 7.2.2 装机阶段的 `start_telnet.cgi` + `touch /tmp/installable_check_pass` 绕过法，
    并注明「非官方支持路径」。
  - 供应链信息带版本闸门：核对时上游最新 release 为 **v3.6.139**（2026-08-30），
    而流传的中文教程多用 v3.6.131，落后 8 个版本——取用前先看 release 页。
- **三处简介收口**（纯文字，功能不变）：
  - `SKILL.md` frontmatter 的 `description` / `description_zh` / `description_en` 三段原有大量重复罗列，
    压成中等长度，保留全部触发关键词（群晖 / Synology / NAS / DSM / NFS / synouser / synoshare / dsm_api）。
  - `README.md`「这是什么」：几句话 + 一张六通路表 + 一行专项清单，去掉第二张五行的表；
    「两条写操作能力」的警告扩为「升级 / 批量整理 / 硬盘兼容性」三条。
  - GitHub 仓库 About 补一句话简介（此前为空）。
- 版本号 `1.4.1` → `1.5.0`（`VERSION`、`SKILL.md` 两处引用同步）。

## 2026-11-03 · v1.4.1 h265 流水线补坑：双机分工 + 看门狗复活记录

纯文档补丁，都在 `references/h265-transcode-pipeline.md`，代码无改动。

- **新增坑 9「两台机器一起压同一批片，怎么分工不打架」**。NAS 单线程约 2 小时/条，
  几百条排下来一个多月；让本机分担时**不能两家都从清单头开始**。
  可行解是**双指针**：NAS 顺序正序、本机把剩余清单倒序后从尾部往前，两边对着走。
  前提是队列脚本自带三条自跳过（源已不在 / 已有成品 / 本机见到同名 hevc `.mkv` 直接返回），
  再加一条保险——生成「本机可接清单」时把 NAS 正在写的 `*.hevc.mkv` 临时文件也排掉，
  连正在编的那一部都不会被抢。
  附带一个隐蔽坑：清单排序写 `{p: i for i, p in enumerate(set(paths))}`，
  **set 遍历顺序随机，等于没排序**，倒序意图会完全失效；要按文件行序建索引。
- **坑 8 补 2026-11-03 复发记录**。此前结论是「`DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`
  能脱离进程组」——当天第二次重启看门狗时证伪：批次与两个 ffmpeg 仍一起消失，
  留下 2.0 GB + 1.6 GB 两个 `*.hevc.qsv-tmp.mkv` 半成品。根因是受管终端把整棵进程树放进
  **Windows Job 对象**，`DETACHED_PROCESS` 只脱控制台/进程组，**脱不出 Job**。
  改写为三步可靠做法：①批次在跑就别动看门狗；②非要重启就等当前批次自然结束；
  ③真被中断只做两件事——扫 `*.hevc.qsv-tmp.mkv` 搬进暂存区、跑一次台账对账。
  想彻底免疫得换父进程（`schtasks` / `wmic process call create`），别让批次挂在看门狗下面。
- 全包文案同步为「九个必踩的坑」（`README.md` 两处、参考文档标题）。

## 2026-11-03 · v1.4.0 媒体服务：Peach 部署 + h265 批量转码流水线

一次把「NAS 上看片」和「NAS / 本机压片」两条链路补齐。**两条链路互不相干**：
Peach 的硬件转码是给播放用的实时 H.264/VAAPI，h265 流水线是批量离线重编码，参数不可混用。

- **新增 `references/peach-deploy.md`** —— Peach（`peach-mitao/peach`，AGPL-3.0）Docker 部署运维参考。
  以 DS423+ / DSM 7.4.1-90080 update1 实机 + 官方 `docs/DOCKER.md` 为准：
  - **五个坑**：①Docker Hub 上**没有 `latest` 标签**，只有版本号（`0.50.0`）与 `edge`，
    照教程写 `:latest` 必然 `manifest unknown`；②镜像**固定以 UID/GID 1000 运行**，
    群晖默认没有 uid 1000 账号，必须 `--user <uid>:<gid>` 覆盖；③媒体目录经 ACL 控制时
    要确认容器 uid 真有读权限；④**不要把整块共享根挂进 `/media`**（扫描器会去啃非媒体文件）；
    ⑤`/data` 必须是持久卷，否则重建容器丢库。
  - **国内拉不到镜像的根因不是「镜像不存在」**：`nslookup hub.docker.com` 回到 `31.13.x.x`
    （Meta 段）即 DNS 被投毒，`registry-1.docker.io:443` 直连超时。实测可用源
    `docker.1ms.run` / `docker.xuanyuan.me` / `docker.m.daocloud.io`；
    daocloud 有仓库白名单（未收录报 `not in allowlist`），xuanyuan 免费节点会 `403 TOOMANYREQUESTS` 需重试。
    **v2 接口返回 `401 UNAUTHORIZED` 是正常鉴权挑战，不代表 tag 不存在**——判断 tag 只能真拉一次。
  - 路径三层概念表（宿主机目录 / 容器内目录 / 数据库路径前缀）、与转码流水线对接的三条硬约定、
    排错速查（`/healthz?ready=1`、`peach token`、诊断包导出）、备份与卸载。
- **新增 `references/h265-transcode-pipeline.md`** —— h265 批量转码流水线全流程。
  以 DS423+（Celeron J4125 / UHD 600）+ Windows 本机实测为准：
  - **编码器选型实测**（同段 1080p）：`libx265 -crf 26` = 2481 kb/s / SSIM 0.9709 / **3.97 fps**；
    `hevc_qsv -global_quality 26` = 2536 kb/s / SSIM 0.9684 / **81 fps**。
    结论：**QSV 的 Q 值 ≠ x265 的 CRF，必须实测对齐**；Q21 体积翻 2.2 倍而画质看不出来。
  - **分工原则**：本机跑 ≥6 Mbps 的高码率片（CPU 强、可并行 2–3 路），NAS 只啃 2–6 Mbps 的
    （J4125 4 核，QSV 快但并行多了会互相拖），<2 Mbps 直接跳过（压完反而更大）。
  - **三段校验**（缺一不可）：时长 ±1%、分辨率完全一致、体积必须变小且 > 源的 2%。
  - **八个必踩的坑**（v1.4.1 又补了第 9 条），每条都带症状与修法：
    ① ffmpeg 吞 stdin → 队列每轮只跑 1 条（解：列表走 fd 3 + `-nostdin`）；
    ② 没有「体积不能变大」保护 → 出现 12.71 → 16.85 GB；
    ③ `docker top` 显示宿主 PID、容器内 `/proc` 是容器 PID，混用会判断错位；
    ④ 容器内没有 `ps`/`pkill`/`kill`（扫 `/proc/*/cmdline`，宿主侧 kill）；
    ⑤ 覆盖正在运行的 bash 脚本会读到错位字节（先 kill 再改）；
    ⑥ **删除原片被静默拦截**（SMB 盘上回收站重定向必失败且 fail-closed、批量配额用完后静默跳过）
    → 改同卷 `os.replace()` 搬进暂存区 + 搬完 `exists()` 复核；
    ⑦ 批次异常退出导致台账不回写（台账要以磁盘为准对账）；
    ⑧ 重启看门狗会连坐正在跑的批次（`DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`）。
- **新增 `scripts/peach_deploy.sh`** —— 一键部署。参数 `--media --data --uid --gid --port --image --name`；
  起容器前先做四道前置检查（媒体目录存在 / docker 可用 / 容器名不冲突 / 端口未占用），
  镜像缺失时先直连再按可用镜像源轮询，最后 `setpriv` 以目标 uid 自检媒体目录读权限，
  起完自动 `peach token` 取登录口令。
- **新增 `scripts/peach_pull.sh`** —— 国内环境可续传拉镜像。先做连通性自检把  「被墙 / DNS 投毒」和「镜像不存在」分开，再按 源 × 轮次 重试；**只以「镜像是否真的落地」
  判成功，不按日志大小判停滞**（非 TTY 下 `docker pull` 只在状态变化时输出，
  大层下载期间几分钟不吭声是正常的——按日志判停滞并把进程杀掉，会永远拉不完）。
  附 DSM 特有坑：**没有 `pgrep`（只有 `pkill`）**，用它写守护会 `command not found` 返回非 0，
  被判成「进程已退出」，短时间内并发十几个 `docker pull` 互相拖死。
- **新增 `scripts/h265_queue.sh`** —— NAS 容器内队列脚本（通用版）：`flock` 串行防双写、
  列表走 fd 3、三级编码兜底（`copy` → `aac 384k` → 去字幕）、三段校验、过小 / 反而变大保护、
  原片搬进暂存区。
- **新增 `scripts/h265_qsv_transcode.py`** —— 本机并行转码（参数化版）：`class Coder` 封装
  `probe` / `encode` / `verify` / `stage_original` / `discard` / `handle`；
  支持 `--root --csv --stage --bindir --q --workers --limit --min-bitrate --max-bitrate --list --dry-run`；
  逐条结果写 `results/h265_progress.jsonl`。
- **新增 `scripts/h265_ledger_check.py`** —— 以磁盘实况为准对账 CSV 台账，
  分「已转码 / 源文件缺失」两类回写，写前自动 `.bak`。
- **`SKILL.md`**：新增「专项参考：媒体服务与转码」一节（两张参考 + 三个脚本的索引，
  外加四条最值钱的结论）；**`README.md`**：索引表与「我想…」决策表各补三行；`VERSION` → `1.4.0`。
- **实机验收补丁（同日，DS423+ / DSM 7.4.1-90080 上跑通后回写）**：
  - **`--user` 之外必须 `--group-add 101`。** DSM 共享文件夹 ACL 基本只授权
    `group:administrators`（GID 101），而容器**不继承**宿主机账号的属组。
    只写 `--user 1026:100` 时：容器 `Up (healthy)`、`/healthz?ready=1` 返回 200，
    但容器内 `ls /media` 是 `Permission denied` —— 典型的「看着部署成功、实际一个字都读不到」。
    加上 `--group-add 101` 后同一命令输出 1118 个条目。
  - **DSM 没有 `setpriv`**，起容器前无法「以目标 uid 试读」；`peach_deploy.sh` 的自检
    因此改成「先起容器 → `docker exec -u <uid>:<gid> ls /media` 实测」，
    并把 `--group-add` 做成参数（默认 101）。
  - 镜像 `longmeidao/peach:0.50.0`（1.18 GB）经 `docker.1ms.run` 拉取成功；
    首次启动自动应用 49 个数据库迁移，`peach token` 正常出口令。
  - **`peach-deploy.md` 新增第七节「没有浏览器时怎么配置（API 实做）」**：登录拿
    `peach_session`、用 `revision`（config.toml 的 sha256）防并发改、`media_sources`
    加媒体库、`/api/configuration/access` 设密码的完整 curl 流程，外加六个坑
    （revision 有两个别混、必须带 `Origin` 且从本机发、**设密码后 auth-token 立即失效**、
    改配置 ≠ 有内容还得扫描、大库别在转码高峰扫）。

## 2026-10-24 · v1.3.0 DSM 升级 + 套件升级 + 批量文件整理

> 素材来源：一次完整的「DSM 跨大版本升级（7.2.1-69057 U13 → 7.4.1-90080 U1）
> + 套件批量升级 + 数万文件批量改名归集」实战。
> 本次为**纯新增能力**（新增 2 篇 references + SKILL.md 扩充），语义化 minor。
> 相对已发布的 v1.2.0 属新增能力，版本 1.2.0 → **1.3.0**。

- **新增 `references/dsm-upgrade.md`** —— DSM 固件升级 + 套件批量升级全流程：
  - **头号结论：官方升级包直链在官网前端不暴露**，自己拼的 URL 全 404。
    唯一可靠入口是让 DSM 自己下：`SYNO.Core.Upgrade.Server.Download.start`
    （**空参数**，传多余参数报 error 101），落到 `/volume1/@autoupdate/`。
  - **`synoupgrade --patch` 是陷阱**：走 local_upload 分支后
    `SYNO.Core.Upgrade.start` 报 **5209「patch is not ready」**，
    **且失败回滚会连带删掉整个 `@autoupdate` 目录**（已下载的包一起丢）。
    正确路径 = 重新 `Download.start` 下载 → `synoupgrade --start-force`
    （verify-checksum / check-unique / run-updater-prehook / launch-updater 四 stage 全 success）
    → `SYNO.Core.System` `method=reboot`。
  - **DSM 7.4 已移除 `synosystemctl` 二进制** —— `synosystemctl reboot` 报
    `No such file or directory`（看着像没权限，其实是文件没了），改用 Web API reboot。
  - **重启判据要用「先断后通」** —— DSM 的 5000 端口在重启流程里仍会连上好几分钟，
    只看「端口通不通」会误判成没重启。
  - **升级后 Docker 容器不会自动拉起** —— `unless-stopped` 不覆盖「daemon 整体重启」场景，
    实测多个容器停在 Exited，须逐个 `docker start`；
    `docker` 不在 PATH，用 `/var/packages/ContainerManager/target/usr/bin/docker`。
  - **升级前检查四件套**：阵列（`/proc/mdstat` 全 U + unused none）、
    空间（`/` 留 600 MB+）、内存（available ≥ 1 GB + swap）、备份。
    备份用**绝对路径**（`cd / && tar czf /volumeX/…/etc_full.tgz etc`），
    相对路径会只打出几十字节空壳。
  - **套件盘点三个坑**：`synopkg checkupdateall` / `checkupdate` 本机**返回空不可用**；
    `synopkg show` 的 `qupgrade` **对同版本包也返回 true**（实测 54 个「可升级」全是假的），
    必须自己比版本号；包 id 用 `ls /var/packages`
    （`synopkg list | cut -d: -f1` 拿到的是「名字-版本」）。
  - **DSM 跨大版本会自己升一批套件**（HyperBackup→4.2.2、SynologyDrive→4.0.3、
    SnapshotReplication→7.5.1 等），升级后必须重新盘点，别以为是自己装的。
  - 附 `synoupgrade` 可用选项全集、API 速查表、13 条排错速查表。
- **新增 `references/bulk-file-rename.md`** —— 批量文件改名 / 归集 / 隔离方法论：
  - **WAL 先行（硬规则）** —— 破坏性批量改名，日志必须**先于文件落盘**且 `fsync`。
    实测反面教材：17124 条全部改完、最后统一写 CSV 时崩溃，**明细全丢**，
    而 btrfs 没开快照 → 原名不可恢复。
    崩溃后的三层补救：隔离区路径反推 / 归集 manifest 反查 / 现状清单重算（兜底）。
  - **跨 btrfs 子卷 rename 必报 EXDEV** —— 同一物理卷上的不同「共享文件夹」
    是不同子卷（`stat` 的 `st_dev` 不同即跨卷），rename 要 **copy + unlink**；
    `shutil.move` 会**静默降级**成复制（不报错但极慢）。
  - **SMB 客户端改名 Permission denied，NAS 端 root 可以** —— 普通用户对源文件无删除权
    （实测 151 成功 / 198 失败）→ 改走 NAS 端 root `mv` 后 198 个全成。
    附 NAS 后台进程活不过 SSH 会话的两种可靠写法（前台分批 / python3 脚本自循环）。
  - **干跑必做** —— 实测靠 dry-run 抓到三个规则回退：
    正则尾部断言误伤编号（`(?![\x20-])` → `(?![0-9])`）、
    标签表误收编号前缀（`CRC`）、日期被分隔符拆开（需 token 占位保护）。
    另：`~` 会毁掉片名；括号内纯序号要保留在尾部；隔离区统计别 skip `@eaDir`
    （实测 715 vs 实际 17974）。
  - **敏感内容分类只能用客观指征** —— 题材/风格标签不能当判据，
    原则是**宁可漏判不可误判**。
  - **判有效媒体要看文件头不看扩展名** —— MP4 `ftyp`+`moov` / MKV `1A45DFA3` / AVI `RIFF`。
    某类假视频扩展名实测**并非都是空文件**（三类：全空 / 内容完整仅未改名 / 真未完成）。
  - 附媒体库重扫的有效/无效接口清单（`/Library/Refresh` 204 有效，
    `/Library/VirtualFolders/Refresh` 404 无效）。
- `SKILL.md`：新增「系统升级与套件批量升级」「批量文件整理」两节；
  专项能力表补 2 行；**实测设备档案新增档案 C（DS423+ / DSM 7.4.1-90080）**；
  常见坑补 3 条；description / description_zh / description_en 同步更新。
- **无新增脚本**：本次沉淀的全是「操作方法论与坑位」，脚本化收益不大，
  沿用既有 `nas_exec.py` / `dsm_api.py` 即可。

### 2026-10-26 追加 · v1.3.0 并入 Drive 客户端运维与上传后删本地

> 素材来源：DS918+ / DSM 7.3-81180 + Windows 10 + Drive Client 8.0.3.17892 的实测，
> 以及一次 P0 级数据清空事故复盘（2026-10-26）。仍属 v1.3.0（新增能力，不另起 minor）。

- **新增 `references/drive-client-and-retention.md`** —— 从「Drive 客户端在哪」到
  「删除只由服务器侧内容实锤授权」的完整链路：
  - **客户端落点三个反直觉**：装在 `%LOCALAPPDATA%\SynologyDrive\SynologyDrive.app\bin`
    （不在 Program Files）；进程名是 `cloud-drive-*`（按 `synology*` 查一定漏判）；
    日志在 `log\daemon.log`（不是 `data\logs\`）；版本只能读卸载注册表 `DisplayVersion`。
  - **同步 vs 备份必须先自证方向性**：`sys.sqlite` 的 `session_table` 里看
    `session_type` / `sync_direction` / `ignore_local_remove`（只读要用 `immutable=1`）。
    双向同步下本地删除会**反删服务器副本**。
  - **⚠️ 删「同步任务」本身是破坏性动作** —— 向导里勾「同时删除本地文件」，
    `recycle-cleaner` 立即无条件清空源目录；实测 1 分钟内 8 个文件 / 1.21 GB 归零，
    而备份任务只以 `[INFO]` 级 `(vanish)` 静默跳过，唯一异常迹象是上传计数为 0。
  - **FileStation 取证契约**：`additional` 必须是 JSON 数组、`checksum` 不在 List 选项里、
    `size` 可能是字符串、时间读 `additional.time.mtime`；MD5 走独立的
    `SYNO.FileStation.MD5`（`start` → `status` 两段式）。
  - **Drive API 不能做逐文件校验**（`Files.list` 报 1000、`Node.list` 忽略 `path`），
    逐文件取证只能走 FileStation 或 SSH；两条通道的路径视角也不同（共享文件夹 vs 卷路径）。
  - **安全删除七件套**：`verified_at → staged_at → purged_at` 三阶段状态机、
    `verified_at` 计时起点与重置规则（指纹用 `mtime_ns`，只比 MD5 会漏掉 A→B→A）、
    删除前 TOCTOU 双端复检、purge 前 realpath 白名单、暂存同名追加后缀、
    dry-run 默认、空落地守卫用「合格候选数」做前置条件。
- `references/error-codes.md`：新增「FileStation Web API 错误码」一节 ——
  `400` 多为负载型偶发（判据：同账号同路径结果是否不一致）、
  `599` 是 MD5 任务已丢失（重发 `start` 拿新 taskid，重试同一 taskid 无效）。
- `SKILL.md`：专项参考表扩为 NFS / 性能诊断 / 系统升级 / 批量整理 / Drive 五类
  （补 Drive 一行）；常见坑补 Drive 一条；版本基线文案 `1.1.0` → `1.3.0`；
  frontmatter `version` 1.2.0 → 1.3.0，三条 description 同步追加「Drive 客户端运维」。
- `README.md`：场景速查补 6 行（升级 / 批量整理 / Drive 各 2 行）；参考文档目录表补 3 行。
- `scripts/pack_skill.py`：`DOC_ORDER` 补入 `dsm-upgrade.md`、`bulk-file-rename.md`、
  `drive-client-and-retention.md`、`vdi-nas-perf-test.md`，修正包内文档顺序。
- `VERSION`：1.2.0 → **1.3.0**。

## 2026-10-14 · v1.2.0 NFS 文件服务 + 性能与网络诊断（并合入上游 v1.1.0）

> 本次是**双向合并**：先把本地基线快进到上游 **v1.1.0**（AD 域控 GPO/FSLogix/ACL、
> VDI 压测参考、只读守卫 quote-aware 修复、免责声明改为安装时单次弹出），
> 再叠加本次新增的 NFS 与性能诊断两条专项能力。v1.0.2 / v1.0.3 两个本地版本号
> **从未发布**，本次统一跳到 **1.2.0**（相对已发布的 1.1.0 属新增能力，语义化 minor）。

- **新增 `references/nfs-service.md`** —— NFS 从「有没有导出」到「能不能挂、该怎么选」一整条：
  - **头号纠正：`/etc/exports` 里没有某个共享 ≠ NFS 没开。** 权威判据是 Web API
    `SYNO.Core.FileServ.NFS.SharePrivilege load share_name=<共享>` 返回的 `rule` 是不是空数组。
    该接口只有 `load` / `save`，**参数名是 `rule`（不是 rules）**，且是**整体覆盖**——
    改一条规则要先读全量再写回，否则会冲掉别人的规则。
  - NFSv3 协议要点与 6 个实测坑（RPC 头含 `proc` **不能缓存复用**，否则 MNT 会以 EXPORT 发出去、
    表现为「MNT status=1 像是权限问题」；`CREATE` 返回 `post_op_fh3` 有布尔前缀；
    单次 `WRITE` 超上限会被 nfsd **直接 RST**，实测上限 1 MiB；记录标记可能多片段；…），
    附 MOUNT / NFS 两层状态码对照。
  - UNIX 权限与 UID 映射（`/volume1/homes` 是 711，非属主能穿越不能列目录）。
  - **写语义**：实测 Synology nfsd **不给 `UNSTABLE` 开写回**，`COMMIT` 瞬时返回 →
    NFS 写天然是持久化口径，和 SMB 的页缓存口径不可直接比。
  - Windows Client for NFS 的两个绕不开的限制：**匿名 UID/GID 是整机注册表级**、
    **挂载按会话/账户** → VDI「每人挂自己 home」在 NFSv3 + Windows 下难落地
    （这是此前 VDI 项目最终选 SMB 的现实理由之一）。
  - NFS vs SMB 取舍对照表（含「别把用户数据放到 ESXi 正在用的同一个导出上」）。
- **新增 `references/perf-and-network.md`** —— 「NAS 慢」怎么定位：
  - **三层对照法**：客户端观测 / **NAS 侧 `/proc/net/dev` 实测** / NAS 本机裸盘。
    只看客户端数字会把「客户端消费不动」误判成「NAS 慢」（实测客户端 1044 MiB/s 那一次，
    NAS 实际发出 1160 MiB/s）。
  - **多网卡路由陷阱**：DSM 默认路由只挂一张卡 → 跨网段**读**被压回千兆口，
    症状是「写正常、读 ~110 MiB/s 且延迟恒定、方差极小」。给了
    `ip route get` / `ip rule list` / `table static-table` 的诊断与修正，
    并强调**该改动是临时的（重启即丢）、属改配置、必须先与用户确认**。
    顺带排除两个常见误判：SMB Multichannel 开关、RAID 写惩罚。
  - **口径陷阱**：同一目录 `dd` 的三种写法（`oflag=direct` / `direct,dsync` / `conv=fsync`）
    能差 3 倍以上（实测 701 / 401 / 1335 MiB/s），写的结论必须标口径。
  - 附一台万兆 NAS 的实测基线表（空载 RPC 0.106 ms、读 1160 MiB/s、写 546–577 MiB/s …）。
- **新增脚本**：
  - `scripts/nas_nfs.py` —— 共享文件夹 NFS 导出规则 `list` / `show` / `set` / `revert`；
    `set` / `revert` 属变更操作，不加 `--yes` 直接返回 2（只读优先红线）。
  - `scripts/nfs3_client.py` —— **纯标准库实现的 NFSv3 客户端**，不需要系统 NFS 栈、
    不需要管理员。子命令：`verify`（MNT/READDIR/CREATE/WRITE/回读校验/REMOVE 全流程）、
    `rsize`（探测服务端上限）、`read[-sweep]` / `write[-sweep]` / `randread[-sweep]` / `lat`。
    这是「Windows 装不了 NFS 客户端」时唯一还能验证 NAS 侧的办法。
  - `scripts/nas_nic_sample.py` —— SSH 读 `/proc/net/dev` 逐秒采样各网卡 RX/TX（只读），
    判定瓶颈侧的关键工具。
- **`scripts/dsm_api.py`**：`call()` 增加可选 `post=True`（参数值很长时更稳，如 NFS 的 `rule` JSON）。
- **既有文档更新**：
  - `references/dsm-web-api.md`：速查表补 `SYNO.Core.FileServ.NFS.SharePrivilege`、
    `SYNO.Core.FileServ.SMB`（**必须 POST + 全字段，否则 error 2001**）、
    `SYNO.Core.Network.Ethernet`；`Routing` 标注为未验证。
  - `references/ssh-and-troubleshooting.md`：新增第 9–12 条 —— 先 `whoami`/`id` 确认身份
    （DSM 7 上 SSH 用户**不是 root**，读 `/etc/exports` 报 Permission denied 是权限边界）、
    `sudo -S` 喂密码与提示串污染 stdout、**Git Bash `MSYS_NO_PATHCONV=1` 路径转换坑**。
  - `SKILL.md`：新增「文件服务（NFS）与性能诊断」小节与三条最值钱结论；
    **实测设备档案新增档案 B（RS6426xs+ / DSM 7.4.1-90080）**；常见坑补三条。
  - `README.md`：新增专项能力表、第 6 节 NFS 与性能诊断快速上手、场景速查 6 条、目录与排错同步。
  - `scripts/pack_skill.py`：打包清单（DOC_ORDER）补入新增的 2 份参考与 3 个脚本。
- `VERSION` → `1.2.0`。

## 2026-10-13 · v1.1.0 新增 AD 域控管理能力（GPO / FSLogix / ACL）

- **新增 `references/synology-gpo.md`**：群晖域控 GPO 管理（无 ADWS 绕过方案）。
  基于 2026-10-12 DS918+（DSM 7.3，Samba AD 域控）实操：域控不运行 ADWS，
  GPMC / PowerShell GPO 模块 / Get-ADDomain 均不可用，唯一可行路线是
  LDAP（必须 LDAPS 636）+ SYSVOL 直改。含 GPO 创建完整清单
  （groupPolicyContainer 对象 / CN=Machine+CN=User 子容器 / gPLink / GPT.INI）、
  registry.pol 二进制格式规范与生成代码、默认域策略逐字节对比调试法、
  事件 ID 1058/1096/1502 错误码速查与排错顺序。
- **新增 `references/fslogix-odfc.md`**：FSLogix ODFC 容器在群晖上的完整部署。
  含共享子目录 ACL 配置（断开继承 + 三条目 ---n）、Agent 静默安装、
  ODFC 注册表 10 值完整表、群晖环境 5 个关键结论、验证方法与实测记录。
- **新增 `references/synoacltool-acl.md`**：synoacltool 实战。13 位权限串 →
  Windows 权限映射表、常用模板（FC/RW/RO/仅穿越/域用户容器根）、
  继承标志、四大怪癖（mkdir 需 W+C / 他人 fd-- 条目阻止 mkdir /
  CREATOR OWNER 不支持 / owner 隐式权限更宽）、条目排序陷阱、域主体写法。
- **SKILL.md**：执行方式通路表新增「AD 域控管理」行；新增
  「AD 域控管理通路（Directory Server）」章节（凭据 LDAP_USER/LDAP_PASS、
  samba-tool 位置 / SYSVOL 路径 / SFTP 写不了 @appdata 等环境备注）；
  细粒度权限与 VDI 两节加 references 指引；版本基线文案与 VERSION 对齐
  （声明以 VERSION 文件为准）。
- **修 `scripts/nas_exec.py` 只读守卫误拦**：原 DESTRUCTIVE 检查对整条命令
  做子串匹配，`grep 'rm '` 这类引号内文本 / testparm 输出中的 "rm " 会误触
  （2026-10-12 实测 `samba-tool testparm` 被拦）。改为按 shell 分词后的
  命令词 + 独立选项 token 匹配，引号内容与重定向检查均走 quote-stripped
  文本；config_mutations 的子串检查同样改为忽略引号内文本；
  新增 samba-tool / synoacltool 只读子命令白名单。16 条正反用例回归通过。
- `VERSION` → `1.1.0`（新增能力，语义化 minor）。

> 规则：每周只回传「新增的能力」到 ima「公用nas操作技能」库（kb_id `7510180233248137`），
> 条目名《Synology NAS 管理技能包-增量-YYYY-MM-DD.md》；
> 每月做一次整合，重新打整包并 REPLACE 覆盖《Synology NAS 管理技能包.md》。
> 所有内容脱敏，不记录任何真实账号/密码/密钥。

## 2026-10-11 · 新增 VDI NAS 性能测试参考 + 免责声明改为安装时单次弹出

- **新增 `references/vdi-nas-perf-test.md`**：整合 WorkBuddy 资料库《VDI NAS 性能测试》归档
  三篇（成果汇总 / 全过程记录 / 踩坑手册）为一份脱敏、技能导向的参考。内容含：
  RS6426xs+ 双万兆上 350 台 VDI 用户盘承载验证的测试通路定义、成果矩阵、
  双万兆静态路由修复（跨网段读 113→1125 MiB/s，约 10 倍）与 SMB 低风险调优收益、
  350 并发验收判定口径、根因诊断套路、10 阶段流程速览、按类踩坑清单、
  以及可直接复用的 fio / DiskSpd / `ip route` 命令片段。
  真 IP / 主机名 / 账号按脱敏规范一律占位，仅保留机型 / DSM 版本等无凭据事实。
- **SKILL.md 新增「VDI 性能压测与容量验证（实测案例参考）」一节**指向该参考；
  README.md 场景速查表与目录表同步加条目。
- **免责声明改为仅安装时弹出一次**：去掉 SKILL.md「首次加载必弹（每次触发本技能第一件事输出）」
  的强制指令，改为「安装须知（仅安装时由 first_run.py 弹出一次）」；`first_run.py`
  docstring 与 README.md 使用须知措辞同步更新——不再于每次触发技能时强制输出，
  避免打扰。声明文本本身保留（仍由 first_run.py 在需要时打印）。
- `VERSION` → `1.0.3`。

> 规则：每周只回传「新增的能力」到 ima「公用nas操作技能」库（kb_id `7510180233248137`），
> 条目名《Synology NAS 管理技能包-增量-YYYY-MM-DD.md》；
> 每月做一次整合，重新打整包并 REPLACE 覆盖《Synology NAS 管理技能包.md》。
> 所有内容脱敏，不记录任何真实账号/密码/密钥。

## 2026-10-04 · 本周无新增 NAS 能力；修 delta 起点精度（防重复回传）

- **本周（采集窗口 2026-09-27 → 2026-10-04）无新增能力**：工作区记忆日志中
  没有新的 NAS / DSM / SSH / synouser / synoshare / dsm_api 操作记录、报错或新设备信息，
  最近一次有证据的改动仍停在 2026-09-30（已并入 2026-10-02 整包 v2026.09）。
  按「不臆造」原则，本次不新增任何设备档案条目与命令。
- **修 `pack_skill.py` delta 起点精度（本周唯一代码改动）**：
  水位原来只存 `YYYY-MM-DD`，`changed_files()` 按当天 00:00 比较 mtime。
  实际后果（本次跑出来的）：2026-10-02 03:28 月度整包改过的 `SKILL.md` / `CHANGELOG.md`
  mtime 落在 10-02 00:00 之后 → 被永久判为「变更」，**每周都会把这两个大文件当增量重复回传**，
  直接违反「周度只回传新增能力」。
  改为新增 `parse_since()`，接受 `YYYY-MM-DD[ HH:MM:SS]`，delta 默认优先取
  `build/.sync_state.json` 的 `last_stamp`（带秒），无 stamp 才退回 `last_sync` 当天 00:00。
  实测：修前 `--list-changed` 报 `SKILL.md`+`CHANGELOG.md`，修后只剩本次真改动的文件。
- 校验：`python -m py_compile scripts/*.py` 全通过；
  守卫不加 `--dry-run` 实测：改配置（`synouser --setpw`）返回 **2** 并打印只读策略提示，
  只读命令（`synouser --list`）放行（本例止于本机 SSH 连接失败，非守卫拦截）。
- 回传状态：**未完成** —— 当前会话 ima 连接器不可用（`create_media` / `add_knowledge` 不在工具列表），
  增量产物留在本地，需人工上传或先接回 ima 连接器。

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
