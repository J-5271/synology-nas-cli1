# 新机开荒部署要点（提炼自官方《Synology NAS 部署指南》DSM 6.2）

> **来源**：群晖官方《Synology NAS 部署指南》V1.0.0（基于 DSM 6.2，面向机架式机型/企业部署）
> PDF：<https://cndl.synology.cn/download/Document/Software/UserGuide/Os/DSM/6.2/chs/Synology_NAS_Deployment_Guide_DSM_6_2_chs.pdf>
>
> ⚠️ **本文件是要点重述，不是原文复制**。官方 PDF 的法律声明明确禁止未经书面许可摘抄、
> 翻译、复制其部分或全部内容 —— 因此这里只保留**事实性、可操作的知识**
> （选型表、参数限制、配置路径、注意事项），并以官方知识库链接指向原始步骤。
> 完整图文步骤与截图请以官方 PDF / 知识库为准。商标与版权归 Synology Inc. 所有。
>
> ⚠️ **版本差异**：本指南基于 DSM 6.2。DSM 7 上部分入口改了名（见文末对照表），
> 且 DSM 7 起官方不再建议直接停用 admin 之外的部分旧做法。下命令前先按本技能
> 「先 discover 再执行」的原则在设备上核实。

## 一、部署顺序（官方推荐流程，照着走不漏项）

```
1. 创建 Synology 帐户（QuickConnect / 授权 / 技术支持要用）
2. 下载 Synology Assistant + 《硬件安装指南》（+ 离线场景预下载 .pat 安装包）
3. 装硬件：导轨 → 硬盘 → 网卡（可选）→ 内存（可选）→ UPS（可选）→ 扩充设备（可选）
4. 通电，等约 5 分钟（电源灯蓝闪 → 蓝常亮）；NAS 与装机电脑同一网段
5. 装 DSM：Assistant 双击「DSM 未安装」的设备 → EULA → 立即安装 → 勾选「数据将被删除」
   → 等约 10 分钟（勿断电）→ 设服务器名/管理员/密码 → QuickConnect → 完成
6. 【可选】网络：Link Aggregation → SHA 双机热备 → MTU
7. 存储：RAID Group（可选）→ 存储池 → 存储空间 → SSD 缓存（可选）→ Hot Spare（可选）
8. 账号：批量导入（可选）→ 群组 → 用户 → 家目录（可选）→ AD 域（可选）
9. 文件访问：共享文件夹 → File Station → 网络协议（SMB/NFS/iSCSI）→ Drive（可选）
10. 监控：日志中心 + 归档（+ syslog 收发，可选）
11. 安全：DSM 更新策略 → 邮件通知 → IP 自动封锁 → 账户保护 → 防火墙 →
    停用 admin/guest → 密码强度 → 2 步验证 → 改默认端口 → 安全顾问定期扫描
```

装机时的三条硬约束：

- **管理员名不要用 admin / administrator / root**（常见病毒优先撞这几个）；
  用自定义名后 DSM 会自动停用 admin 与 guest，装完要去确认。
- **装系统会格式化硬盘**，装前备份。
- 组件要在 Synology 兼容性列表里，否则稳定性不保。

## 二、第 2 章：装 DSM

| 项 | 值 |
|---|---|
| 三种进入方式 | Synology Assistant（**官方推荐，最稳**）／ `find.synology.com`（Windows）／ `synologynas:5000`（Mac） |
| 浏览器 | 建议 Chrome / Firefox |
| 离线安装 | Assistant 里「手动安装」→ 选预先下载的 `.pat` |
| 耗时 | 约 10 分钟，中途断电/断连会失败，需重新连 |

> 与本技能 `references/browser-automation.md` 的关系：那份记的是 **DSM 7.4 Web Assistant**
> 的浏览器安装实测（含"需手动输入产品型号"这个坑）。本节是官方 6.2 的 Assistant/网页路径。
> 两条路都能装，7.x 建议看浏览器那份。

## 三、第 3 章：网络（可选）

- **Link Aggregation**：多网口聚合成一个逻辑口提带宽。
  ⚠️ **顺序铁律：必须先建链路聚合，再组 HA 集群**；进了集群就加不了，
  只能「移除集群 → 建链路聚合 → 重建集群」。
- **SHA 双机热备**：2 台组成 HA 集群，1 主 1 备，数据持续复制，主机故障时备机接管。
- **MTU**：装了万兆网卡才把默认 1500 调到 9000。
  ⚠️ **全网（交换机、路由器、客户端）MTU 必须一致**，否则丢包。
  - Windows：网卡 → 属性 → 配置 → 高级 → 巨型帧 → 9KB MTU
  - macOS：网络 → 高级 → 硬件 → 手动 → 特大 (9000)

