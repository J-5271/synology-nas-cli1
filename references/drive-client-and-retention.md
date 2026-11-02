# Drive 客户端与「上传后删本地」（实测参考）

> 场景：要用群晖 Drive 把本机目录传到 NAS，**上传确认无误后把本地副本删掉**省空间。
> 这条路有两类致命坑：**任务类型选错会反删服务器**，**任务删错会把本地源目录清空**。
> 本文给的是先自证任务方向性、再逐文件取证、最后安全删除的完整做法。
>
> 全部结论来自 DS918+ / DSM 7.3-81180 + Windows 10（PowerShell 5.1）上的实测，
> 以及 2026-10-26 一次真实数据清空事故的复盘。
> 示例一律占位：`<NAS_IP>`、`10.x.x.x`、`<账号>`、`<共享文件夹>`。
> 相关脚本：无（本篇是纯运维参考）；API 调用见 `scripts/dsm_api.py`。

---

## 一、Drive 客户端在 Windows 上的真实落点

**结论：装用户目录、进程不叫 synology、版本要从注册表读。** 按常规思路找会连踩三个空。

| 项 | 实际值 |
| --- | --- |
| 安装目录 | `%LOCALAPPDATA%\SynologyDrive\SynologyDrive.app\bin` |
| **不在** | `C:\Program Files\Synology...`（那些目录不存在） |
| 进程名 | `cloud-drive-ui.exe` / `cloud-drive-daemon.exe` / `cloud-drive-connect.exe` |
| 配置库 | `%LOCALAPPDATA%\SynologyDrive\data\db\sys.sqlite` |
| 日志 | `%LOCALAPPDATA%\SynologyDrive\log\daemon.log` |
| 实测版本 | `8.0.3.17892` |

⚠️ **按** `synology*` **关键字查进程一定漏判。** 三个进程名都以 `cloud-drive-` 开头，
用 `Get-Process synology*` 或 `tasklist | findstr /i synology` 会返回空，
从而误判「客户端没在跑」。正确写法：

```powershell
Get-Process cloud-drive*  -ErrorAction SilentlyContinue |
  Select-Object Id, ProcessName, Path
```

⚠️ **`Get-Item ...exe).VersionInfo` 是空的。** 这几个 exe 不带版本资源，
`FileVersion` / `ProductVersion` 全为空。版本只能从卸载注册表读：

```powershell
Get-ItemProperty HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\* `
  -ErrorAction SilentlyContinue |
  Where-Object { $_.DisplayName -like '*Synology Drive*' } |
  Select-Object DisplayName, DisplayVersion
# → Synology Drive Client (remove only)   8.0.3.17892
```

⚠️ **日志目录是 `log`，不是 `data\logs`。** 网上与部分旧文档写 `data\logs\daemon.log`，
本机实测不存在该路径，直接 `Get-Content` 会报「找不到路径」。
`data` 下只有 `config` / `db` / `session` / `tmp` / `cert*` 等目录，日志在**同级**的 `log`。

### 1.1 配置库：四张表管全部状态

`sys.sqlite` 是 SQLite，**客户端运行时会持锁**。只读查证请用 `immutable=1` 打开，
避免加锁干扰客户端同步：

```bash
# 注意：客户端在跑时不要用写模式打开，容易和同步进程抢锁
sqlite3 "file:%LOCALAPPDATA%\SynologyDrive\data\db\sys.sqlite?immutable=1" ".tables"
```

| 表 | 管什么 | 关键字段 |
| --- | --- | --- |
| `connection_table` | 连接（一个 NAS 一行） | `server_ip`、`server_port`(6690)、`username`、`ds_id`、`session`、`use_ssl` |
| `session_table` | 同步 / 备份任务 | `id`、`conn_id`、`share_name`、`remote_path`、`session_type`、`sync_direction`、`ignore_local_remove` |
| `backup_plan_table` | 备份计划 | `task_id`、`backup_mode`（**1=手动 / 0=连续**）、`backup_status`、`backup_days`、`backup_times`、`do_missing_backup` |
| `server_view_table` | 该连接可见的共享文件夹 | `view_id`、`conn_id`、`name`、`privilege` |

> `session_table` 与 `backup_plan_table` 是**一条任务两处记录**：
> 任务本体在 `session_table`（id 与 conn_id 数值常常相同，别拿它当外键猜），
> 备份任务的调度参数在 `backup_plan_table`（`task_id` 对应 session id）。

---

## 二、同步任务 vs 备份任务（全篇最重要的一节）

**结论：必须是单向任务（`sync_direction=1` + **`ignore_local_remove=1`**）。双向同步等于把刚上传的成果亲手删掉。**
本项目最终采用**备份任务**：它在语义上最干净（删除意图不会被同步逻辑解释成一次变更），
代价是目的地只能落在 `home/Backup/<设备名>` 之下，见 2.2 末尾的取舍说明。

两者的差别不在界面上（都是「选个本地文件夹 → 选个服务器文件夹」），
而在**删除语义**：双向同步会把「本地没了」当成一次变更，同步到服务器上。

### 2.1 语义差异

| 任务 | `session_type` | `sync_direction` | `ignore_local_remove` | 本地删除后服务器 |
| --- | --- | --- | --- | --- |
| 同步（双向） | 1 | 0 | 0 | **副本一并被删** |
| 备份（单向） | 2 | 1 | 1 | 副本保留，MD5 不变 |

- `sync_direction`：**0 = 双向 / 1 = 仅上传 / 2 = 仅下载**
- `ignore_local_remove`：仅对 `sync_direction=1` 生效，默认 1 = 「本地删了不映射到服务器」

### 2.2 用 sqlite 自证方向性

建完任务**先查一遍再传第一个字节**，这是唯一不可妥协的一步：

```bash
sqlite3 "%LOCALAPPDATA%\SynologyDrive\data\db\sys.sqlite" \
  "select id, session_type, sync_direction, ignore_local_remove from session_table;"
