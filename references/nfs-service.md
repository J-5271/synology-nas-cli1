# NFS 文件服务（导出管理 · 客户端验证 · Windows 落地）

> 本文结论中标注「实测」的部分，来自 DS918+ / DSM 7.3-81180 与 RS6426xs+ / DSM 7.4.1-90080 两台设备。
> 未实测的内容会显式标注「未验证」。机型 / DSM 版本差异大，动手前先 `--help` 与官方知识库复核。
>
> **脱敏**：本文所有示例用 `<NAS_IP>` `<内网网段>` 占位，不含真实 IP / 账号 / 序列号。
> 配套脚本：`scripts/nas_nfs.py`（导出规则读写）、`scripts/nfs3_client.py`（NFSv3 客户端与基准）。

---

## 一、先搞清楚「NFS 到底有没有导出」

### 1.1 最大的坑：`/etc/exports` 里没有 ≠ NFS 没开

实测（DSM 7.4.1）：一台 NAS 的 `/etc/exports` 里只列了 `nas-ssd` / `nas-ssd2`，
看起来「home 没有 NFS 导出」。但 **NFS 服务本身是开着的**（nfsd 在 `:2049` 监听、rpcbind 在 `:111`），
只是那个共享确实没有导出规则。

判据顺序：

```bash
# ① 服务是否在跑（只读）
netstat -lntp | grep -E ':2049|:111'
cat /proc/fs/nfsd/threads          # 存在且有值 = nfsd 已启动
# ② 真正生效的导出表（要看导出选项必须 sudo）
sudo exportfs -v
```

> `/etc/exports` 在 DSM 7 上**普通管理员账号读不到**（Permission denied），
> 而且它不一定是权威来源 —— 权威来源是 `exportfs -v` 与 DSM 的共享文件夹 NFS 权限设置。

### 1.2 用 Web API 查某个共享的 NFS 规则

```
api     SYNO.Core.FileServ.NFS.SharePrivilege
version 1
method  load      （只读）
参数    share_name=<共享文件夹名>
```

返回里的 `rule`：

| `rule` 的值 | 含义 |
|---|---|
| `[]`（空数组） | **该共享没有 NFS 导出规则** ← 最容易被忽略的状态 |
| 非空数组 | 每条对应一个客户端网段 / 主机与它的权限 |

也就是说：**查 `/etc/exports` 里没有，仍要用这个 API 确认一次 `rule` 是否为空数组**，
才知道到底是「服务没开」还是「共享没导出」。

### 1.3 写入导出规则（改配置，走只读优先红线）

```
api     SYNO.Core.FileServ.NFS.SharePrivilege
version 1
method  save
参数    share_name=<共享文件夹名>
        rule=<JSON 数组的字符串>
```

实测要点（DSM 7.4.1）：

- 参数名是 **`rule`**，不是 `rules` / `privilege` / `share_privilege`。写错参数名不报错，规则也不会生效。
- 只有 `load` / `save` 两个方法，**没有 `add` / `delete`**。改规则 = 读出全量 → 改数组 → 整体 `save` 回去。
- `rule` 数组元素的实际字段：

```json
[{
  "async": true,
  "client": "<内网网段>",             
  "crossmnt": true,
  "insecure": true,
  "privilege": "rw",                  // rw | ro
  "root_squash": "root",              // root（no_root_squash）| nobody
  "security_flavor": {
    "kerberos": false,
    "kerberos_integrity": false,
    "kerberos_privacy": false,
    "sys": true                       // AUTH_SYS
  }
}]
```

- `client` 可以是 `*`（任意主机）或具体 IP / 网段。**能收窄就收窄**，别图省事写 `*`。
- 写入后立即用 `exportfs -v` 复核，确认选项与预期一致。
- 用 `scripts/nas_nfs.py` 一把梭：

```bash
export DSM_HOST="http://<NAS_IP>:5000" DSM_ACCOUNT=<账号> DSM_PASSWORD='<密码>'
python3 scripts/nas_nfs.py list                      # 只读：列出所有共享的 NFS 导出规则
python3 scripts/nas_nfs.py list   --share <共享名>    # 只读：看单个共享
python3 scripts/nas_nfs.py set    --share <共享名> --client <网段或IP> --privilege rw --yes
python3 scripts/nas_nfs.py revert --share <共享名> --yes   # 清空该共享的规则（回滚到「未导出」）
```

