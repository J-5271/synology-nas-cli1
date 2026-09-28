# 版本记录（CHANGELOG）

> 规则：每周只回传「新增的能力」到 ima「公用nas操作技能」库（kb_id `7510180233248137`），
> 条目名《Synology NAS 管理技能包-增量-YYYY-MM-DD.md》；
> 每月做一次整合，重新打整包并 REPLACE 覆盖《Synology NAS 管理技能包.md》。
> 所有内容脱敏，不记录任何真实账号/密码/密钥。

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

## 2026-09-27 · v2026-09-27

- 新增「细粒度权限：synoshare 做不到」：ACL 删除位 D/DC 拆分、两条规则、
  CREATOR OWNER、系统共享文件夹不支持 Windows ACL、ACL 上限 200、权限检查器验证。
- 新增「技能包维护与 ima 同步」：三步回传流程、bucket appid 坑、
  403 InvalidAccessKeyId 处置（重取凭证）。
- `pack_skill.py` 打包含自身与 `cos_upload.py`；`cos_upload.py` 支持多 host 回退 + URLError 捕获。
- cli-commands.md 补 synoshare 权限粒度注解；三份 references 补维护记录。
- 实测设备档案：本周无新增实测设备（DS918+ / DSM 7.3-81180 不变）。