```

实测输出（一台机器上同时存在两种任务，正好做对照）：

```
4|1|0|0     ← 同步（双向），本地删 = 服务器删
5|1|0|0     ← 同步（双向）
7|2|1|1     ← 备份（单向·仅上传），本地删不影响服务器
```

要连路径一起看，把四列扩成全貌：

```bash
sqlite3 "%LOCALAPPDATA%\SynologyDrive\data\db\sys.sqlite" \
  "select id, conn_id, share_name, remote_path, session_type, sync_direction from session_table;"
```

```
4|4|海草海草|/|1|0
5|5|home|/|1|0
7|7|home|/Backup/SY_TG/C/Users/<账号>/Desktop/test/|2|1
```

> 第 7 行就是备份任务：`share_name=home` + `remote_path=/Backup/SY_TG/...`。
> **备份任务的目的地只能落在** `home/Backup/<设备名>/` **下面**，
> 迁不到任意团队文件夹——要「指定团队文件夹子目录 + 单向」，用同步任务并把
> `sync_direction` 设成 1、`ignore_local_remove` 保持 1（默认值），Mass Deploy 配置里
> `sharefolder`=团队文件夹名、`remote_path`="/子目录"、`sync_direction`=1。

### 2.3 日志旁证

不想动数据库时，`daemon.log` 里也有方向标识：

```bash
grep -a "is ONE_WAY_UPLOAD" "%LOCALAPPDATA%\SynologyDrive\log\daemon.log"
# 2026-10-26T... Session 7 is ONE_WAY_UPLOAD
```

出现 `Session N is ONE_WAY_UPLOAD` 即该任务是仅上传。**没有这行的一律按双向对待**，
不要靠界面上的箭头图标判断。

---

## 三、⚠️ 危险操作：删除 Drive 任务会连带删本地文件

**结论：删除「同步任务」这个动作本身是破坏性的。动任务前先把源目录备份出来。**

### 3.1 真实事故（2026-10-26 14:01–14:02，DS918+）

| 时刻 | 事件 |
| --- | --- |
| 14:01:xx | 在 Drive Client 里删除「同步任务」（session #6） |
| 14:02:10 | 删除向导勾选了「**同时删除本地文件**」→ `recycle-cleaner` 清空源目录 |
| 14:02:11 | 备份任务（session #7）启动，扫到的是已消失的空壳 |
| 14:02:11 | 日志：`file_size: 0`、`file_mtime: 0` 的幽灵条目 |
| 14:0x | 上传结果：**0 个文件** |

**后果**：源目录 8 个文件、1.21 GB，在 1 分钟内全部消失。

**日志原文**（`daemon.log`，一字不改地引用，可作为排查锚点）：

```
upload-local-handler.cpp(449): Worker (3193): Path '...\FreeCAD-...-installer-1.exe' cannot be uploaded. (vanish)
upload-local-handler.cpp(449): Worker (3196): Path '...\SteamSetup.exe' cannot be uploaded. (vanish)
upload-local-handler.cpp(449): Worker (3197): Path '...\UbisoftConnectInstaller.exe' cannot be uploaded. (vanish)
```

数据最后从服务器 `/volume1/测试文件夹2` 找回，8 个文件合计 1,207,603,124 字节，逐个尺寸吻合。

### 3.2 为什么这个坑特别容易踩

① **向导那句话和业务诉求字面几乎一样。** 「是否同时删除本地文件」——
而用户的目标本来就是「上传完成后删本地文件」。两句话读起来是同一件事，
一个是**立即无条件删除**，一个是**校验通过后按策略删除**，但界面上分不出来。

② **备份任务遇到幽灵条目只静默跳过，不报错退出。** 上表 14:02:11 那几条
`(vanish)` 全是 `[INFO]` 级别，任务状态照常显示「正常」，
唯一能看出来的地方是**上传计数为 0**。

③ 因此必须由**外部脚本**检测「落地数为 0」，见第七节的「空落地守卫」。

### 3.3 三条操作约束

1. **动任何 Drive 任务之前，先把源目录整体备份到别处**（哪怕只是 `robocopy /MIR` 到另一个盘）。
2. **删除任务时，向导里「同时删除本地文件」一律不勾。** 想清本地就走本节第七节的可控流程。
3. **绝不用「本地文件还在」证明「文件没传上去/传上去了」。** 产龄、图标、大小不变，
全部不能作为删除依据——事故里那 8 个文件在删除前一切都「正常」。

---

## 四、FileStation API 取证契约

逐文件确认「服务器上真的有这个文件、内容一致」时，只能走 FileStation（或 SSH）。
以下是踩过的坑，逐条列清。**每一条都是先按直觉写、被真实返回打回来后修正的。**

### 4.1 `SYNO.API.Auth`：v7 不通，要从 v6 往下退

- `version=6` 的 `login` 可用，参数 `session=FileStation&format=sid`
- **`version=7` 直接返回** `103`（API 版本不存在）
- 处理：v7 → v6 → v3 逐个回退。别只信 `SYNO.API.Info` 报的 `maxVersion`
（与 `references/dsm-web-api.md` 第一节同一个结论）

### 4.2 `SYNO.FileStation.List` v2：四个参数陷阱

| 参数 | 正确写法 | 错误写法与后果 |
| --- | --- | --- |
| `additional` | **JSON 数组字符串** `["size","time"]` | 逗号串 `size,time` → 取不到字段 |
| `additional` | 只列真实存在的扩展项 | 传 `checksum` → **List 根本没有这个选项** |
| 时间字段 | 读 `additional.time.mtime` | 读 `modify_time` → 永远 undefined |
| `size` | 可能是**字符串**，必须 `int()` | 直接比较 → `'1024' == 1024` 恒假 |

- `checksum` 不是 List 的 `additional` 选项，**MD5 必须走独立的** `SYNO.FileStation.MD5`（见 4.3）
- 建议固定带上 `filetype=file`（排除目录）与 `limit=0`（不截断）

⚠️ **`additional` 少写** `size` **时不会报错**，只是返回里没有 size——
典型的**静默降级**：校验逻辑拿不到 size 就跳过比对，
看起来「校验通过」，实际什么都没校验。

```python
# 正确
params = {
    "api": "SYNO.FileStation.List", "version": "2", "method": "list",
    "folder_path": "/home/Backup/<设备名>/<子目录>",   # 共享文件夹视角，见第六节
    "additional": json.dumps(["size", "time"]),        # JSON 数组字符串
    "filetype": "file", "limit": "0", "_sid": sid,
}
# 返回: data.files[i].size （可能是 str，转 int）
#       data.files[i].additional.time.mtime
```

### 4.3 `SYNO.FileStation.MD5` v2：start → status 两段式

```
start  拿到 taskid
  ↓