### 1.4 导出选项里几个容易误读的词

| 选项 | 含义 | 注意 |
|---|---|---|
| `async` | 服务端**允许**先回包再落盘 | 见下方「四、写语义」——实测 Synology nfsd 并不真给写回 |
| `no_wdelay` | 仅在检测到相关写时才延迟提交 | 对顺序大块基本无影响 |
| `insecure` | 允许客户端使用 > 1024 的源端口 | Windows / 多数客户端需要，不要去掉 |
| `crossmnt` | 允许跨越子挂载点 | 一般保留 |
| `no_root_squash` | root 客户端不被降权 | **安全面**：会放大误配置的影响，按需开 |
| `anonuid` / `anongid` | 匿名（AUTH_NULL / 未映射）访问时的 UID/GID | 决定「不传凭据」时以什么身份落盘 |

---

## 二、NFS 挂载验证：客户端侧

### 2.1 Windows 没有 NFS 客户端时怎么办（实测）

现象：Windows Server / Win10 默认**不带** NFS 客户端。检查这几处都是空的就说明没装：

```
C:\Windows\System32\mount.exe
C:\Windows\System32\nfsadmin.exe
C:\Windows\System32\drivers\nfsclnt.sys
C:\Windows\System32\drivers\msnfsflt.sys
```

装它需要管理员权限 + 联网/安装源：

```powershell
Enable-WindowsOptionalFeature -Online -FeatureName ServicesForNFS-ClientOnly,ClientForNFS-Infrastructure -All
nfsadmin client stop
nfsadmin client start
```

> 实测：**在权限受限的会话里（进程非管理员、`Start-Process -Verb RunAs` 被安全策略拦截）
> 这条路走不通**，而且连 `Start-Process cmd.exe -Verb RunAs` 都会被挡。
> 此时要么请用户手工提权执行上面的命令，要么走 2.2 的绕行方案先验证 NAS 侧是否正常。

### 2.2 绕行：纯 Python NFSv3 客户端（不装任何驱动、不要管理员）

`scripts/nfs3_client.py` 用 ONC-RPC over TCP + XDR 直接实现 NFSv3，**只需要发一个 TCP 连接**，
无需系统 NFS 栈、无需提权。它是排查「问题在 NAS 还是在客户端」的关键工具。

```bash
# 挂载验证：EXPORT / MNT / GETATTR / READDIR / LOOKUP / CREATE / WRITE / 回读校验 / REMOVE
python3 scripts/nfs3_client.py verify --host <NAS_IP> --export /volume2/<共享名> --subdir <子目录>

# 探测服务端允许的单次 READ 上限（rsize）
python3 scripts/nfs3_client.py rsize  --host <NAS_IP> --export /volume2/<共享名> --file <大文件>

# 性能：顺序读 / 顺序写 / 随机读 / 延迟
python3 scripts/nfs3_client.py read-sweep     --host <NAS_IP> --export /volume2/<共享名> --subdir <目录> \
    --file <大文件> --size-mib 8192 --sweep 1,4,8,16
python3 scripts/nfs3_client.py write-sweep    --host <NAS_IP> --export /volume2/<共享名> --subdir <目录> \
    --size-mib 8192 --sweep 1,4,16 [--unstable]
python3 scripts/nfs3_client.py randread-sweep --host <NAS_IP> --export /volume2/<共享名> --subdir <目录> \
    --file <大文件> --size-mib 16384 --io-kib 32 --sweep 1,4,8,16 --count 2000
python3 scripts/nfs3_client.py lat            --host <NAS_IP> --export /volume2/<共享名> --subdir <目录>
```

AUTH_SYS 身份用 `--uid` / `--gid` 指定（默认 `1026` / `100`，即 DSM 上典型的 `administrators` 用户）。
**权限不足时不是「连不上」，而是 MNT / LOOKUP 返回状态码**，见 2.4。

### 2.3 NFSv3 协议要点（自己写客户端必须知道的）

调用链（全部 over TCP，端口先从 rpcbind 查）：

```
rpcbind  :111        PORTMAP(v2) GETPORT  ->  mountd 端口（动态）+ nfsd 端口（通常 2049）
mountd   :动态        MOUNT(v3)   EXPORT   -> 列出导出
                     MOUNT(v3)   MNT      -> 取根 filehandle
nfsd     :2049       NFS(v3)     GETATTR / LOOKUP / READDIR / READ / CREATE / WRITE / COMMIT / REMOVE
```

