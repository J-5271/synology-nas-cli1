# DSM 系统升级与套件批量升级（官方通道实操）

> 实测机型：DS423+（geminilake_423+，Intel Celeron J4125 / 6 GB）
> 实测路径：DSM 7.2.1-69057 Update 13 → **DSM 7.4.1-90080 Update 1**（跨大版本全量安装）
> 实测日期：2026-10-24
>
> ⚠️ 本篇是**写操作**（升级会重启 NAS、装套件会改系统），动手前必须：
> ① 用户明确确认目标版本与重启时机；② 已做阵列/空间/内存检查；③ 已备份关键配置。
> 本文所有主机名、IP、路径均用占位符，实际使用时替换成自己的值。

---

## 1. 一句话路线

**别去官网找** `.pat` **直链**——官网前端不暴露下载地址，脚本拼出来的 URL 全是 404。
唯一可靠的入口是让 **DSM 自己下载**：

```
SYNO.Core.Upgrade.Server.Download.start   （空参数即可）
        ↓  DSM 后台下载
/volume1/@autoupdate/DSM_<MODEL>%2B_<build>.pat
        ↓  synoupgrade --start-force
     校验 → 解包 → updater 阶段
        ↓  SYNO.Core.System method=reboot
        ↓  重启后 configupdate
   新版本生效
```

---

## 2. 升级前检查（必做，四项全绿再动手）

```bash
cat /proc/mdstat          # 阵列：每个 md 都是 [UU]/[UUUU]，末尾 unused devices: <none>
df -h                     # / 、/volume1 、/volume2 的可用空间
free -m                   # available 内存 + swap
cat /etc/VERSION
```

判据（本次实测通过的口径）：

| **项** | **要求** | **实测值** |
| --- | --- | --- |
| 阵列 | 所有 md 满盘、状态 U、无 unused devices | md2 RAID5 [4/4] UUUU、md3 NVMe RAID1 [UU]、md0/md1 RAID1 [UUUU] |
| 空间 | `/` 至少留 600 MB，各卷留足升级包与解包空间 | `/` 626 MB、volume1 19 T、volume2 393 G |
| 内存 | available ≥ 1 GB 且有 swap 兜底 | available 1764 MB + swap 4.7 GB |
| 备份 | `/etc` + 用户 home + 套件清单已归档 | 见 §7 |

### 2.1 备份（用绝对路径，别用相对路径）

```bash
cd / && tar czf /volume2/备份/<备份目录>/etc_full.tgz etc      # ← 必须 cd / 再用绝对路径
```

⚠️ 踩坑：直接 `tar czf <相对路径> etc` 会因为工作目录不是 `/` 而只打出几十字节的空壳。
`tar` 是相对当前目录打包的，**要么 **`cd /`**，要么给绝对路径**。

---

## 3. 下载升级包（唯一的官方入口）

### 3.1 登录取 sid

```bash
curl -s "http://<NAS_IP>:5000/webapi/entry.cgi?api=SYNO.API.Auth&version=3&method=login\
&account=<管理员账号>&passwd=<密码>&session=DSM&format=sid"
```

返回 `data.sid`，后续请求带 `_sid=<sid>`。

### 3.2 先问有没有新版

```bash
curl -s ".../entry.cgi?api=SYNO.Core.Upgrade.Server&method=check&version=1&_sid=$SID"
# → {"data":{"available":true,"version":"DSM 7.4.1-90080 Update 1", ...}}
```

### 3.3 触发下载（**参数留空**）

```bash
curl -s ".../entry.cgi?api=SYNO.Core.Upgrade.Server.Download&method=start&version=1&_sid=$SID"
# → {"success":true}
```

⚠️ **`Download.start` 不需要任何参数**，传多余的参数反而会报 error 101（参数名错误）。

### 3.4 轮询进度

```bash
curl -s ".../entry.cgi?api=SYNO.Core.Upgrade.Server.Download&method=progress&version=1&_sid=$SID"
# → {"data":{"percent":42,"status":"downloading"}}
# → {"data":{"percent":100,"status":"finished"}}
```

同时看 `SYNO.Core.Upgrade` `method=status`：
`status` 会从 `downloading` → `ready_upgrade`，并带出 `patch_info`。

实测：405 MB 的包，官方通道下载约 3.5 分钟（9% → 100%）。

### 3.5 校验包

```bash
/usr/syno/sbin/synoupgrade --check-pat '/volume1/@autoupdate/DSM_<MODEL>%2B_<build>.pat'
# → {"buildnumber":90080,"productversion":"7.4.1","reboot":"now",
#    "unique":"synology_geminilake_423+","upgradetype":"dsm", ...}
```

`unique` 必须与你的机型平台一致（可从 `/proc/sys/kernel/syno_hw_version` 拿到）。

