# 浏览器自动化通路：GUI 才能干的事

有些事 DSM 的 Web API 干不了，只能走网页界面：

| 场景 | 为什么只能走 GUI |
|---|---|
| **安装 DSM**（Web Assistant） | 设备还没账号/没会话，压根没有可登录的 API |
| **装套件** | `SYNO.Core.Package.Installation.install` 实测返回 **103（no such API/method）** |
| **建共享文件夹** | `SYNO.Core.Share.create` 缺必填字段返回 **403**，字段名不好猜 |
| 绕过磁盘兼容性检查 | 向导里点不出来，得在页面里发带 `force:true` 的请求 |

浏览器通路 = 用浏览器自动化工具（`agent-browser`）打开 DSM，
**在已登录的页面上下文里执行 JS**，直接调页面自己的 `SYNO.API.Request`。
好处是完全复用浏览器里的登录态，不用自己管 sid / SynoToken。

## 一、准备

```bash
npm install -g agent-browser      # 0.27.0+
agent-browser install             # 下载 Chrome（约 196MB）
```

命令速查：

| 命令 | 作用 |
|---|---|
| `agent-browser open <url>` | 打开页面 |
| `agent-browser snapshot` | 取可访问性树（含 `[ref=eN]`，用于定位元素） |
| `agent-browser snapshot -i` | 只取可交互元素 |
| `agent-browser click <ref>` | 点元素 |
| `agent-browser type <ref> <文本>` | 输入 |
| `agent-browser check <ref>` | 勾选复选框 |
| `agent-browser eval "<js>"` | **在页面里执行 JS**（本通路的核心） |
| `agent-browser reload` / `screenshot` | 刷新 / 截图 |
| `agent-browser close` | 关闭（收尾必做） |

## 二、核心姿势：在页面里调 DSM Web API

```bash
agent-browser eval "new Promise(function(res){
  SYNO.API.Request({api:'SYNO.Core.System', method:'info', version:1,
    callback:function(s, r){ res(JSON.stringify({ok:s, model:r && r.model})) }});
})"
```

### ⚠️ 头号坑：`callback` 的第一个参数是布尔 `success`，数据在第二个

```js
callback: function(r){ ... r.data ... }        // ❌ r === true，取到 undefined
callback: function(s, r){ ... r.model ... }    // ✅ 正确
```

写成前者时 `JSON.stringify` 会得到 `{}` 或 `true`，看着像调用失败，其实是取错了参数位。
不确定签名就先 `function(){ res(JSON.stringify(Array.prototype.slice.call(arguments))) }`
把参数全打出来看一眼。

### 其它坑（都踩过）

- **`eval` 里别写箭头函数 IIFE**，会报 `Unexpected token ')'`。
  一律 `new Promise(function(res){ ... })`，显式写 `function`。
- **首次 `open` 冷启动可能挂 8 分钟以上**。加 `timeout 45` 包一层反而常常就能成功；
  进程已经在跑时 `snapshot` 直接可用，不必重复 `open`。
- 套件应用（如 Snapshot Replication）的窗口**可能渲染不进可访问性树**，
  点了菜单看不到窗口不代表没打开。此时别死磕 UI，直接 `eval` 调它的 Web API。
- 截图对排查"窗口为什么没渲染"帮助有限；优先读页面自己加载的 JS
  （`/webman/modules/AdminCenter/admin_center.js`、`/webman/3rdparty/StorageManager/storage_wizard.js`）
  反推真实 API 参数，比猜快得多。

## 三、判断设备状态（装 DSM 前后）

| 状态 | 判据 |
|---|---|
| 未装 DSM | `http://<NAS_IP>:5000` → 302 到 `web_index.html`，title = `Synology Web Assistant`；`/webman/uistring.cgi` 返回 `str_installer={...}` |
| 已装好 | title 是 DSM 登录页 / `<设备名> - Synology NAS` |

## 四、Web Assistant 装 DSM 的实际步骤（DS220+ / DSM 7.4.1-90080 实测）

1. 安装 → 选「自动下载 DSM 7.4.1-90080」（或手动指定本地 .pat）
2. 勾选「我了解硬盘 1 数据将被删除」
3. **需手动输入产品型号**（如 `DS220+`）才会继续 —— 这个弹窗容易漏
4. 进度 100% → 自动重启（约 10 分钟）
5. 欢迎页「开始」→ 设备名 / 管理员账号 / 密码
6. 更新选项、Synology 账户、设备分析、推荐套件、**2FA、Adaptive MFA**

> 2FA / Adaptive MFA 是否启用按现场要求定；测试机可跳过，生产环境建议开。
> 跳过 2FA 意味着账号只有口令一层保护，属于安全取舍，要向用户说明。

装完验证：`SYNO.Core.System info` 看型号 / 固件版本；
设备随后**开始回应 findhostd**（装前完全不应答），可当作「DSM 活着」的判据。

