# 套件离线安装 + 共享文件夹 + 日志归档（Web API 路线）

> 配套脚本：`scripts/install_packages.py`（纯标准库，复用 `dsm_api.py` 的 DSM 传输层）。
> 凭据约定与 `dsm_api.py` 一致：`DSM_HOST / DSM_ACCOUNT / DSM_PASSWORD / DSM_VERIFY_SSL`。

---

## 1. 为什么需要这条路线

Package Center 在线安装时，NAS 会回到 Synology 的 CDN 拉 `.spk`。很多内网 / 受限网络
环境里 NAS **连不上 CDN**，在线装直接报 `error 400`。可靠做法：在能上网的机器上先把
`.spk` 下下来，再**离线**装进 NAS。

实测可用的离线路线（已在 DS 系列 / DSM 7.x 验证）：

```
本地 .spk  ──FileStation 上传──▶  共享文件夹（共享根路径）
                                      │
                                      ▼
                     SYNO.Core.Package.Installation
                     （SYNO.Entry.Request 复合 check+install，path 用磁盘绝对路径）
```

⚠️ 这是「变更 / 写」操作，脚本默认不执行，**必须显式 `--yes` 才落地**，符合技能
「只读优先、变更需确认」红线。

---

## 2. 头号坑（务必先看）

### 2.1 本地 NAS 必须绕过本机代理（NO_PROXY）
如果运行脚本的机器上挂着 HTTP/HTTPS 代理（常见开发机有 `HTTPS_PROXY=http://127.0.0.1:xxxx`），
FileStation 上传会**撞代理**报 `ProxyError 10054`（连接被重置）。

脚本在启动时会自动把 `DSM_HOST` 里的主机名/IP 追加进 `NO_PROXY` / `no_proxy`，
让上传走直连。若你手动调 API，务必先：

```bash
export NO_PROXY="<nas_ip>,127.0.0.1,localhost"   # 换成你的 NAS IP
```

### 2.2 FileStation 用「共享根路径」，不是磁盘路径
FileStation 的所有路径都是**共享根路径**：

| 场景 | 正确写法 | 错误写法 |
|---|---|---|
| 上传目标 / 建子目录 | `/nas管理` | `/volume1/nas管理` |
| 列目录 | `folder_path=/nas管理` | `folder_path=/` （返回 401） |

但**安装套件时**用的 `path` 必须是**磁盘绝对路径** `/volume1/nas管理/xxx.spk`（见 3.2）。
两套路径不要混。

### 2.3 日志归档 `set` 的布尔字段必须是 true/false 字符串
`SYNO.LogCenter.Setting.Storage set` 里 `archive / enable_time / format` 等布尔字段，
传 `1/0` 整数 DSM 会拒（**error 120**）。必须传字符串 `"true"/"false"`（即 Python
`True/False` 经 `str(v).lower()` 转换后的值）。

而且 `set` 必须是 **HTTP POST**（`request_data` 的第 4 个参数是 HTTP 动词，不是 API 方法）。
用 GET 默认会报 120。脚本已处理这两点。

### 2.4 共享文件夹 Web API 偶发 403
`SYNO.Core.Share create` 在部分机型/DSM 版本上会返回 **403**（权限层面的已知限制）。
脚本会尝试 Web API 创建，失败后明确提示改用浏览器自动化路线
（`references/browser-automation.md`）。**子目录**用 FileStation 建则不受影响。

---

## 3. 脚本用法

### 3.1 环境准备
```bash
export DSM_HOST="http://<nas>:<端口>" DSM_ACCOUNT=<管理员账号> DSM_PASSWORD='<密码>'
# 自签证书：export DSM_VERIFY_SSL=0
```

### 3.2 子命令

| 命令 | 作用 | 是否写操作 |
|---|---|---|
| `status` | 只读：列共享文件夹 / 已装套件 / 当前日志归档设置 | 否 |
| `install --share <共享> <a.spk> [b.spk]` | 上传并安装本地 .spk（离线安装） | 是，需 `--yes` |
| `create-share --name <名>` | 创建共享文件夹 | 是，需 `--yes` |
| `create-folder --share <共享> --name <子目录>` | 在共享内建子目录 | 是，需 `--yes` |
| `set-log-archive --share <共享> --sub <子目录>` | 设日志中心归档路径为 `<volume>/<共享>/<子目录>` | 是，需 `--yes` |
| `setup --name <共享> --subs log 分析报告 --files LogCenter.spk StorageAnalyzer.spk --clean` | 一条龙：建共享→子目录→安装→归档→清理安装包 | 是，需 `--yes` |

`--volume` 默认 `/volume1`；`--pid` 默认取 .spk 文件名首段（如 `LogCenter-x86_64-...spk` → `LogCenter`）。

### 3.3 典型一条龙（Request D 场景）
```bash
python3 scripts/install_packages.py setup \
  --name nas管理 --subs log 分析报告 \
  --files /tmp/LogCenter.spk /tmp/StorageAnalyzer.spk \
  --clean --yes
```
效果：
1. 建共享文件夹 `nas管理`（若已存在则跳过）；
2. 建子目录 `log/`、`分析报告/`；
3. 上传并安装两个套件（磁盘路径 `/volume1/nas管理/*.spk`）；
4. 日志归档设为 `/volume1/nas管理/log`（`archive=1, enable_time=1`）；
5. 删除共享文件夹里的 `.spk` 安装包。

### 3.4 复核
```bash
python3 scripts/install_packages.py status   # 看套件 status 是否 running、归档路径是否正确
```
套件安装是**异步**的，`install` 返回 `has_fail:false` 只代表请求已接受，稍后用 `status`
确认 `status=running`。

---

## 4. 局限（无法用 Web API 自动化）

- **存储空间分析器（StorageAnalyzer）的「每周分析报告」无法用 API 建**。
  全量 `SYNO.API.Info query=all` 返回数百个 API，但**没有任何 `StorageAnalyzer` /
  `SYNO.SDS.StorageAnalyzer.*` 条目**（返回均为 102 = API 不存在）。它的「报表配置 +
  计划任务」是桌面客户端（UI）功能，配置存在套件私有路径，FileStation/SSH 都够不到
  （SSH 默认关闭）。
  **手动步骤**：套件内 设置 → 报表保存位置 = `/nas管理/分析报告`；报表配置 → 新建 →
  按计划生成报表 → 每周。

- **共享文件夹创建**在部分机型 Web API 返回 403，见 2.4。

---

## 5. 安全与脱敏

- 脚本只做「上传 + 安装 + 建目录 + 设归档 + 删安装包」，不含任何 SSH / 删系统文件能力。
- 凭据全部走环境变量，不落盘、不写日志。
- 推送 / 提交前确认脚本与文档里**没有真实 IP / 账号 / 密码 / sid / token**
  （示例一律用占位符 `<nas>` / `<管理员账号>`）。
