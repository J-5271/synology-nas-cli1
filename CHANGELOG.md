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

## 2026-09-27 · v2026-09-27

- 新增「细粒度权限：synoshare 做不到」：ACL 删除位 D/DC 拆分、两条规则、
  CREATOR OWNER、系统共享文件夹不支持 Windows ACL、ACL 上限 200、权限检查器验证。
- 新增「技能包维护与 ima 同步」：三步回传流程、bucket appid 坑、
  403 InvalidAccessKeyId 处置（重取凭证）。
- `pack_skill.py` 打包含自身与 `cos_upload.py`；`cos_upload.py` 支持多 host 回退 + URLError 捕获。
- cli-commands.md 补 synoshare 权限粒度注解；三份 references 补维护记录。
- 实测设备档案：本周无新增实测设备（DS918+ / DSM 7.3-81180 不变）。
