# synoacltool ACL 实战：权限位映射与群晖怪癖

> 基于 2026-10-12 实操（DS918+ / DSM 7.3 / Samba AD 域控），全部经过真实验证。
> 改 ACL 是写操作：先 `synoacltool -get` 留底，再小步改，改完立刻核对。

## 一、常用命令速查

```bash
synoacltool -get PATH                    # 查看 ACL（含 level:0 显式 / level:1 继承）
synoacltool -add PATH '主体:权限:继承'    # 添加条目
synoacltool -replace PATH INDEX '条目'    # 按索引替换（注意：群晖会重排条目！）
synoacltool -del PATH                    # 删除全部条目
synoacltool -copy PATH_SRC PATH_DST      # 复制 ACL
synoacltool -del-archive PATH is_inherit # 断开继承（关键！）
synoacltool -set-owner PATH NAME         # 改属主
```

**断开继承的正确姿势**：`synoacltool -del-archive PATH is_inherit`
（`-set-archive PATH no_inherit` **无效**，别用）。

## 二、权限位映射（13 位串）

群晖用 13 位权限串，映射到 Windows 权限：

| 位 | 字符 | Windows 权限 | 说明 |
|---|---|---|---|
| 1 | r | ReadData/ListDirectory | 读 |
| 2 | w | WriteData/CreateFiles | 写 |
| 3 | x | Execute/Traverse | 执行/穿越 |
| 4 | p | AppendData/CreateDirectories | 追加/建目录 |
| 5 | d | Delete | 删除自身 |
| 6 | D | DeleteSubdirectoriesAndFiles | **删子项（互删风险的来源）** |
| 7 | a | ReadAttributes | 读属性 |
| 8 | A | WriteAttributes | 写属性 |
| 9 | R | ReadPermissions(READ_CONTROL) | 读权限 |
| 10 | W | 属 Modify 组合 | 单独去掉会导致 mkdir 失败（见怪癖 1） |
| 11 | c | ReadExtendedAttributes | 读扩展属性 |
| 12 | C | **ChangePermissions(WRITE_DAC)** | 改 ACL |
| 13 | o | **TakeOwnership(WRITE_OWNER)** | 取所有权 |

### 常用模板

| 用途 | 权限串 | Windows 视图 |
|---|---|---|
| 完全控制 | `rwxpdDaARWcCo` | FullControl |
| 群晖"读/写"预设 | `rwxpdDaARWc--` | Modify + DeleteSubdirectoriesAndFiles |
| 只读 | `r-x---a-R-c--` | ReadAndExecute |
| 仅穿越 | `--x---a-R----` | 能穿过不能列出 |
| **域用户容器根（FSLogix 实测可用）** | **`rwxpd-aARWcC-`** | **Modify + ChangePermissions** |

### 继承标志（第二位段）

| 值 | 含义 |
|---|---|
| `fd--` | 继承到文件和目录 |
| `---n` | 仅本目录，不继承 |
| `fdi-` | 仅作为继承（不对自身生效） |

## 三、群晖 ACL 四大怪癖（全部实测）

### 怪癖 1：mkdir 需要 W 和 C 同时存在

域用户建目录的权限串**必须同时含 W（位10）和 C（位12）**（或含 D）。
只给 `rwxpd-aAR-cCo`（缺 W）建目录会被拒（Access denied），但**建文件正常**——
现象极具迷惑性。

实测可用的最小集：`rwxpd-aARWcC-`（Modify + ChangePermissions，无 D 无 o）。

### 怪癖 2：给其他主体的 fd-- 继承条目会阻止域用户 mkdir

只要目录 ACL 里存在**任何给其他主体的 fd-- 条目**（哪怕是本地 administrators 组），
域用户 mkdir 即被拒。推测是群晖安全设计：用户不能为自己新建的目录应用包含
他人权限的 ACL。

**推论**：想让用户建目录 → ACL 里只能有给自己的 `---n`/`fd--` 条目 +
给别人的 `---n` 条目；管理组的 FC 只能用 `---n`（不继承进子目录）。

### 怪癖 3：CREATOR OWNER 不支持

```bash
synoacltool -add PATH 'user:CREATOR OWNER:allow:...'   # 报 No such user
synoacltool -add PATH 'user:S-1-3-0:allow:...'         # 同样报错
```

微软规范里"CREATOR OWNER 对子文件夹和文件 Modify"这一条在群晖**无法直接实现**。

### 怪癖 4：owner 隐式权限比 Windows 宽

文件/目录的**创建者（owner）对自己创建的对象有完整读写**（建文件、追加写、
目录内建文件实测全 OK）。这弥补了怪癖 3——FSLogix 每用户容器场景可用。

## 四、条目排序陷阱

`synoacltool -add` 的新条目会**插入到 [1]**（[0] 保持第一个），`-replace` 也会
触发重排。因此：

- **不要用 `-replace PATH 1 ...` 连续改多个条目**（索引会漂移，可能改错对象
  或产生重复条目）；
- 稳妥做法：`-del PATH` 全删 → 按目标顺序重新 `-add`；
- 每次操作后用 `-get` 核对。

## 五、域主体写法

```bash
# 域组/域用户：域\名称（winbind 会规范成小写存储，正常现象）
synoacltool -add PATH 'group:<域>\Domain Users:allow:rwxpd-aARWcC-:---n'

# 本地组
synoacltool -add PATH 'group:administrators:allow:rwxpdDaARWcCo:---n'

# 属主设置（域账号）
synoacltool -set-owner PATH '<域>\administrator'
```

## 六、排查命令

```bash
# 查看 ACL（注意 level:0=显式, level:1=继承）
synoacltool -get '/volume1/<共享>/<目录>'

# 从 Windows 侧看最终效果（域管凭据挂载后）
(Get-Acl '\\<NAS>\<共享>\<目录>').Access | Format-Table IdentityReference, FileSystemRights

# 检查用户组映射（域用户是否真在 Domain Users）
samba-tool user getgroups <用户名>
```

## 七、实测案例（FSLogix 共享，2026-10-12）

目标：域用户能建自己的容器目录、不能互删、管理员可管。

**最终 ACL（三条目全 `---n`）**：

| # | 主体 | 权限串 | 继承 | 效果 |
|---|---|---|---|---|
| 0 | `<域>\Domain Users` | `rwxpd-aARWcC-` | `---n` | 建目录/建文件/写自己的 |
| 1 | `administrators` | `rwxpdDaARWcCo` | `---n` | 管根目录（不继承） |
| 2 | `<域>\Domain Admins` | `rwxpdDaARWcCo` | `---n` | 管根目录（不继承） |

父共享根加一条仅穿越：`group:<域>\Domain Users:allow:--x---a-R----:---n`。

**验证结果**：建目录/建 VHDX/读写自己容器 OK；用户间读/列/删全部拒绝；
父共享原有 8 条 ACL 未受影响。

**遗留**：管理员访问用户容器需 NAS root/SSH 临时授权（管理组权限不继承进
容器，这是怪癖 2 的必然代价）。

完整部署上下文（ODFC 注册表、Agent 安装、GPO）见 `references/fslogix-odfc.md`。
