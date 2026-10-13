# 群晖域控 GPO 管理（无 ADWS 绕过方案）

> 基于 2026-10-12 实操：群晖 Directory Server（Samba AD DC）+ Windows 11 管理机，
> 成功创建并生效一个 registry 型 GPO。写操作前先 `--dry-run`，先备份再改。
> 脱敏：`<域>` `<域fqdn>` `<NAS-IP>` 等一律用占位符。

## 一、核心限制（先说清楚）

群晖 Directory Server（Samba AD DC）**不运行 AD Web Services (ADWS)**，导致：

| 工具 | 状态 |
|---|---|
| GPMC（gpmc.msc） | 打不开域（"用户名或密码错误"，实际是本地登录身份不被域信任） |
| PowerShell GPO 模块（Get-GPO/New-GPO） | 无 `-Credential` 参数，依赖当前进程域身份；`Start-Process -Credential` 被拒 |
| Get-ADDomain / ActiveDirectory 模块 | 报 "Unable to find a default server with AD Web Services running" |
| **LDAP + SYSVOL 直接操作** | **可用**（本文方案） |

## 二、可行方案：直接操作 LDAP + SYSVOL

GPO 本质 = LDAP 对象（groupPolicyContainer）+ SYSVOL 文件（GPT.INI + MACHINE/Registry.pol）。

### 连接方式

```python
# LDAP 必须用 LDAPS(636)！明文 389 简单绑定会被 strong auth 拒绝
import ldap3
server = ldap3.Server('<NAS-IP>', port=636, use_ssl=True)
conn = ldap3.Connection(server, user='Administrator@<域>', password='<密码>',
                        authentication=ldap3.SIMPLE)
conn.bind()
```

SYSVOL 文件用 SSH exec 通道传（SFTP 写不了 @appdata 路径，见本文第七节）。

## 三、GPO 创建完整清单

### 1. LDAP 对象（CN=Policies,CN=System,DC=<域>,DC=）

```python
GPO_DN = f'CN={{{GUID}}},CN=Policies,CN=System,{DOMAIN_DN}'
attrs = {
    'objectClass': ['top', 'container', 'groupPolicyContainer'],
    'cn': f'{{{GUID}}}',
    'displayName': '<GPO 名>',
    'gPCFileSysPath': f'\\\\<域fqdn>\\sysvol\\<域>\\Policies\\{{{GUID}}}',
    'gPCFunctionalityVersion': [2],
    'flags': [0],
    'versionNumber': [0],          # 每次改内容要递增
    'showInAdvancedViewOnly': [True],
    # Registry CSE 正确 GUID 对（从默认域策略复制，勿编造）
    'gPCMachineExtensionNames': ['[{35378EAC-683F-11D2-A89A-00C04FBBCFA2}{53D6AB1B-2488-11D1-A28C-00C04FB94F17}]'],
}
conn.add(GPO_DN, attributes=attrs)
```

### 2. 两个必备子容器（容易漏！）

```python
for sub in ['Machine', 'User']:
    conn.add(f'CN={sub},{GPO_DN}',
             attributes={'objectClass': ['top','container'], 'cn': sub,
                         'showInAdvancedViewOnly': [True]})
```

### 3. 链接到域（gPLink，方括号不能省）

```python
# 每个链接都要 [LDAP://...;0] 格式，多个直接拼接
link = f'[LDAP://CN={{{GUID}}},CN=Policies,CN=System,{DOMAIN_DN};0]'
conn.modify(DOMAIN_DN, {'gPLink': [(ldap3.MODIFY_REPLACE, [existing + link])]})
```

### 4. SYSVOL 文件（群晖路径）

```
/volume1/@appdata/DirectoryServerForWindowsDomain/private/sysvol/<域>/
└── Policies/
    ├── PolicyDefinitions/          ← ADMX 模板放这里
    │   ├── <产品>.admx
    │   └── en-US/<产品>.adml
    └── {<GUID>}/                   ← 新建 GPO
        ├── GPT.INI                 ← ASCII 编码！
        ├── MACHINE/Registry.pol    ← 二进制，目录/文件名大写
        └── USER/
```

属主统一 `chown '<域>\administrator':root`（组随便是 root 也能读，777 权限）。

## 四、registry.pol 二进制格式（最容易踩坑）

### 格式规范（每条记录）