---

## 4. 启动安装：用 `--start-force`，不要用 `--patch`

### 4.1 头号坑：`--patch` 会失败，还会删掉升级包

```bash
/usr/syno/sbin/synoupgrade --patch '/volume1/@autoupdate/xxx.pat'
```

实测输出：

```json
{"data":{"has_fail":true,"result":[
  {"api":"SYNO.Core.Upgrade.Patch","method":"local_upload","success":true, ...},
  {"api":"SYNO.Core.Upgrade","method":"start","success":false,
   "error":{"code":5209,"errors":{"message":"Upgrade patch is not ready."}}}]}}
```

后续表现：

- `SYNO.Core.Upgrade.start` 在找 `/volume1/@autoupdate/Manual.<pid>.pat` —— 找不到；
- **整个** `/volume1/@autoupdate/` **目录连同已下载的 `.pat` 一起消失**；
- 系统版本纹丝不动，`Upgrade.status` 仍是 `ready_upgrade`。

根因：`--patch` 走的是「本地手工上传补丁」分支，会先做 `local_upload` 再 `start`，
两者对补丁落盘位置的约定不一致 → start 判定 patch 未就绪并回滚清理。

### 4.2 正确路径：重新下载 + `--start-force`

```bash
# 1) 重新走 §3 下载（包被删了）
# 2) 直接启动安装
/usr/syno/sbin/synoupgrade --start-force
```

实测输出（4 个 stage 全 success）：

```json
{"data":{"result":[{"data":{"result":{"skipPostAction":false,"stageResults":[
  {"stage":"verify-checksum","status":"success"},
  {"stage":"check-unique","status":"success"},
  {"stage":"run-updater-prehook","status":"success"},
  {"stage":"launch-updater","status":"success"}],"success":true}}}]}}
```

`/var/log/synoinstall.log` 尾部会看到：

```
updater.c:6847 Congratulations!! The update has been completed!! Do configupdate when next bootup.
```

⚠️ **这一步只是把更新写进** `/tmpRoot` **的升级区，还没生效** —— 必须重启。

### 4.3 `synoupgrade` 可用选项全集

```
--check                                查有没有新版本（等价于 Server.check）
--start-force                          ★ 用已下载的包强制启动安装
--patch ABSOLUTE_UPGRADE_FILE_PATH     走 local_upload 分支（实测会失败，见 §4.1）
--check-pat ABSOLUTE_UPGRADE_FILE_PATH 校验包信息
--autoupdate[=1]                       走自动更新通道
--upload-patch ABSOLUTE_UPGRADE_FILE_PATH
--start-with-extracted-patch ABSOLUTE_EXTRACTED_PATH
```

⚠️ `--get-smallupdate-info` 在没有「部分小更新」信息文件时会**报错退出**（读
`/manualupdate.small.info` 失败），这是正常的，不是环境坏了。

---

## 5. 重启（DSM 7.4 已移除 `synosystemctl`）

⚠️ **DSM 7.4 里** `/usr/syno/sbin/synosystemctl` **这个二进制不存在了**，
`synosystemctl reboot` 会报 `No such file or directory`（看起来像"没权限"，其实是文件没了）。

用 Web API：

```bash
curl -s ".../entry.cgi?api=SYNO.Core.System&method=reboot&version=1&_sid=$SID"
# → {"data":{},"success":true}
```

或用 `/usr/sbin/reboot`。

### 5.1 等它真的重启（别只看端口）

**坑：重启命令发出去后，DSM 的 5000 端口往往还连着好几分钟** ——
此时如果只用「端口能不能连」判断，会以为没重启、其实 NAS 已经在重启流程里。

正确判据是「**先看到端口断，再看到端口通**」：

```python
down_seen = False
for i in range(120):
    if port_open(5000):
        if down_seen:
            print('重启完成'); break
    else:
        down_seen = True
    time.sleep(8)
```

实测：DS423+ 从发 reboot 到版本生效约 **2.5 分钟**。

### 5.2 核验（三个地方都要对）

```bash
cat /etc/VERSION            # 机型级：buildnumber / smallfixnumber / productversion
cat /etc.defaults/VERSION   # 固件级：与上面一致才说明真的落盘了
```

```bash
curl -s ".../entry.cgi?api=SYNO.Core.System&method=info&version=1&_sid=$SID"
# → data.firmware_ver == "DSM 7.4.1-90080 Update 1"
```

再确认没有更新残留：

```bash
/usr/syno/sbin/synoupgrade --check    # 只输出 UPGRADE_CHECKNEWDSM = 已无新版本
```

---

## 6. 升级后的收尾（跨大版本必做）

### 6.1 Docker 容器不会自动拉起