## 五、存储与快照：GUI 同款 API 契约（读 JS 反推，DSM 7.4 实测）

### 建卷（绕过磁盘兼容性检查）

```js
{api:'SYNO.Storage.CGI.Volume', method:'create', version:1,
 /* 同 storage_wizard.js 的参数 */ force:true}
```

向导提示「此硬盘不支持用于存储池」时，GUI 自己发的就是带 **`force:true`** 的同一个请求。
已实测第三方盘（如 ST500DM009）加了 `force:true` 能正常建成 btrfs 卷。

⚠️ 这是改磁盘/存储的操作，**必须先向用户说明并拿到确认**，且确认数据已无价值或已备份。

查结果：`SYNO.Storage.CGI.Storage` `load_info`（看 `volumes[].fs_type` / `space_status`）。
快照要求文件系统是 **btrfs**。

### 快照计划

```js
{api:'SYNO.Core.Share.Snapshot', method:'set_schedule', version:1,
 name:'<共享文件夹名>', enable_snapshot_schedule:true, task_id:<-1 或既有 id>,
 schedule:{date_type:0, week_name:'0,1,2,3,4,5,6', hour:0, min:0,
           repeat_hour:0, repeat_min:0, last_work_hour:0}}
```

- `date_type=0` + `repeat_hour=0` = **每天**；`week_name` 全选即一周七天
- 读回：`method:'get_schedule'`，看 `enable_snapshot_schedule` 与
  **`next_trigger_time`**（有值才说明任务真的注册上了）

### 保留策略

```js
{api:'SYNO.DisasterRecovery.Retention', method:'set', version:1,
 type:'Share', name:'<共享文件夹名>', tid:<-1 或既有>,
 policyType:64, retainDay:3, recently:3,
 advRetainDay:1, advHourly:24, advDaily:7, advWeekly:2,
 advMonthly:1, advYearly:1, advMinimum:5, advPolicyType:95}
```

`policyType` 是位掩码（常量出自 `admin_center.js`）：

| 常量 | 值 | 生效字段 | 含义 |
|---|---|---|---|
| `RTT_ALL` | 0 | — | 不启用保留策略 |
| `RTT_KEEP_ALL` | 1<<31 | — | 全部保留 |
| `RTT_DEL_OLD` | 20 | `recently` | 保留最近 N 个版本 |
| `RTT_TRRIGER_BY_TIME` | 32 | `schedule` | 按触发时间点清理（与上面按位或） |
| `RTT_BY_DAY` | 64 | `retainDay` | 保留 N 天 |
| `RTT_BY_ADVANCE` | 128 | adv* 组 | 高级保留策略 |

adv 子策略位：`MINIMUM=1, HOURLY=2, DAILY=4, WEEKLY=8, MONTHLY=16, YEARLY=32, DAY=64`
（默认 `advPolicyType=95`）。

**「保留 3 天」和「保留 3 份」是两回事**：前者 `policyType=64 / retainDay=3`，
后者 `policyType=20 / recently=3`。每天跑一次时两者效果接近，但语义不同，问清楚再配。

GUI 是把上面两条塞进 `SYNO.Entry.Request`（`mode:'sequential'`）的 `compound` 数组里一起发的，
照做即可。

### 快照冒烟验证（可回滚）

```js
// 建：返回快照名，形如 GMT+08-2026.09.30-13.20.49
{api:'SYNO.Core.Share.Snapshot', method:'create', version:1, params:{name:'<共享名>', desc:'smoke'}}
// 列：注意字段名是 time，**不是** snapshot_name
{api:'SYNO.Core.Share.Snapshot', method:'list', version:2, params:{name:'<共享名>', offset:0, limit:-1}}
// 删
{api:'SYNO.Core.Share.Snapshot', method:'delete', version:1, params:{name:'<共享名>', snapshots:['<快照名>']}}
```

建→列→删 走完一轮，`total` 回到 0，说明 btrfs 快照链路真的可用，而不只是配置写进去了。

## 六、安全与收尾

- 浏览器里的 DSM 会话**等价于完整登录凭据**。任务结束 `agent-browser close`，
  别把登录态挂在后台。
- 不要为了图方便把 sid / SynoToken 落盘成临时文件再给脚本用 ——
  页面 `eval` 已经带登录态，根本不需要。**确实落了盘就当场删掉**（同脱敏规范）。
- 截图可能含有设备名、序列号、内网 IP。要贴出去前先脱敏。
- 这条通路能改设备状态（建卷、装套件、删快照），
  **破坏性操作照样要先向用户说明 + 拿到确认**，不因为"是浏览器点的"就免检。

## 七、维护记录

- 2026-09-30：新增。含 DSM 7.4.1-90080 上建 btrfs 卷 + 每日 0 点保留 3 天快照计划的完整实测，
  以及 findhostd 之外的浏览器通路首个落地记录。