```
'['(5b 00) + key(UTF-16LE + 00 00) + ';'(3b 00) + value(UTF-16LE + 00 00) + ';'(3b 00)
+ type(4B LE) + ';'(3b 00) + size(4B LE) + ';'(3b 00) + data(size B) + ']'(5d 00)
```

**三个致命细节**：

1. **分隔符 `[` `;` `]` 全是 UTF-16**（`\x5b\x00`/`\x3b\x00`/`\x5d\x00`），不是单字节 ASCII；
2. **data 之后没有分号，直接 `]`**（多写一个 `;` 会报 ErrorCode 13
   "Expected to find ], but found ;"）；
3. key/value 是 UTF-16LE 以 `\x00\x00` 结尾；type/size 是 4 字节小端 DWORD
   （REG_DWORD=4, REG_SZ=1, REG_MULTI_SZ=7）。

### 生成代码（实测可用）

```python
import struct
def dword(v): return struct.pack('<I', v & 0xFFFFFFFF)
def reg_sz(s): return s.encode('utf-16-le') + b'\x00\x00'

key = "Software\\Policies\\<产品>\\<节>".encode('utf-16-le')
semi = b'\x3b\x00'
with open('Registry.pol','wb') as f:
    f.write(b'PReg\x01\x00\x00\x00')   # 头部签名+版本
    for name, typ, data in entries:
        val = name.encode('utf-16-le')
        f.write(b'\x5b\x00' + key + b'\x00\x00' + semi
                + val + b'\x00\x00' + semi
                + struct.pack('<I', typ) + semi
                + struct.pack('<I', len(data)) + semi
                + data + b'\x5d\x00')
```

### GPT.INI（ASCII，别用 UTF-16）

```
[General]
Version=<与 LDAP versionNumber 一致>
```

## 五、调试方法论（推荐）

**下载默认域策略的 Registry.pol 逐字节对比**——这是定位格式问题最可靠的方法：

```python
# 从 NAS 拉默认 GPO 的 Registry.pol 到本地
cmd = "base64 '/volume1/@appdata/DirectoryServerForWindowsDomain/private/sysvol/<域>/Policies/{31B2F340-016D-11D2-945F-00C04FB984F9}/MACHINE/Registry.pol'"
```

事件日志（关键错误码）：

```powershell
Get-WinEvent -LogName System | Where-Object ProviderName -like '*GroupPolicy*'
# ID 1096 = registry.pol 应用失败，XML 里有 ErrorCode/ErrorDescription/FilePath
# ID 1058 = 读不到 gpt.ini
# ID 1502 = 成功（"New settings from N Group Policy objects were detected and applied"）
```

错误码速查：

| 现象 | 原因 |
|---|---|
| ID 1058 "cannot read gpt.ini" | GPT.INI 编码错（须 ASCII）/ 大小写 / gPLink 没生效 |
| ID 1096 ErrorCode 13 "Expected ], found ;" | registry.pol data 后多写分号 |
| ID 1096 "could not apply registry-based policy ... CN=Machine" | 缺 CN=Machine/CN=User 子容器 |
| gpupdate 报成功但注册表没变 | versionNumber 没递增，客户端不重新下载 |

## 六、排错顺序（实战总结）

1. 先确认 gPLink 格式（方括号）→ 客户端才会尝试读 GPO；
2. 再确认 GPT.INI 是 ASCII + Version 与 LDAP versionNumber 同步；
3. 再确认 MACHINE/Registry.pol 大小写和二进制格式；
4. 最后确认 CN=Machine/CN=User 子容器存在；
5. 每次改 registry.pol：**递增 versionNumber + 同步 GPT.INI Version**，
   否则客户端用缓存不重下。

## 七、相关环境备注

- SYSVOL 路径：`/volume1/@appdata/DirectoryServerForWindowsDomain/private/sysvol/<域>/`；
- SFTP **写不了** @appdata 下的 sysvol，用 SSH exec 通道 + base64 分块传输
  （片段见 `references/ssh-and-troubleshooting.md` 或 SKILL.md「文件传输」小节）；
- samba-tool 实际在 `/usr/local/bin/samba-tool`（不在 DirectoryServer 套件目录）；
- 域密码策略默认最长 42 天、锁定阈值 0；LDAP 简单绑定必须走 LDAPS(636)/StartTLS，
  明文 389 即使密码正确也报 `strongerAuthRequired`。