status 轮询直到 status == finished
  ↓
读 data.md5
```

### 4.4 ⚠️ `code 400` 不是「路径不存在 / 没权限」

**这是本篇最容易把运维带偏的一条。**

现象：**同一路径、同一参数、同一 sid**，连续多次返回 400；过一分钟重跑就成功。
同期还出现过一次 `502`。

曾据此下的错误结论是「账号没有该共享文件夹的 ACL」——
被推翻的依据是：**同一账号、同一路径，结果不一致**。
自写客户端稳定成功、别的客户端稳定失败、压力测试 30/30 与 15/15 又都成功，
随后再冒 502。这是 DSM 的**负载型偶发**，不是权限。

**判据只有一条**：`同一账号 + 同一路径` 的结果是否不一致。不一致 → 偶发，不是权限。

**处理：所有 list / MD5 请求都包指数退避重试**，可重试码集合固定为

```
{400, 402, 406, 407, 500, 502, 503}
```

重试耗尽仍失败时，报错文案要**同时给「稍后重跑」和「查共享文件夹权限」两条路径**，
不能只写「权限不足」——那会把运维引向完全错误的方向。

**绝不能把首次 400 当路径不存在去改权限或改路径。**

### 4.5 ⚠️ `MD5 status` 随机返回 `599`（task not found）

- 599 会**随机出现**，与轮询延迟无关（已验证 0 / 0.3 / 0.5 / 1 / 2 秒各 3 次，仍随机）
- **重试同一个** `taskid` **无效** —— 任务已经丢了，再问也是 599
- 正确处理：**重新发** `start` **拿新 taskid**，继续轮询到总超时

---

## 五、Drive API 不能做逐文件校验（明确的能力边界）

**结论：逐文件取证只能走 FileStation 或 SSH，没有第三条路。**

两条 Drive API 都试过，都不可用：

| API | 实测结果 |
| --- | --- |
| `SYNO.SynologyDrive.Files` `list` | 返回 `code 1000 list node failed` |
| `SYNO.SynologyDrive.Node` `list` | **忽略** `path` **参数**，永远返回同一批根节点 |

`SYNO.SynologyDrive.Node list` 尤其容易误用：它不报错、有数据返回，
但传任何 path 都返回同一组根节点（"My Drive" 的 `absolute_path` 是 `/Drive`），
所以拿它判「目录里有没有这个文件」会**永远得到同一个答案**。

另注：`SYNO.SynologyDrive.*` 家族在 Server 端注册完整，能查配额、版本、团队文件夹等，
**只是没有「按路径列文件 + 校验内容」的能力**。别在 API 注册表里看到名字就以为能列目录。

---

## 六、两条通道的路径视角不同

**结论：同一个文件，FileStation 和 SSH 看到的路径写法不一样。配错必然「服务器一个文件都找不到」。**

| 通道 | 视角 | 例 |
| --- | --- | --- |
| FileStation | 共享文件夹视角 | `/home/Backup/xxx` |
| SSH | 真实文件系统 | `/volume1/homes/<账号>/Backup/xxx` |

- FileStation 的 `folder_path` **以共享文件夹名开头**，没有 `/volume1`
- SSH 看到的是卷路径，`homes` 共享对应 `/volume1/homes`
- 两者不只是前缀差异：**卷号（`/volume1` 还是 **`/volume2`**）在 FileStation 视角里完全不可见**，
只有 SSH 或 `df` 才看得到

> 换算规则：FileStation 的 `/<共享名>/<相对路径>`
> → SSH 的 `/volume<N>/<共享的实际挂载点>/<相对路径>`
> `homes` 这类特殊共享的挂载点是 `/volume<N>/homes`，不是 `/volume<N>/homes_shared`。
> 拿不准就先 SSH 跑 `df -h` / `ls /volume1` 对一遍，别猜卷号。

⚠️ 顺带一个本地坑：**Git Bash / MSYS 会改写** `/volume1/...` **这类参数**，
传参前 `export MSYS_NO_PATHCONV=1`（与 `SKILL.md` 常见坑一节同一条）。

---

## 七、安全删除的可复用模式

把「上传确认后按 N 天删本地」做成可复用做法，不绑定任何具体脚本实现。
**核心：删除的授权只来自「服务器侧内容实锤」，不来自「本地文件看着传完了」。**

### 7.1 判定只有一条硬闸门

满足全部条件才允许移动/删除：

1. 服务器侧 **size 相等**
2. 服务器侧 **MD5 相等**
3. 本地 `mtime` 已**静止超过稳定窗口**（还在写入的文件不参与判定）

任一条不满足 → 不删、不记账、下轮重试。**没有「差不多」「大小对了就行」这一档。**

### 7.2 `verified_at` 的计时起点与重置

- 计时起点取「**服务器校验通过的时刻**」，不是文件创建时间、不是上传开始时间
- 内容指纹 `size + mtime_ns` **或** 远端 MD5 一旦变化 → **`verified_at` 必须重置**

⚠️ 只比「内容 MD5 有没有变」是不够的：文件内容 A → B → A 时，
比 MD5 会认为「没变」而沿用最早的 `verified_at`，导致**提前删除**。
用 `mtime_ns`（纳秒）做指纹才能捕捉到回退。

### 7.3 删除前必须做 TOCTOU 双端复检

从「校验通过」到「真正删除」之间存在时间窗，两端都可能变：

- **本地**：重新 `stat` + **重算 MD5**
- **远端**：重新取 size / MD5

只复检 size 是不够的——同尺寸改写会被放过。任一端变化 → 本轮放弃。

### 7.4 三阶段状态机：`verified_at → staged_at → purged_at`

| 阶段 | 动作 | 保证 |
| --- | --- | --- |
| `verified_at` | 记录校验通过时刻与指纹 | 计时起点可信 |
| `staged_at` | **移入暂存目录**（不是原地删） | 宽限期内可回滚，幂等、断电可恢复 |
| `purged_at` | 宽限期后从暂存真正删除 | 删除动作最小化 |

- **移入暂存**而不是直接 `remove`，是为了让「删错了」有救
- 状态机要**幂等**：同一文件被处理两次不会产生两条记录或二次删除
- 断电恢复后从 `manifest.json` 续跑，不存在「半删」状态

### 7.5 purge 前用 realpath 白名单校验

暂存路径来自 `manifest.json`，而 `manifest.json` 是**可被篡改的普通文件**。
purge 前必须：

1. 对暂存路径取 **realpath**（解析符号链接与 `..`）
2. 断言它仍在暂存目录前缀之下

否则一条被改过的记录就能让脚本删掉任意文件。

```python
# 示意：realpath + 前缀断言，两个都不能省
target = os.path.realpath(entry["staged_path"])
if not target.startswith(os.path.realpath(stage_dir) + os.sep):
    raise RuntimeError("purge 路径越界，拒绝执行")