## 四、第 4 章：存储（选型表是本章最值钱的部分）

### 存储池类型

| 类型 | 适用 |
|---|---|
| 性能改善 | 只要**单个**存储空间，追求性能 |
| 灵活性提高 | 要建**多个**存储空间，或要用 RAID Group |

### RAID 选型（官方建议，单存储池）

| 硬盘数 | 场景 | 建议 |
|---|---|---|
| ≦ 5 | 通用 | RAID 5 |
| ≧ 6 | 通用 | RAID 6 |
| ≧ 6 | **长期无人值守**（如假期机房无人，坏了没人换盘） | RAID 6 + 1 块热备盘 |

RAID 6 + 热备的做法：先建 RAID 6，**预留 1 块盘不勾选**，再把它配成 Hot Spare。

### 文件系统：Btrfs vs Ext4

| | 特点 | 适用 |
|---|---|---|
| **Btrfs** | 支持快照、复制、时间点恢复；数据完整性保护；可为**每个共享文件夹**设用户配额 | 绝大多数场景（文件共享、关键业务数据、iSCSI LUN） |
| Ext4 | 备份方式单一 | **仅当该空间只存 Surveillance Station 录像** |

> 补充（本技能实测）：**快照功能要求 btrfs**。建卷时选了 ext4 就没法做快照计划，
> 见 `references/browser-automation.md`。

### 其它存储要点

- **Stripe Cache size**：跑虚拟机要提升随机读写时可**调小** —— 缩短延迟，但降吞吐、
  也降 RAID 重同步速度。**仅 RAID 5 / 6 / F1 支持改**。
- **SSD 缓存**：1 块 SSD 只能做**只读**缓存，2 块及以上可做只读或读写。
  - M.2 SSD **不支持热插拔**（SATA SSD 支持）。
  - **M.2 SSD 只能做缓存，不能用来建存储池。**
  - ⚠️ 缓存盘必须与它所服务的存储空间**在同一台主机或同一个扩充设备上**，
    跨设备一旦断线/断电会导致存储池损毁、套件失效，且难修复。
- **Hot Spare**：存储池降级时自动顶替故障盘。三个前置条件：
  1. RAID 类型必须带保护（RAID 1 / 5 / 6 / 10 / F1）；
  2. 热备盘容量 ≥ 池中最小盘；
  3. **HDD 池不能用 SSD 热备盘自动修复，反之亦然**。
- **RAID Group**：1 个池里放 2 个以上 RAID 阵列提升容灾，主要用于 24 盘位机型
  （FS6400 / FS3600 / FS3400）或跨扩充设备建池。
  ⚠️ 官方明说：跨设备存储池即使用 RAID Group，**风险仍高于独立池**，
  断连/断电/意外关机都可能毁池。
- 存储池建完会进入「在后台验证硬盘」状态 —— **此期间别关机重启**，除不能加 SSD 缓存外功能可用（性能受影响）。

## 五、第 5 章：账号

- 批量导入用户：UTF-8 文本或 Excel。
- 用户默认加入 `users` 组；勾 `administrators` 组即给管理员权限。
- ⚠️ **每个文件夹的 ACL（用户 + 群组）上限 200 条** —— 这条在
  SKILL.md「细粒度权限」一节也提到过，权限设计时要留余量。
- 家目录：控制面板 → 用户帐号 → 高级设置 → 勾「启动家目录服务」+「启用回收站」。
  开后每个用户只能访问自己的 home；`homes` 是所有 home 的镜像，**仅管理员可见**。
  **域用户的 home 需登录一次 DSM 后才会创建**（控制面板 → 域/LDAP → 域用户 → 家目录）。
- 无域但有多台 NAS → 用 Synology Directory Server；有 AD → 把 NAS 加入域，
  域用户可凭同一套凭据访问多台 NAS。

## 六、第 6 章：共享文件夹与文件访问

### 命名规则（建之前先对一遍）