实测踩到的坑，按「最浪费时间」排序：

1. **RPC 头里含 `proc`（过程号），绝不能跨过程复用缓存。**
   把 RPC 头缓存起来只改 xid 会导致 `MNT`(proc=1) 被当成 `EXPORT`(proc=5) 发出去，
   服务端按 EXPORT 解析、把导出列表的第一个字段（布尔 1）当状态码返回 →
   客户端看到的是 `MNT 失败 status=1`（`MNT3ERR_PERM`），**看起来像权限问题，实际是请求错了**。
   定位办法：把 `sendall` 的字节流抓下来，和正确实现的请求逐字节对比。
2. **`CREATE` 的返回是 `post_op_fh3`：`diropres3` 里先有一个布尔「是否跟随 filehandle」，再是 filehandle。**
   漏读这个布尔位，后续 `WRITE` 会带着错位的 filehandle，报 `status=10001`。
3. **单次 `WRITE` 超过服务端上限会被直接 RST，不是返回错误码。**
   实测 DS918+ 上一次写 4 MiB 会让连接被复位（客户端 `WinError 10053`）。
   `rsize` / `wsize` 上限实测为 **1 MiB（1048576）**，按 1 MiB 分块即可。
4. **RPC over TCP 的记录标记可以多片段**：4 字节 marker 的最高位是「最后一片」标志。
   只读一次 4 字节 marker 就假设单片段，在 1 MiB 级 READ 上会偶发解析错位。
5. **`READDIR` 要翻页**：`cookie` + `cookieverf`，直到 `eof=true`。
6. **AUTH_SYS 要带 `uid` / `gid` / `gids` 数组**，`gids` 至少包含 `100(users)`；
   走 AUTH_NULL 会落到导出选项的 `anonuid/anongid`。

### 2.4 NFS 状态码（troubleshooting 用）

| 层 | 码 | 含义 | 常见原因 |
|---|---|---|---|
| MOUNT | 1 | `MNT3ERR_PERM` | 请求本身错了（见 2.3-①）、或该客户端不在导出规则里 |
| MOUNT | 2 | `MNT3ERR_NOENT` | 导出路径写错（**`/volume1/homes` ≠ `\\NAS\home`**） |
| MOUNT | 13 | `MNT3ERR_ACCES` | 路径被 Git Bash 之类改写了（见 5.3） |
| NFS | 2 | `NFS3ERR_NOENT` | 文件名不存在 |
| NFS | 13 | `NFS3ERR_ACCES` | UNIX 权限不足（见第三节） |
| NFS | 20 | `NFS3ERR_NOTDIR` | 对文件用了目录操作 |
| NFS | 22 | `NFS3ERR_INVAL` | 参数非法（如 count 超上限） |
| NFS | 10001 | `NFS3ERR_BADHANDLE` | filehandle 解析错位（见 2.3-②） |

---

## 三、UNIX 权限与 UID 映射（NFS 独有的坑）

NFSv3 的身份就是 `uid` / `gid` 数字，**没有名字映射、没有 Windows ACL**。所以：

- 实测 `/volume1/homes` 与每个用户目录权限是 **`711 (drwx--x--x)`**：
  非属主**能穿越、不能列目录、不能写**。想访问就必须让客户端提供**匹配的 UID**。
- 共享文件夹里的目录如果是 `777`，则任何人可读写，没有 UID 障碍。
- `administrators` 组用户在 DSM 上通常是 `uid=1026(<管理员账号>) gid=100(users) groups=100,101`。
  先用 SSH `id` 确认，不要猜。

**决策含义**：要按用户隔离的 NFS 挂载（「每人挂自己的 home」），必须在客户端能按登录用户切换 UID 才行。
Windows 的 Client for NFS **做不到**——见下节。

---

## 四、写语义：`FILE_SYNC` vs `UNSTABLE`（影响所有写性能数字）

NFSv3 的 `WRITE` 请求带一个 `stable_how`：

| 值 | 语义 | 服务端行为 |
|---|---|---|
| `UNSTABLE (0)` | 写回 | 可以先放缓存，客户端之后发 `COMMIT` |
| `DATA_SYNC (1)` | 数据落盘（元数据可延后） | — |
| `FILE_SYNC (2)` | 数据 + 元数据落盘后才回包 | **默认语义，也是最慢的** |