```

### 7.6 暂存同名一律追加后缀

同一文件名的第二个副本进暂存时，**追加时间后缀，绝不覆盖**。
覆盖会让宽限期内的「可回滚」变成假的——回滚拿到的其实是新文件。

### 7.7 dry-run 必须是默认值

默认只报告不删除，需显式 `--apply` / `-Apply` 才动文件。
另外 `--apply` 遇到明文 HTTP 应当**直接拒绝**（HTTP 下 checksum 可被中间人伪造，
校验闸门形同虚设），要 HTTP 必须再加一个显式的 `--allow-http`。

### 7.8 空落地守卫（用「合格候选数」做前置条件）

**本地有候选文件，但服务器命中为 0 → 必须告警，绝不能继续删。**
这正是第三节事故里缺的那道闸。

但前置条件必须是「**已通过稳定窗口、真正进入校验流程的候选数**」（下称 `eligible`），
不能直接用「本地文件数」：

| 条件 | 判定 | 语义 |
| --- | --- | --- |
| `eligible > 0` 且 `server_hit == 0` | **ALERT 并停止** | 备份任务空转 / 路径映射错 |
| `eligible > 0` 且 `verified == 0` 但 `server_hit > 0` | **ALERT** | 命中了但内容不一致，可能还在传 |
| `eligible == 0`（新文件都在稳定窗口内） | 正常跳过，**不告警** | 否则每来一批新文件就误报一次 |

⚠️ 用「本地文件数」当条件会**误报**：新文件因稳定窗口未满根本没进入校验，
却依然触发「服务器一个都没有」的告警。误报几次之后运维就对告警脱敏了，
真出事那天没人看——守卫等于不存在。

---

## 八、维护记录

- 2026-10-26 首次整理。来源：DS918+ / DSM 7.3-81180 + Drive Client 8.0.3.17892 上的
实测（配置库字段、日志字符串、FileStation 契约逐条验证）与一次 P0 级数据清空事故复盘。
  - 版本号 `8.0.3.17892` 取自卸载注册表 `DisplayVersion`（exe 无版本资源，读不到）。
  - 日志路径校正为 `%LOCALAPPDATA%\SynologyDrive\log\daemon.log`（不是 `data\logs`）。
  - 已实测的账号 / IP 一律未入库，全部替换为占位符。