⚠️ **`restart=unless-stopped` 的容器在 docker daemon 重启后不会被自动启动** ——
重启策略只在容器**已退出**的情况下管「要不要再起」，
daemon 整体重启时它会把容器标成 Exited，然后按策略判断；实测 `unless-stopped` 的
几个容器都停在 Exited，必须手动拉。

```bash
DOCKER=/var/packages/ContainerManager/target/usr/bin/docker     # ← docker 不在 PATH 里
$DOCKER ps -a --format '{{.Names}}\t{{.Status}}\t{{.Image}}'
$DOCKER start <容器名> ...
```

⚠️ `docker` **不在 PATH**，`docker: command not found` 是常态，
用绝对路径 `/var/packages/ContainerManager/target/usr/bin/docker`。

拉起后逐个确认健康：

```bash
$DOCKER ps -a --format '{{.Names}}\t{{.Status}}'
# jellyfin  Up (healthy)
# homepage  Up (healthy)
```

### 6.2 host 网络模式的容器，端口要单独验

`--network host` 的容器没有 `Ports` 映射列，要看宿主机监听：

```bash
netstat -ltn | grep -E ':26000|:7890'
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:26000/
```

### 6.3 DSM 会自动把套件升到新版本兼容版

跨大版本升级时，DSM 自己会把一批套件更新到与新 DSM 匹配的版本
（本次实测：HyperBackup 4.1.2→4.2.2、SynologyDrive 3.5.0→4.0.3、
SnapshotReplication 7.4.5→7.5.1、LogCenter 1.3.0→1.3.2、HybridShare 1.4.2→1.5.0 等）。
**别以为是自己装的** —— 升级后要重新做一遍套件版本盘点，见 §8。

### 6.4 清理

```bash
rm -f '/volume1/@autoupdate/DSM_<MODEL>%2B_<build>.pat'
rmdir '/volume1/@autoupdate' 2>/dev/null
```

### 6.5 备份别急着删

`homes` 备份动辄几十 GB，建议**观察一两周**确认系统稳定后再删。

---

## 7. 备份清单模板

```
/volume2/备份/dsm_upgrade_backup_<日期>/
├── etc_full.tgz          # tar czf 打的 /etc 全量（绝对路径）
├── homes_<用户>.tgz      # 用户 home（最大，通常几十 GB）
├── packages_before.txt   # 升级前 synopkg list
├── pkg_ids.txt           # 升级前 ls /var/packages 的包 id 列表
├── docker_conf.tgz       # 容器配置/挂载快照
└── VERSION               # 升级前 /etc/VERSION 副本
```

---

## 8. 套件（Package Center）批量升级

### 8.1 ⚠️ `synopkg checkupdateall` 在本机返回空，不可用

```bash
synopkg checkupdateall      # 返回 0 字节，别指望它
synopkg checkupdate <pkg>   # 同样空
```

**唯一可靠的盘点方式**是 `synopkg show <pkg>`，读它的 JSON 字段。

### 8.2 ⚠️ `qupgrade: true` 对同版本包也返回 true

`synopkg show` 的 `qupgrade` 字段**不能直接用** —— 它对已经是最新的包也返回 `true`
（实测 54 个包全是 "可升级"）。必须自己比版本号：

```python
def verkey(v):
    nums = re.findall(r'\d+', v or '')
    return tuple(int(x) for x in nums[:4]) if nums else (0,)

if verkey(new_ver) > verkey(cur_ver):
    ...  # 才是真需要升级
```

### 8.3 包 id 怎么拿

```bash
ls -1 /var/packages        # ✅ 这是包 id
synopkg list | cut -d: -f1 # ❌ 这是「名字-版本」，不是包 id
```

### 8.4 spk 直链模板

`synopkg show` 的 `link` 字段直接给出官方 spk 直链：

```
https://global.synologydownload.com/download/Package/spk/<包id>/<版本>/<包id>-x86_64-<版本>.spk
```

平台段不总是 `x86_64`，也有 `geminilake`（如 `StorageManager-geminilake-1.1.0-2018.spk`）。

### 8.5 安装流程（md5 校验后装）

```bash
curl -sL --max-time 3000 --retry 3 -o /volume2/tmp/pkgup/<pkg>.spk '<link>'
md5sum /volume2/tmp/pkgup/<pkg>.spk          # 与 show 返回的 md5 字段比对
synopkg install /volume2/tmp/pkgup/<pkg>.spk
```

⚠️ `synopkg install` 会重启 web service，**SSH 会短暂不可用** —— 重连即可，不是故障。

### 8.6 ⚠️ 后台跑会被杀

NAS 上的后台进程**一律活不过 SSH 会话**（实测 `setsid nohup python3 x.py &` 连日志文件
都没生成）。批量升级必须**前台分批执行**：每批控制在超时内，逐批推进。

