# DSM Web API 通路（已在真实 DS918+ 上验证）

除 SSH 外，DSM 还有一套官方 HTTP Web API，能在不启用 SSH 的情况下管理 NAS。
以下结论均在真实 DS918+（注册了 1644 个 API）上实测通过，不是推测。

## 一、认证：拿 sid

```
GET /webapi/entry.cgi?api=SYNO.API.Auth&version=<v>&method=Login
    &account=<账号>&passwd=<密码>&session=<会话名>&format=sid
```

成功返回：

```json
{ "success": true,
  "data": { "sid": "...", "did": "...", "is_portal_port": false } }
```

会话凭据 sid 之后每次调用都带上，任选其一：

- URL 参数：`...&_sid=<sid>`
- 或 Cookie：`id=<sid>;`
登出：`method=Logout`（用完务必登出，否则会话一直有效）。

### ⚠️ 关键坑：SYNO.API.Info 报的 maxVersion 不一定能用

实测该机 SYNO.API.Auth 注册信息为 maxVersion=7，
但 v7 登录返回 error 103，v6 才成功。

结论：从高到低逐个试 v7 → v6 → v3，别只信注册表里的 maxVersion。
`scripts/dsm_api.py` 已内置这个回退逻辑。

## 二、探查：API 注册表是唯一真相

```
GET /webapi/query.cgi?api=SYNO.API.Info&version=1&method=Query&query=all
```

返回一个巨大的字典，key 是 API 名，value 含 path（该走哪个 cgi）与版本区间。
动手前先查它，比猜 API 名可靠得多。

按需要筛：

```
GET /webapi/query.cgi?api=SYNO.API.Info&version=1&method=Query&query=SYNO.Core.Terminal
```

## 三、DSM 错误码（处置重点在多版本 Auth 与 API 命名上）

| 码 | 含义 | 处置 |
|---|---|---|
| 102 | API 不存在（名字写错 / 该 DSM 没注册） | 去注册表查正确名字。不要误判成权限不足 |
| 103 | API 方法/版本不存在 | 降 version 重试（见第一节） |
| 105 | 权限不足以调用该 API | 确认账号是否在 administrators 群组 |
| 119 | 会话失效/未登录 | 重新 Login，dsm_api.py 会自动重登一次 |
| 400 | 账号或密码错误 | 核对凭据 |
| 117 | 需要二次验证（OTP） | 需 SYNO.Core.OTP 流程 |

常见 API 名陷阱（实测）：

- ❌ SYNO.Core.CurrentUser —— 不存在，用 SYNO.Core.User / SYNO.Core.NormalUser
- ❌ SYNO.Core.Share.Util —— 不存在，用 SYNO.Core.Share

## 四、常用 API 速查（实测可用）

| 用途 | API | method | version |
|---|---|---|---|
| 系统概要 / 硬件 | SYNO.Core.System | info | 3（比 1 多返回 cpu_family、cpu_series、cpu_cores、firmware_date） |
| CPU/内存占用 | SYNO.Core.System.Utilization | get | 1 |
| SSH/Telnet 开关 | SYNO.Core.Terminal | get / set | 3 |
| 共享文件夹列表 | SYNO.Core.Share | list | 1（传 only_visible=false） |
| 本地用户列表 | SYNO.Core.User | list | 1（传 type=local） |
| 当前连接会话 | SYNO.Core.CurrentConnection | list | 1 |
| 已装套件 | SYNO.Core.Package.Server | list | 1 |
| 磁盘/存储池 | SYNO.Storage.CGI.Storage | load_info | 1 |
| 任务/Findstation 文件列举 | SYNO.FileStation.List | list_share | 2 |

判断账号是否管理员：别指望某个 "am I admin" 接口，
直接试着调用只有管理员能调的 API（如 SYNO.Core.Share list / SYNO.Core.User list），
能列出全部共享文件夹与用户即为管理员权限。

## 五、安全提醒（重要）

- 走 HTTP 时账号密码是明文上行的。若 DSM 是 http://，务必只在内网/可信链路使用，
或改用 HTTPS 端口（DSM 默认 5001）。
脚本提供 `DSM_VERIFY_SSL=0` 跳过自签名证书校验，仅限内网调试。
- 凭据只从环境变量读取，不要写进脚本、仓库或命令行历史。
- 脚本用完会 logout；手动连的话记得收尾登出。
- sid 等价于完整会话凭据，泄露即等于账号失守。

## 六、用法（scripts/dsm_api.py）

```bash
export DSM_HOST="http://<nas>:<端口>" DSM_ACCOUNT=<账号> DSM_PASSWORD='<密码>'

python3 dsm_api.py info                       # 系统 + SSH状态 + 共享文件夹
python3 dsm_api.py apis [关键字]              # 列出注册 API
python3 dsm_api.py call SYNO.Core.Share list 1 only_visible=false
python3 dsm_api.py call SYNO.Core.System info 3
python3 dsm_api.py logout
```

凭据不落盘，进程退出即失效。

## 七、维护记录

- 2026-09-27 周度巡检：本周无新的 DSM Web API 实测记录（未连接新设备），
  第三节错误码与第四节 API 速查表不变。已知结论仍是 DS918+ / DSM 7.3-81180 上的实测。
