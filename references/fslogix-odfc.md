# FSLogix ODFC 容器部署（群晖 NAS）

> 基于 2026-10-12 实操：DS918+ / DSM 7.3 + Directory Server（Samba AD 域控），
> 全部经过真实验证。写操作前先 `--dry-run`；本文命令均为 root 权限。
> 脱敏：`<域名>` `<共享>` `<NAS-FQDN>` 等一律用占位符，落地时替换为自己的值。

## 一、适用场景

VDI / 多用户环境把 Microsoft 365 应用数据（Outlook OST、OneDrive、Teams、
Office 授权、OneNote）重定向到 NAS SMB 共享上的 VHDX 容器：

- 用户数据集中存储、便于备份；
- 登录时按需挂载，减轻本地盘压力；
- OST 不再受"不能放网络盘"限制（VHDX 挂载后是本地块设备）。

## 二、前置条件

1. NAS 已装 Directory Server（Samba AD DC）并建域；
2. 客户机已加域（GPO 走计算机配置，域用户登录才生效）；
3. 目标机安装 FSLogix Agent（`https://aka.ms/fslogix_download`，最新 26.01 系）；
4. SMB 共享已建（建议专用子目录，如 `<业务共享>\FSLogix`）。

## 三、部署步骤

### 1. NAS 侧：建共享子目录

```bash
# 建议用业务共享下的专用子目录，避免与业务数据混放
mkdir -p '/volume1/<业务共享>/FSLogix'
```

### 2. NAS 侧：断开继承 + 配 ACL（关键，群晖有怪癖）

```bash
# 断开从父目录的 ACL 继承（否则继承业务共享的 ACL）
synoacltool -del-archive '/volume1/<共享>/FSLogix' is_inherit

# 清空后按序添加（新条目会插到 [1]，[0] 保持首个条目，见 synoacltool-acl.md 怪癖）
synoacltool -del '/volume1/<共享>/FSLogix'
synoacltool -add '/volume1/<共享>/FSLogix' 'group:<域>\Domain Users:allow:rwxpd-aARWcC-:---n'
synoacltool -add '/volume1/<共享>/FSLogix' 'group:<域>\Domain Admins:allow:rwxpdDaARWcCo:---n'
synoacltool -add '/volume1/<共享>/FSLogix' 'group:administrators:allow:rwxpdDaARWcCo:---n'
```

如果父目录（业务共享）根 ACL 没有域用户条目，需加一条仅穿越权限让用户能到达子目录：

```bash
synoacltool -add '/volume1/<业务共享>' 'group:<域>\Domain Users:allow:--x---a-R----:---n'
```

权限位含义、模板与怪癖详见 `references/synoacltool-acl.md`。

### 3. 客户机侧：装 Agent + GPO 配置

Agent 静默安装：

```powershell
FSLogixAppsSetup.exe /install /quiet /norestart /log C:\fslogix-install.log
```

GPO 配置见 `references/synology-gpo.md`（ODFC 注册表 10 个值）。

### 4. 验证

```powershell
# 注册表（GPO 生效后）
Get-ItemProperty 'HKLM:\SOFTWARE\Policies\FSLogix\ODFC'
# frx 工具
& 'C:\Program Files\FSLogix\Apps\frx.exe' list-redirects
# 域用户登录后，VHDLocations 下应出现 <用户名>-<SID> 目录 + VHDX
```

> 本地账号登录时 `frx list-redirects` 显示 "No redirections are currently active"
> 是**正常的**——FSLogix 只给域用户挂容器。

## 四、ODFC 注册表完整配置（10 值）

`HKLM\SOFTWARE\Policies\FSLogix\ODFC`：

| 值 | 类型 | 推荐值 | 说明 |
|---|---|---|---|
| Enabled | DWORD | 1 | 必填 |
| VHDLocations | REG_SZ | `\\<NAS-FQDN>\<共享>\FSLogix` | 用 FQDN（Kerberos 需要） |
| VolumeType | REG_SZ | vhdx | 容量大、损坏场景少 |
| SizeInMBs | DWORD | 30000 | 默认 30GB |
| FlipFlopProfileDirectoryName | DWORD | 1 | 目录名更易读 |
| IncludeTeams | DWORD | 1 | Teams 数据入容器 |
| LockedRetryCount / LockedRetryInterval | DWORD | 3 / 15 | 快速失败 |
| ReAttachRetryCount / ReAttachIntervalSeconds | DWORD | 3 / 15 | 快速重挂 |

## 五、群晖环境的 5 个关键结论（务必记住）

1. **任何给"其他主体"的 `fd--` 继承条目都会阻止域用户创建目录**。域用户能建目录
   的前提：ACL 里没有给别人的继承条目（本地 administrators 组也不例外）。因此
   **管理组权限用 `---n`（不继承）**——代价是管理员无法继承进每用户容器，
   需 SSH/root 临时授权访问。
2. **CREATOR OWNER 不被 synoacltool 支持**（名字和 SID `S-1-3-0` 形式都报
   `No such user`）。微软规范里的 CREATOR OWNER 条目无法直接实现。
3. **群晖 owner 隐式权限比 Windows 宽**：文件/目录创建者对自己创建的对象有完整
   读写（实测建目录、建文件、追加写全部 OK），弥补了第 2 点——FSLogix 每用户
   容器因此可用。
4. **mkdir 需要 W 和 C 同时存在**（群晖内部检查怪癖）：域用户权限串至少含
   W（Modify 组合位）和 C（ChangePermissions）。实测 `rwxpd-aARWcC-` 可用。
5. **ODFC 没有 SIDDirSDDL**（该设置仅 Profile 容器有），隔离完全靠 NAS ACL
   + owner 语义。

## 六、已知限制

- **Kerberos AES-SHA1**：2026-04 Windows 更新起 Kerberos 默认加密 RC4→AES-SHA1，
  承载容器的文件共享须先完成升级再装更新；
- **VHDLocations 必须用 FQDN**（如 `\\<NAS-FQDN>\...`），IP 访问会退到 NTLM；
- 建议 DSM 里把 FSLogix 子目录加入**媒体索引排除**，避免索引服务扫描大 VHDX；
- 加密共享不要用于 FSLogix 容器。

## 七、实测验证记录（2026-10-12）

| 测试项 | 结果 |
|---|---|
| 域用户穿越父共享并打开 FSLogix 目录 | 通过 |
| 域用户建每用户目录 + 容器内建 VHDX + 读写 | 通过 |
| 用户2 读/列/删 用户1 的容器 | 全部拒绝（隔离符合预期） |
| 用户2 建自己的目录 | 通过 |
| 父共享原有 ACL 及业务数据 | 未受影响 |