- 不分大小写，**1–32 字符**
- 禁用字符：`! " # $ % & ' ( ) * + , / : ; <= > ? @ [ ] \ ^ ` { } | ~`
- 系统保留名：`.` `..` `global` `home` `homes` `printers` `satashare` `usbbackup` `usbshare`
- 首字符不能是减号或空格，末字符不能是空格
- 描述区分大小写，最多 64 个 Unicode 字符

### 建文件夹时的几个开关

| 开关 | 效果 |
|---|---|
| 启用回收站 | **建时务必勾上**；配合「只允许管理者访问」则只有管理员能进回收站 |
| 在"网上邻居"隐藏 | 不出现在 Windows 网络列表，但**不影响权限**，仍可 `\\服务器名\共享名` 访问 |
| 对无权限用户隐藏子文件夹和文件 | 仅 **Windows 文件共享协议**支持 |
| 高级权限三项 | 禁止浏览目录内容 / 禁止修改文件内容（仍可上传新建）/ 禁止下载文件 —— **仅对 File Station、FTP、WebDAV 生效** |

### 加密共享文件夹（坑很多，务必先读）

- 加密后**不能再启用文件压缩**，且**性能下降**。
- **DSM 6.2 及更早：NFS 访问不了加密共享文件夹。**
- 密钥不能含 `=` `,` `:`。
- 名称长度上限：143 个英文字符 / 47 个中文字符；macOS 访问时更严（130 英文 / 43 中文）。
- ⚠️ **重启 NAS 会卸载加密文件夹，需手动挂载**。建议在控制面板 → 共享文件夹 →
  动作 → **密钥管理器**里登记并勾「启动时装载」。
- ⚠️ **用机身 Reset 按钮重置 NAS 后，自动装载会被禁用**，加密文件夹会被卸载。
- 🚨 **密钥丢了 = 数据没了**：卸载后必须靠密钥或密钥文件挂载，两者皆失则无法恢复。
  设完浏览器会自动下载密钥文件，**务必另存**。

### 高级数据完整性（Btrfs 专属）

- 「启用数据总和检查码」：可自动用 RAID 冗余修复损毁数据。**仅 Btrfs**，
  且**创建后不可修改**。
- 不建议开启的场景：托管数据库或虚拟机、存 Surveillance Station 录像、需要大量小型随机写入的服务。
- 「启用文件压缩」的前提是**三条同时满足**：Btrfs + 未加密 + 已启用数据校验码。
  冷数据划算，多媒体文件本来已压缩、收益低。

### 协议配置要点

| 协议 | 要点 |
|---|---|
| SMB | 高级设置建议**最大 SMB 3 / 最小 SMB 1**；勾「启动传输日志」并勾全日志类型 |
| NFS | 除特殊情况**无需启用 NFSv4.1**；权限在共享文件夹 → 编辑 → NFS 权限的 **Squash** 里设 |
| iSCSI | Thick Provisioning（建时就占满，性能稳）vs Thin Provisioning（按需分配，省空间但易遇资源回收问题） |

NFS Squash 五种映射：`无映射`（保留原始权限，含 root）、`映射 root 为 admin/guest`、
`映射所有用户为 admin/guest`。

Windows 挂载 iSCSI LUN 两个注意：**>2TB 或将来可能扩容到 2TB 以上必须选 GPT**（MBR 建后不可改）；
**卷大小设为磁盘空间的 95%**，留 5% 避免空间回收滞后。

### Drive

装 Synology Drive Server → 启用团队文件夹 → 版本控制。
⚠️ **版本数量上限建议设 1–5**：每次改文件留一个备份版本，版本太多会拖垮系统响应
（不同机型建议的 Drive 文件数不同，查官网产品规格）。

## 七、第 7 章：日志

- DSM 自带**基础版**日志中心，企业用户应装完整版**日志中心套件**并配归档：
  归档设置 → 选择位置（归档到哪个文件夹）→ 可选归档规则 → 已归档日志在「日志 → 已存档」看。
- 外发到 syslog 服务器 / 本机当 syslog 服务器接收其它设备日志，都走日志中心（官方链接见下）。

## 八、第 8 章：安全加固清单（照着打勾）

| # | 项 | 要点 |
|---|---|---|
| 1 | DSM 更新 | 更新策略选「**通知我并让我决定是否安装**」；⚠️ 勾自动更新可能自动重启，**企业环境不建议** |
| 2 | 邮件通知 | 控制面板 → 通知 → 电子邮件。⚠️ SMTP 各项填**发件人**邮箱的信息，不是收件人 |
| 3 | IP 自动封锁 | 安全性 → 帐户 → 启用自动封锁（次数 + 时间窗），可导入黑白名单 |
| 4 | 账户保护 | 安全性 → 帐户 → 启用账户保护，按客户端加信任/屏蔽 |
| 5 | 防火墙 | 安全性 → 防火墙 → 启用防火墙 + 通知，自定义规则与配置文件 |
| 6 | 停用 admin / guest | 装时用了自定义管理员名的，系统已自动停用，**去确认**；<br>⚠️ 若此前用 admin 配过套件/服务，禁用可能影响部分服务 |
| 7 | 密码强度 | 用户帐号 → 高级设置 → 启用密码强度限制规则 + 启用密码期限 |
| 8 | 2 步验证 | 选项 → 个人设置 → 帐号 → 启用 2 步骤验证；先配邮件通知（手机丢了收紧急验证码）<br>⚠️ **邮箱密码栏要填「授权码」，不是邮箱密码**；勾了「记住本设备」的设备不再要验证码 |
| 9 | 改默认端口 | 控制面板 → 网络 → DSM 设置 → 改 HTTP 5000 / HTTPS 5001；<br>常用 SSH 就一起改 22，并**不用时禁用 SSH/Telnet**<br>⚠️ 改后原来走 5000/5001 的套件登录都要带新端口 |
| 10 | 安全顾问 | 主菜单 → 安全顾问 → 选「工作和业务」→ 开始扫描；<br>高级设置里**启用定期扫描计划** |

> 端口这条与 `references/lan-discovery.md` 呼应：改了 DSM 端口后 5000/5001 扫不到，
> 但 **findhostd 会把自定义 HTTP/HTTPS 端口一起报出来** —— 这正是发现脚本的价值。

## 九、DSM 6.2 → DSM 7 入口对照（实操时别找错门）

| 本指南（6.2） | DSM 7 |
|---|---|
| 控制面板 → 用户帐号 | 控制面板 → **用户和群组** |
| 存储空间管理员 | **存储管理器** |
| iSCSI Manager | **SAN Manager**（DSM 7 起 iSCSI Manager 并入其中） |
| 控制面板 → 网络 → DSM 设置 | 仍在「网络 → DSM 设置」（改名后入口位置基本一致） |
| 安全顾问 | Security Advisor（套件，需单独装） |

DSM 7 上还有一条本指南没覆盖的重要变化：**DSM 7 起部分套件要求以非 root 运行、
共享文件夹权限模型调整**，迁移前查官方知识库。

## 十、官方链接（本文件各处指向的原始出处）

| 主题 | 链接 |
|---|---|
| 知识库总入口 | <https://www.synology.cn/knowledgebase> |
| 下载中心 | <https://www.synology.cn/support/download> |
| Synology 帐户 | <https://account.synology.cn> |
| 如何选择 UPS | <https://www.synology.cn/zh-cn/knowledgebase/DSM/tutorial/Compatibility_Peripherals/How_to_Choose_UPS> |
| 哪些型号支持 RAID Group | <https://www.synology.cn/zh-cn/knowledgebase/DSM/tutorial/Storage/Which_models_support_RAID_Group> |
| 选择 RAID 类型 | <https://www.synology.cn/zh-cn/knowledgebase/DSMUC/help/DSMUC/StorageManager/storage_pool_what_is_raid> |
| Hot Spare | <https://www.synology.cn/zh-cn/knowledgebase/DSM/help/DSM/StorageManager/hotspare> |
| 创建 SSD 缓存注意事项 | <https://www.synology.cn/zh-cn/knowledgebase/DSM/tutorial/Storage/What_are_Some_Considerations_for_Creating_SSD_Cache> |
| 创建 HA 集群 | <https://www.synology.cn/zh-cn/knowledgebase/DSM/tutorial/Disaster_Recovery/How_to_create_a_high_availability_configuration_with_Synology_NAS> |
| 导入用户 | <https://www.synology.cn/zh-cn/knowledgebase/DSM/help/DSM/AdminCenter/file_user_import> |
| 加入 AD 域 | <https://www.synology.cn/zh-cn/knowledgebase/DSM/tutorial/Management/How_to_join_my_Synology_NAS_into_Windows_Active_Directory_domain> |
| 禁用 admin 后受影响的服务 | <https://www.synology.cn/zh-cn/knowledgebase/DSM/tutorial/Management/services_affected_by_disable_admin> |
| DSM 服务使用的端口 | <https://www.synology.cn/zh-cn/knowledgebase/DSM/tutorial/Network/What_network_ports_are_used_by_Synology_services> |
| 日志发送 / 接收 | <https://www.synology.cn/zh-cn/knowledgebase/DSM/help/LogCenter/logcenter_client> ／ `.../logcenter_server` |

## 十一、维护记录

- 2026-09-30：新增。基于官方 DSM 6.2 部署指南（99 页）提炼，仅保留事实性/可操作知识
  并附官方链接，未复制原文表述；补了 DSM 6.2 → DSM 7 的入口对照。