### 8.7 ⚠️ 有些包 `synopkg show` 返回 "Package not found"

实测在 DSM 7.4 上，以下包的 `synopkg show <id>` 返回 `Package not found`，
但 `synopkg list` 里它们明明在、`synopkg status` 也是 running：

```
Chat  HybridShare  Node.js_v14  Node.js_v16
PHP7.3  PHP7.4  PHP8.0  VPNCenter  pan-xunlei-com
```

**真实版本要看** `/var/packages/<包id>/INFO`：

```bash
grep -E '^(version|os_min_ver)' /var/packages/<包id>/INFO
```

这类包不影响使用，也不影响升级盘点（只是没法用 `show` 拿 spk 直链）。

### 8.8 降级不要做

本机某包版本**高于**官方最新版时（如 UniversalViewer 本机 1.5.0-0831 > 官方 1.4.0-0712），
那是人为或特定渠道装的，**保持原样**，不要为了"对齐官方"而降级。

---

## 9. 排错速查

| **现象** | **根因** | **处理** |
| --- | --- | --- |
| 官网/脚本拼的 `.pat` 直链全 404 | 官网前端不暴露下载地址 | 走 `Server.Download.start` |
| `SYNO.Core.Upgrade.Patch.install` → error 103 | 缺必填参数 | 不用它，走 `synoupgrade --start-force` |
| `Server.Download.start` → error 101 | 传了多余参数 | 该接口**空参数**调用 |
| `--patch` 后报 5209「patch is not ready」 | local_upload 与 start 落盘约定不一致 | 重新下载后用 `--start-force` |
| `--patch` 后 `@autoupdate` 整个目录消失 | 失败回滚时清理了升级包 | 重新 `Server.Download.start` |
| `--check-pat` 通过但版本没变 | 只写进 `/tmpRoot` 升级区，没重启 | `SYNO.Core.System method=reboot` |
| `synosystemctl: No such file or directory` | DSM 7.4 移除了该二进制 | 用 Web API reboot |
| 端口一直通、以为没重启 | DSM 5000 端口在重启流程里仍会连上 | 判据改成「先断后通」 |
| 容器升级后全 Exited | `unless-stopped` 不覆盖 daemon 重启场景 | 逐个 `docker start` |
| `docker: command not found` | 不在 PATH | 用 `/var/packages/ContainerManager/target/usr/bin/docker` |
| `synopkg checkupdateall` 无输出 | 本机该命令不可用 | 改用 `synopkg show` 逐包盘点 |

| **现象** | **根因** | **处理** |
| --- | --- | --- |
| 54 个包都显示可升级 | `qupgrade` 对同版本也返回 true | 自己比版本号 |
| `synopkg list` 得到的名字装不上 | 那是「名字-版本」不是包 id | `ls /var/packages` |
| `tar czf` 只打出几十字节 | 相对路径打包 | `cd /` 后用绝对路径 |
| 后台脚本跑着跑着没了 | SSH 会话结束即清理 | 前台分批执行 |

---

## 10. API 速查

| **API** | **method** | **用途** | **关键返回** |
| --- | --- | --- | --- |
| `SYNO.API.Auth` | `login`（version=3） | 取 sid | `data.sid` |
| `SYNO.Core.Upgrade.Server` | `check` | 查可升级版本 | `data.version` / `data.available` |
| `SYNO.Core.Upgrade.Server.Download` | `start`（**空参数**） | 触发官方通道下载 | `success` |
| `SYNO.Core.Upgrade.Server.Download` | `progress` | 下载进度 | `data.percent` / `data.status` |
| `SYNO.Core.Upgrade` | `status` | 升级总状态 | `data.status`（`downloading`→`ready_upgrade`）/ `data.patch_info` |
| `SYNO.Core.Upgrade.Patch` | `install` | ❌ 实测报 103，别用 | — |
| `SYNO.Core.System` | `info` | 固件版本 | `data.firmware_ver` |
| `SYNO.Core.System` | `reboot` | **重启 NAS** | `success` |

DSM 全部 API 约 1297 个，更新相关的约 37 个（`SYNO.Core.Upgrade.*` 系列），
可用 `api=SYNO.API.Info` + `query=upgrade` 之类枚举。

---

## 11. 相关文档

- `references/package-install.md` —— 套件**离线**安装（NAS 连不上 CDN 时的路线）
- `references/browser-automation.md` —— 浏览器兜底（装 DSM、建共享文件夹）
- `references/dsm-deployment-guide.md` —— 新机开荒（装 DSM 的前置准备）
- `references/error-codes.md` —— 错误码对照表
- `references/ssh-and-troubleshooting.md` —— SSH 通道故障排查