实测（DSM 7.4.1）：把 `WRITE` 换成 `UNSTABLE` + 结尾一个 `COMMIT`，
**吞吐不升反降**，而且 `COMMIT` 在 0.00 s 内返回。
说明 **Synology 的 nfsd 并没有真给 `UNSTABLE` 开写回**，导出选项里的 `async` 对这段路径不起作用。

> **这条结论很重要**：它意味着
> **NFS 写入的数字天然就是「持久化口径」，比同盘 SMB 的数字低是正常的，不是 NFS 慢。**
> 拿它和 SMB 的写带宽直接比大小是错的。详见 `references/perf-and-network.md` 第三节。

---

## 五、Windows 上挂 NFS：能挂，但不适合做「每人一份」

### 5.1 命令

```powershell
# 装组件（需管理员 + 联网/安装源）
Enable-WindowsOptionalFeature -Online -FeatureName ServicesForNFS-ClientOnly,ClientForNFS-Infrastructure -All
nfsadmin client stop; nfsadmin client start
```

```cmd
:: 匿名挂载（Synology 导出若为 world + 目录 777，anon 即可）
mount -o anon \\<NAS_IP>\volume2\<共享名> X:
:: 先看有哪些导出
showmount -e <NAS_IP>
```

### 5.2 三个绕不开的限制（实测）

1. **匿名 UID / GID 是「整机注册表」级的，不是按登录用户的。**
   `HKLM\SOFTWARE\Microsoft\ClientForNFS\CurrentVersion\Default` 下的
   `AnonymousUid` / `AnonymousGid` 一台机器只能有一套值。
   → 想让每个登录用户以**自己的** UID 访问自己的目录，做不到。
2. **NFS 挂载是「按会话 / 账户」的。** 管理员挂上的盘，普通用户看不见。
3. 因此：**Windows 客户端 + NFSv3 不适合「多人各自 home」的 VDI 场景。**

> 这是当初在 VDI 项目里最终选 SMB 而不是 NFS 的现实理由之一，
> 与 NFS 本身的性能无关（实测 NFS 读能跑满万兆）。

### 5.3 客户端侧的其它坑

- **Git Bash / MSYS 会把类 Unix 路径自动转换成 Windows 路径**：
  传 `/volume1/homes` 会变成 `D:/.../PortableGit/volume1/homes`，MNT 报 `status=13`。
  传参前先 `export MSYS_NO_PATHCONV=1`。
- 服务器端导出是 `/volume1/homes`，Windows 侧 UNC 要写成 `\\<NAS_IP>\volume1\homes`
  （Synology 的 NFS 导出路径**带 volume 前缀**，只有 SMB 才写成 `\\NAS\共享名`）。
- 挂载前先确认目标盘符空闲（`mount` 不会替你挑）。

---

## 六、与 SMB 的取舍速查

| 维度 | NFSv3 | SMB |
|---|---|---|
| Windows 原生客户端 | 要单独装组件、按会话挂载 | 原生，`\\NAS\share` 直接映射盘符 |
| 每用户隔离 | 靠 UID 数字，Windows 侧做不到 | 用 DSM 账号认证，天然支持 |
| 权限模型 | UNIX `uid/gid` + mode 位 | Windows ACL / 共享三档 |
| 写语义 | `FILE_SYNC` 默认（持久化口径） | 服务端写回（页缓存口径） |
| 传输加密 | 无（NFSv3 + AUTH_SYS 明文） | 支持 SMB3 加密/签名 |
| 读带宽 | 实测可跑满万兆（NAS 侧实测约 1.1 GB/s 级） | 同级 |
| 适合 | ESXi 数据存储、Linux 客户端、跨平台共享 | Windows / VDI 用户盘、需要账号隔离 |

> VMware ESXi 挂 NFS 数据存储是 NFS 最典型的用法——实测在 NAS 上看到的
> `*.vmdk` / `*-flat.vmdk` / `*-delta.vmdk` 就说明该导出正被 ESXi 使用。
> **规划时注意：不要把你新加的用户数据放到 ESXi 正在用的同一个导出/同一个卷上**，
> 那会和正在运行的虚拟机抢同一份后端 IO。
