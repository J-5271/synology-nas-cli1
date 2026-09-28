---
name: synology-nas-cli
description: 通过 SSH（root/官方 CLI 工具）或 DSM Web API 管理 Synology NAS（DSM）——查状态、列用户与共享文件夹、开关 SSH、执行只读巡检。涉及改配置或破坏性操作时受只读优先策略约束。当用户提到群晖 / Synology / NAS / DSM / synouser / synoshare / dsm_api 时使用。
agent_created: true
---

## 通过 SSH 操作 Synology NAS（DSM）

本技能用于直接管理 Synology NAS。素材来源：ima「synology开发相关」知识库中的官方
*CLI Administrator Guide for Synology NAS*，以及 Synology 官方知识中心的
SSH root 登录、SSH RSA 密钥登录两篇文章。

### ⚠️ 安全红线（优先级最高）

root/SSH 权限可以直接毁掉数据。执行前必须遵守：

- 默认不改设备配置 —— 只读优先。
除非用户明确点名要改，NAS 自身的持久配置一律不动。包括但不限于：
写 ~/.ssh/authorized_keys、改 /usr/syno/etc/ 下的配置、synonet 改 IP/网关/DNS、
synoservice --enable/--disable/--restart 改服务状态、synouser/synogroup/synoshare
增删改、synouser --setpw 改密码。
拿不准就当「要改配置」，先问再做。查状态、列表、--help 这类只读操作不受限。
> 配套：脚本里有 MUTATING 守卫，命中会拦下来要求 --yes。
> --install-key 也在其列（它会改写 NAS 上的 authorized_keys）。
- 不要主动做端口扫描 / 暴露面审计。用户没要求，就别扫端口清单、别点评哪些端口危险、
别建议关端口换 HTTPS。连不上时只围绕当前任务需要的那个端口排查即可。
- 破坏性操作必须二次确认 —— 任何 rm、--del、格式化、重启、关停服务、
改网络（改 IP 可能直接失联）、改磁盘/存储的操作，都要先向用户明确说明将要执行的命令、
影响范围，并拿到明确确认。只读命令（--list / df / cat /etc/VERSION / 查看状态）无需确认。
- 禁止批量 rm。不要写 rm -rf /*、rm -rf /volume* 这类东西。
- 改网络前先想退路：synonet --set_gateway / --set_dns / --manual 会把 NAS 踢下线，
确认有物理访问或 KVM/IPMI 再动。
- 用完关 SSH。临时开启的 SSH 服务在任务完成后询问用户是否关闭。
- 官方明确警告：仅在必要时启用 SSH，并避免对系统配置进行更改。

### 连接流程（二选一）

#### A. 密码方式（临时使用，来自官方 KB）

- 在 DSM 开启 SSH：控制面板 > 终端机和 SNMP > 终端机 > 勾选「启用 SSH 服务」，记下端口。
> 官方建议把默认 22 换成其他端口。SRM 路由器的路径是「控制面板 > 服务 > 系统服务 > 终端机」。
- 登录（只有 administrators 群组的用户能登 SSH，DSM 5.2 及更早是 root）：
```
ssh <管理员账号>@<NAS_IP> -p <SSH端口>
# 例：ssh myadmin@<NAS_IP> -p 22
```
- 提权到 root —— 输入该管理员账号的密码，不是别的密码：
```
sudo -i
```
DSM 6.0/SRM 1.3 及以上必须走 sudo -i，不能直接 ssh root。

#### B. RSA 密钥方式（推荐，自动化必备；DSM 6.2.4+）

官方流程要点（细节见 references/ssh-and-troubleshooting.md）：

- 用 administrators 群组账号登录 DSM → 控制面板 > 终端机和 SNMP > 终端机 → 勾选启用 SSH。
- 若要以管理员身份用密钥登录：控制面板 > 用户和群组（DSM 7.0+）/ 用户（DSM 6.2.4）
> 高级 > 用户主目录 → 勾选「启用用户主目录服务」；并确保 homes 共享文件夹保持默认权限
（不要给非管理员读写权）。
- 本地生成密钥 `ssh-keygen -t rsa -b 4096`，把 id_rsa.pub 的内容追加进 NAS 上
对应账户 ~/.ssh/authorized_keys（root 则是 /root/.ssh/authorized_keys）。
- 本机建议配 ~/.ssh/config：
```
Host nas
HostName <NAS_IP>
User myadmin
Port 2222
IdentityFile ~/.ssh/nas_rsa
IdentitiesOnly yes
```
之后 `ssh nas` 即可；仍需 sudo -i 提权（除非直接 root 登录）。

### 执行方式

先判断走哪条路：

| 通路 | 依赖 | 适用 | 参考 |
|---|---|---|---|
| DSM Web API（优先） | DSM 的 HTTP/HTTPS 端口 + 账号密码 | 查状态、列用户/共享文件夹、改 SSH 开关等大多数运维操作；不需要 SSH 处于开启状态 | references/dsm-web-api.md |
| SSH + root | 22 或自定义 SSH 端口，且 DSM 里已启用 SSH | 需要真 shell：改系统文件、跑脚本、排查底层 | 本文档下方 + references/ssh-and-troubleshooting.md |

判断不了就用 `scripts/dsm_api.py info` 试 Web API —— 它最省事，也能顺带看出
SSH 是否已启用（SYNO.Core.Terminal）。

#### Web API 通路

```bash
export DSM_HOST="http://<nas>:<端口>" DSM_ACCOUNT=<账号> DSM_PASSWORD='<密码>'
python3 scripts/dsm_api.py info                          # 系统 + SSH 状态 + 共享文件夹
python3 scripts/dsm_api.py call SYNO.Core.User list 1 type=local
```

已实测的两个坑（详见 references/dsm-web-api.md）：

- SYNO.API.Auth 注册信息报 maxVersion=7，但 v7 登录会返回 103，要用 v6。
脚本已做 v7→v6→v3 回退。
- DSM 错误 102 = API 名不存在，不是权限不足。
（如 SYNO.Core.CurrentUser 根本没注册，别误判成没权限。）

#### 文件传输通路（上传 / 下载 / 列目录）

用 `scripts/syno.py`（纯标准库，凭据走 `SYNO_HOST` / `SYNO_USER` / `SYNO_PASS`）：

```bash
export SYNO_HOST="http://<nas>:5000" SYNO_USER=<账号> SYNO_PASS='<密码>'
python3 scripts/syno.py --list /volume1/video               # 列目录（只读）
python3 scripts/syno.py a.mp4 b.mp4 --remote /volume1/video  # 多文件上传
ls *.m4a | python3 scripts/syno.py --remote /volume1/audio   # 管道上传
python3 scripts/syno.py --download /volume1/video/a.mp4 --out .  # 下载
python3 scripts/syno.py a.mp4 --no-overwrite --remote /x/y   # 不覆盖已存在文件
```

只做文件传输（SYNO.FileStation.Upload / Download / List），不含任何改配置、删文件能力。
实测坑：`SYNO.FileStation.List` 的 `folder_path=/` 根路径会返回 401，要用具体共享文件夹路径
（如 `/volume1` 或 `/home`）；`_sid` 走 URL 查询参数或 POST body 均可，但 List 用 GET 更稳。

#### SSH 通路

用 `scripts/nas_exec.py`。它把下面三件事一次做完：SSH 登录 → sudo -i 提权 → 执行命令。

```bash
pip install paramiko          # 一次性；密码登录必须装它，见下方说明
export NAS_HOST=<NAS的IP> NAS_USER=<管理员账号> NAS_PASS='<密码>' NAS_PORT=22

scripts/nas_exec.py --health                     # 只读探针，先跑这个
scripts/nas_exec.py "cat /etc/VERSION; df -h"    # 任意只读命令
scripts/nas_exec.py --dry-run "<危险命令>"        # 只打印将要执行什么（不连设备、不过守卫）
scripts/nas_exec.py "<改配置命令>"                # 守卫：不加 --yes 直接返回 2，拒绝执行
scripts/nas_exec.py - <<'EOS'                    # 多行脚本：从 stdin 读，最保真
for t in synouser synoshare synonet; do
  [ -x "/usr/syno/sbin/$t" ] && echo "OK $t"
done
EOS
scripts/nas_exec.py --install-key --yes          # 装公钥（改设备配置，必须 --yes）
```

⚠️ 密码登录一定要装 paramiko。SSH 有两层独立的认证，别混为一谈：
① SSH 登录（密钥或账号密码）② sudo -i（同一份密码走 pty 喂给 sudo）。
OpenSSH 客户端是从 /dev/tty 读密码的，不吃 stdin——所以 `echo pw | ssh ...`
会卡在 `user@host's password:` 那儿不动。paramiko 在进程内喂密码，是唯一干净的做法。
没装 paramiko 时脚本会退回调用 ssh 二进制，那种模式只支持密钥登录。

⚠️ 别用 `sudo -i bash -c '<命令>'` 传复杂命令。实测 DSM 7.3 上 sudo 会对 payload
多套一层 shell 解析：换行被吞（echo AAA + echo BBB 变成 echo AAAecho BBB），
`$变量` 在执行前就被展开成空。脚本内部改用 base64 中转规避了这个坑（见源码注释）。
副作用是尽量用 stdin（-）传多行脚本，比塞进引号里可靠；
若用双引号包外层参数，里面的 $var 会被本地 shell 提前展开掉。

先 discover 再执行——DSM 各版本命令差异大，不要凭记忆下命令：

```bash
scripts/nas_exec.py "ls /usr/syno/sbin/ | grep -i syno"   # 本机有哪些 CLI 工具
scripts/nas_exec.py "/usr/syno/sbin/synouser --help"       # 该版本真实语法
```

内网 vs 外网：SSH 通常只在内网可达。公网域名上能连到 DSM 网页，
不代表 SSH 端口也转发了——先 `nc -zv <host> <port>` 或直接跑脚本确认。
连不上时先分清是 Connection refused（端口没转发）还是 No route to host / 超时。

### 官方 CLI 工具速查

命令都在 /usr/syno/sbin/ 下，只有 root（super-user）能跑。
完整语法、参数限制、示例见 references/cli-commands.md，执行前必读。

| 工具 | 用途 |
|---|---|
| synouser | 本地用户：增/删/改名/改密/改信息 |
| synogroup | 本地群组：增/删/改名/改成员 |
| synoshare | 共享文件夹：创建/删除/改名/改 ACL |
| synonet | 网络：DHCP/静态 IP/网关/DNS/MTU/主机名 |
| synoservice | 服务：启停/开关/列表（ssh、samba、ftp、nfs…）—— ⚠️ 实测 DSM 7.3-81180 上不存在，见下方 |
| synowin | 加入工作组 / ADS 域 |

⚠️ 实测校正（DS918+ / DSM 7.3-81180）：官方指南列的 6 个工具里，
synoservice 在 /usr/syno/sbin/ 下已经没有了（synouser synogroup
synoshare synonet synowin 都还在）。
这台机器上服务管理走的是 systemd（`systemctl --version` → systemd 219）。
先 discover 再下命令，不要默认手册里的工具一定存在。

#### 高频示例（均出自官方指南）

```bash
# 改 admin 密码
/usr/syno/sbin/synouser --setpw admin '<新密码>'

# 建用户 alice，可访问 FTP(0x1) + File Station(0x2) = 3
/usr/syno/sbin/synouser --add alice 'P@ssw0rd' 'Alice' 0 alice@example.com 3

# 建共享文件夹 private（空 ACL，可见）
/usr/syno/sbin/synoshare --add private 'Comment' /volume1/private '' '' '' 1 0

# 给 alice 和 stuff 组加 private 的读写权
/usr/syno/sbin/synoshare --setuser private RW + alice,@stuff

# 静态 IP + 网关 + DNS（会断网，务必先确认）
/usr/syno/sbin/synonet --manual eth0 192.0.2.10 255.255.255.0
/usr/syno/sbin/synonet --set_gateway 192.0.2.1
/usr/syno/sbin/synonet --set_dns 203.0.113.53

# 服务管理
# DSM 7.3 实测：synoservice 已移除，改用 systemd
systemctl list-units --type=service --state=running | head
systemctl status <服务名>
# 官方 synoservice 语法（DSM 6 / 7 早期版本仍有用）
/usr/syno/sbin/synoservice --enable ssh     # 启用并立即启动
/usr/syno/sbin/synoservice --restart samba
/usr/syno/sbin/synoservice --list           # 全部服务
/usr/syno/sbin/synoservice --list running   # 仅运行中
```

### 细粒度权限：synoshare 做不到（2026-09-21 实测）

需求原型：「某账号能建文件夹/文件、能删自己建的文件，但删不掉文件夹」。

- **共享文件夹三档（NA/RO/RW）做不了。** synoshare --setuser 只有 NA/RO/RW 三档
  （见 references/cli-commands.md），没有「只给文件的删除位」这种粒度。
  细粒度需求必须走 DSM 的 Windows ACL：File Station / 控制面板 → 共享文件夹 →
  权限 → 自定义 ACL。控制台那三档开关同样做不到。
- **关键机理：ACL 里「删除」是两个独立权限位。**
  - 删除（Delete / D）—— 作用于文件，也作用于文件夹自身
  - 删除子文件夹及文件（Delete subfolders and files / DC）—— 作用于文件夹里的内容
- **两条规则凑出效果**（对目标文件夹先禁用继承、转显式权限）：
  1. 基础读写：应用于「此文件夹/子文件夹/子文件」，勾创建的写入位，
     **不勾删除、不勾删除子文件夹及文件**。简档用「写入(W)」而非「修改(M)」——M 自带删除。
  2. 仅文件的删除权：应用于**仅子文件**（不要勾子文件夹），写入只勾「删除」。
- **只能删自己建的**：把规则 2 的主体换成 **创建者所有者 / CREATOR OWNER**（Windows SID S-1-3-0）。
- **坑与边界**：
  - 别把该账号放进 administrators 组 —— 管理员的完全控制会绕过上述限制。
  - 一旦给了 DC，整棵子树都能删，方案直接失效。
  - 群晖系统共享文件夹 photo / satashare / sdshare / surveillance / usbshare **不支持 Windows ACL**。
  - 单文件/文件夹 ACL 条数上限 **200**。
  - 群晖「高级权限 → 禁止修改现有文件」只禁改不禁删，不满足此类需求；回收站只能兜底。
  - PowerShell 里 `(OI)(IO)` 不带 `(CI)` 会被折叠显示成父级条目，看着像串了，实际生效正确；
    DSM 权限编辑器能直接看到「文件/子文件夹」分开的勾选状态，更直观。
- **验证**：File Station → 属性 → 权限 → 高级选项 → **权限检查器（Permission Inspector）**，
  选用户看有效权限。（Windows 侧对应「安全 → 高级 → 有效访问」。）
- **Windows icacls 等价写法（在 Windows 文件服务器上本机实测通过，不是 DSM CLI）**：
  ```
  icacls "投标文件夹" /inheritance:d
  icacls "投标文件夹" /grant "投标管理员:(OI)(CI)(RX,W)"
  icacls "投标文件夹" /grant "投标管理员:(OI)(IO)(D)"
  ```
  第三条 `(OI)(IO)` 不带 `(CI)` → 只被文件继承、不被文件夹继承。
  ⚠️ DSM 上**没有**验证过等价的命令行写法，不要在 NAS 上臆造 chmod/synoacl 命令去实现它，
  走 GUI 权限编辑器。

### 脱敏规范（强制，优先级同安全红线）

回传 ima / 写进本技能包的任何内容，**不得包含真实凭据**：

- 禁写：真实账号名、密码、sid、SSH 私钥、云的 secret_id / secret_key / token。
- 一律用占位符：`<账号>` `<密码>` `<NAS_IP>` `<SSH端口>` `$DSM_PASSWORD` `$NAS_PASS`。
- 设备档案只记型号 / DSM 版本 / 平台 / 网络可达性这类**无凭据**的事实；
  IP 用网段写法（如 `<内网网段>/24`）。
- 凭据只走环境变量或交互输入，**不落盘、不写脚本、不写命令行历史、不进 git**。
- `pack_skill.py` 默认做凭据扫描，命中疑似真实值即中止打包（exit 4）；
  确认真安全才加 `--allow-secrets`（不推荐）。

### 免责声明（对外必读）

- 本技能包为**个人收集整理**的运维笔记：素材来自 Synology 官方文档、官方知识库及个人设备实测。
- **仅限个人学习与技术交流，禁止商用开发**（不得用于商业开发、商业交付、付费服务或二次分发获利）。
- 不同机型 / DSM 版本行为差异很大，内容**不保证适用**于你的设备，一切以设备上 `--help` 与官方知识库为准。
- 因参考或使用本包造成的任何数据丢失、设备损坏或服务中断，整理者**不承担任何责任**；
  执行写操作前先备份、先在测试环境验证。

### git 仓库：唯一真实来源

| 项 | 值 |
|---|---|
| 本地仓库 | `~/.workbuddy/skills/synology-nas-cli/`（唯一真实来源，所有改动先 commit 到这里） |
| 公开分发仓库 | **https://github.com/J-5271/synology-nas-cli1** （公开；只读镜像，用于他人 clone / 下载 Release） |
| 默认分支 | `main` |
| 历史备份 | `~/.workbuddy/skills/synology-nas-cli-backup-20260928.bundle`（含全部 commit，`git clone <bundle>` 可还原） |

任何改动先 `git commit`，再谈 ima 回传。git 历史即版本记录，回滚用 `git revert` / `git checkout <sha> -- <file>`。
`.gitignore` 已排除 `build/`（打包产物）与 `*cred*.json`（临时 COS 凭证）。

#### 分发与版本策略（2026-09-28 定）

- **分发**：GitHub 公开仓库为主渠道。使用者 `git clone <repo>`，或下载 Release 里打好的
  `.tar.gz`（tag 对应稳定版）。不要让人追 `main` HEAD。
- **版本**：语义化版本 `vX.Y.Z`，打 tag 即代表一个可安装的版本；预发布用 `-rc.N`。
- **发布节奏**：日常改动照常 commit；**主要版本由维护者手动审批发布**
  —— `ci.yml` 的发布 job 走 `workflow_dispatch`，人点"Run workflow"并填版本号才上传 Release 产物。
  这样自动化负责构建，发布时机仍掌握在人手里。
- **推送远端**：`git remote add origin https://github.com/J-5271/synology-nas-cli1.git`
  （或已挂过时）`git push -u origin main` 与 `git push --tags`。

> ⚠️ 公开仓库 = 任何人可见。推送前跑一遍自查：无真实 IP / 账号 / 密码 / sid / token，
> 见上方「脱敏规范」。`pack_skill.py` 的凭据扫描同样适用于推送前检查。

### 安全与隐私（对外声明，2026-09-28 定）

本技能包的立场是**用户主动回传，不做自动遥测**：

- 脚本本身**没有任何出站上报行为**：不收集主机名、内网 IP、用户名、文件路径、共享名。
- 所有与 NAS 的通信都由使用者自己发起（本机 → 自己的 NAS），凭据只走环境变量，不落盘、不写日志。
- 支持**完全离线使用**：不开任何外网功能也能跑完 SSH / DSM Web API 两条通路。
- 使用者改进内容、实测记录、问题反馈，通过下方回传入口**由人主动提交**；
  提交前请自行抹掉 IP、序列号、账号名等标识信息（规则同「脱敏规范」）。
- 依赖与供应链：CI 里的第三方 Actions 固定到 commit SHA，不用可变标签；
  版本发布产物附 SHA256 校验和。

### 使用报告回传入口

| 项 | 值 |
|---|---|
| 方式 | **腾讯文档在线表格**（收集表模式：**只允许他人填写/提交，不可查看或修改他人记录**） |
| 地址 | `<待补充：腾讯文档表格链接>`（创建后填入本节与 README） |
| 表头（建议） | 提交日期 / 提交人（可匿名）/ 机型 / DSM 版本 / 场景 / 命令或现象 / 结论或建议 / 附件说明 |
| 适合回传 | 设备实测记录、命令输出、改进建议、问题反馈 |
| 不适合 | 任何含密码 / sid / 私钥 / 真实 IP / 序列号的内容（先脱敏再填） |

**创建与权限设置（三步，缺一不可）**

1. **收集表模式** —— 保证"只能提交，不能改表"
   腾讯文档首页 → 新建 → **收集表**（或打开在线表格 → 工具栏/菜单「收集表」→ 开启收集）。
   设置：
   - 填写人范围：所有人（有链接即可）／指定人
   - 每人可填写次数：按需限制（防刷）
   - **关闭「允许修改已提交记录」**、**关闭「允许查看全部记录」**
   → 填写者只看到自己的提交表单，看不到整张表。

2. **隐私填写**（列级，兜底防互看）
   列头下拉箭头 → 「列设置」/「填写内容隐藏、提示语等设置」→ 勾选 **填写内容隐藏**。
   可设"前 N 行仍可见"（表头 + 示例行设为 2）。
   设置后只有文档所有者/管理员能看到全部，填写者只看得到自己填的。
   ⚠️ 取消隐藏后历史内容会对所有人可见，谨慎。

3. **锁定表头与已有区域**（防误改）
   选中表头行/历史数据区 → 右键或菜单「保护/锁定区域」→ 设为**仅我可编辑**。

**注意**
- 分享权限里选「可编辑」≠ 仅填写，那会让人改别人内容；必须用上面的收集表模式。
- 链接是公开填写入口，任何人都能提交；定期导出归档后清空即可。
- 上述 UI 名称随版本可能变化（"收集表"也可能叫"填写"），以实际界面为准。

### 技能包维护与 ima 同步（周增量 + 月全量）

| 项 | 值 |
|---|---|
| 回传目标库 | ima「**公用nas操作技能**」kb_id `7510180233248137` |
| 素材源库 | ima「synology开发相关」kb_id `7506185150271226`（只出不进） |
| 全量条目名 | 《Synology NAS 管理技能包.md》—— 每月整合，REPLACE 覆盖 |
| 周增量条目名 | 《Synology NAS 管理技能包-增量-YYYY-MM-DD.md》—— **只回传新增能力** |
| 版本记录 | 产物头部 version=打包日期 + 生成时刻；`CHANGELOG.md` 逐条记时间与新增能力 |
| 同步水位 | `build/.sync_state.json` 的 `last_sync`，作为下次 delta 的起点 |

节奏（已挂自动化）：

- **每周**（automation-1790221817758，周日 21:00）：`--mode delta` 只打包上次同步之后变动的文件；
  无变更则 exit 3，跳过回传；同时在 CHANGELOG.md 记一条带日期的新增能力。
- **每月**（automation-1790567281158，每月 1 日 21:00）：`--mode full` 重新打整包，
  REPLACE 覆盖总条目，把本月所有增量并回主干。

```bash
# 1. 改动脚本后必做
python -m py_compile scripts/*.py                       # 语法检查
python scripts/nas_exec.py "<改配置命令>"                # 守卫：不加 --yes 应返回 2
python scripts/nas_exec.py --dry-run "<命令>"            # 只打印将要执行什么，不校验守卫

# 2. 周：只打新增（无变更会打印 NO_CHANGES 并返回 3）
python scripts/pack_skill.py --mode delta
python scripts/pack_skill.py --mode delta --since 2026-09-21   # 手动指定起点
python scripts/pack_skill.py --mode delta --list-changed        # 只看改了哪些文件

# 3. 月：整包整合
python scripts/pack_skill.py --mode full                 # → build/Synology NAS 管理技能包.md
```

回传三步（ima 连接器，两种模式通用）：

1. `create_media`：content_type=text/markdown、file_ext=md、
   file_size=实际字节数、knowledge_base_id=`7510180233248137`
2. 用 `scripts/cos_upload.py --cred-file <凭证JSON> --file <本地md>` 上传（凭证来自第 1 步返回）
3. `add_knowledge`：duplicate_name_strategy=DUPLICATE_NAME_STRATEGY_REPLACE

坑（2026-09-24 实测）：COS 的 `bucket_name` **已带 appid 后缀**（如 `ima-share-kb-1258344701`），
再拼一次 `-{appid}` 会 NoSuchBucket 404。cos_upload.py 已做 endswith 保护。

坑（2026-09-27 实测）：上传返回 403 `InvalidAccessKeyId` 时，别去改签名算法 ——
多半是凭证本身有问题（转录/截断/已失效）。**重新 create_media 取一份新凭证即可**，
实测换新凭证后同一脚本一次 PUT 200 通过。cos_upload.py 现已支持多 host 回退
（标准 COS 域名 → custom_domain）并捕获 URLError，便于区分「凭证错」与「域名不通」。

凭证是临时的，**用完删掉存凭证的 JSON 文件**。

`pack_skill.py` 的 DOC_ORDER 里必须带上 scripts 自身，否则回传的版本无法还原出完整技能目录。

权限位（位掩码）：

- app_privilege（synouser）：FTP 0x01、File Station 0x02、Audio Station 0x04、
Download Station 0x08；官方示例用到 0x10（Surveillance Station）。凑不出就用各自和。
- adv privilege（synoshare 最后一个参数）：禁用目录浏览 0x1、禁止修改已有文件 0x2、
禁止下载文件 0x4。
退出码：所有工具成功返回 0，出错返回 >0。具体错误值见 references/error-codes.md。

### 常见坑

完整清单见 references/ssh-and-troubleshooting.md，最要命的三条：

- scp 上传失败 "No such file or directory" —— 客户端 OpenSSH ≥ 9.0 起旧 scp 协议被弃用，
加 `-O` 大写 O：`scp -O -P <port> file.txt myadmin@<IP>:/volume1/homes/`
- Could not chdir to home directory —— 用户主目录缺失/未启用 homes，不影响基本执行但会刷屏。
- 改了 IP 后失联 —— 改网络前确认有无带外管理通道。

### 版本差异提醒

官方 CLI 指南版权截至 2021（DSM 6 时代）。DSM 7 上部分命令行为可能变化，
一切以 references/ 之外、设备上的 --help 和官方知识库 https://kb.synology.cn/zh-cn/ 为准。
遇到本技能没覆盖或不确定的，先查该知识库，不要凭记忆下命令。

### 实测设备档案（DS918+ / DSM 7.3-81180）

在 DSM 7.3-81180 / DS918+ 上实测得出的硬结论，碰 DSM 先看这段。

> ⚠️ **本仓库是公开仓库**。档案只保留「型号 / 版本级」结论。
> 真实 IP、主机名、序列号、账号名、磁盘与网络拓扑**一律不入库**，用占位符代替。

| 项 | 值 |
|---|---|
| 型号 / 序列号 | DS918+ / `<序列号>` |
| CPU | Intel Celeron J3455 @1.5GHz，4 核 |
| 内存 | 4096 MB |
| DSM | 7.3-81180（builddate 2025/10/03），内核 4.4.302+ #81180 SMP |
| 平台 | synology_apollolake_918+ |
| SSH | 已启用（Telnet 关闭），SSH-2.0-OpenSSH_8.2，端口 22（可在 DSM 改） |
| 账号 | `<管理员账号>`，必须属 `administrators` 组，`sudo -i` → root ✓ |
| 规模 | 数十本地用户、数十共享文件夹、注册 API 逾千（现场 `synouser --get` 数） |
| 磁盘 | 多 volume，型号无关；现场看 `df -h` |
| 网络 | SSH 建议只放通内网 `<内网网段>`；公网端口按现场防火墙策略决定 |

> 使用本技能前，把自己的设备信息填进上面的占位符即可；**填的时候别提交**。

> 维护记录：2026-09-27 周度巡检 —— 本周未产生新的 SSH / DSM Web API 实测记录，
> 无新增实测设备，上表不变。

### 交付/汇报

- 执行完把实际执行的命令 + 输出摘要回给用户，改了什么要列清楚。
- 临时开的 SSH 服务，收尾时问用户要不要关掉。
