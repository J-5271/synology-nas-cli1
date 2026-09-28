# Synology 错误码对照表

来源：ima「synology开发相关」知识库 — CLI Administrator Guide for Synology NAS 第 3 章。
所有 syno 系列 CLI 工具成功返回 0，出错返回 >0；
排查时优先对照下表定位根因。

## 与常用 CLI 最相关的（重点）

| 名称 | 码 | 含义 |
|---|---|---|
| ERR SUCCESS | 0x0000 | 操作成功 |
| ERR ACCESS DENIED | 0x0300 | 拒绝访问（多半没 root 权限，先确认已 sudo -i） |
| ERR BAD PARAMETERS | 0x0D00 | 参数非法 |
| ERR USAGE | 0x3100 | 参数用法错误（synopsis 没照写） |
| ERR INVALID USERNAME | 0x1A00 | 用户名非法 |
| ERR INVALID PASSWORDNAME | 0x1B00 | 密码格式非法 |
| ERR USER EXISTS | 0x1C00 | 用户已存在 |
| ERR NO SUCH USER | 0x1D00 | 用户不存在 |
| ERR WRONG PASSWORD | 0x1E00 | 密码错误 |
| ERR TOO MANY USERS | 0x1F00 | 用户数量超限 |
| ERR USER BATCH CONFLICT | 0x2F00 | 发现重名 |
| ERR INVALID GROUPNAME | 0x1600 | 组名非法 |
| ERR GROUP EXISTS | 0x1700 | 组名已存在 |
| ERR NO SUCH GROUP | 0x1800 | 组不存在 |
| ERR TOO MANY GROUPS | 0x1900 | 组数量超限 |
| ERR RESERVED_GROUP | 0xB700 | gid 小于 GID_MIN（动到系统组了） |
| ERR RESERVED_USER | 0xB800 | uid 小于 UID_MIN（动到系统用户了） |
| ERR INVALID SHARENAME | 0x1200 | 共享名非法 |
| ERR SHARE EXISTS | 0x1300 | 共享名已存在 |
| ERR NO SUCH SHARE | 0x1400 | 共享不存在 |
| ERR TOO MANY SHARES | 0x1500 | 共享数量超限 |
| ERR_NOT_DIRECTORY | 0xA200 | 指定路径不是目录 |
| ERR_DIRECTORY_NOT_EXISTS | 0xA300 | 目录不存在 |
| ERR_IS_DIRECTORY | 0xA500 | 指定路径是个目录 |
| ERR_INVALID_PATH | 0xBE00 | 路径非法 |
| ERR_INVALID_PATHNAME | 0x9900 | 卷路径非法 |
| ERR_NAME_EXISTS | 0xC000 | 名称已存在 |
| ERR_NAME_TOO_LONG | 0xC300 | 文件名过长 |
| ERR_SERVICE_EXISTS | 0xA000 | 服务已存在 |
| ERR_SERVICE_NOT_EXISTS | 0xA100 | 服务不存在 |
| ERR_SERVICE_NOT_SET | 0xA400 | 服务未设置 |
| ERR_INTERFACE_EXISTS | 0xBB00 | 网卡接口已存在 |
| ERR_NO_SUCH_INTERFACE | 0xBC00 | 网卡接口不存在 |
| ERR_TOO_MANY_INTERFACE | 0xBD00 | 网卡接口超限 |
| ERR_INVALID_SERVERNAME | 0x0E00 | 服务器名非法（主机名 1–15 字符且首字符必须是字母） |
| ERR_INVALID_DOMAINNAME | 0x0F00 | 域名非法 |
| ERR_INVALID_NETNAME | 0x1000 | IP 地址格式非法 |
| ERR_SERVER_UNREACHABLE | 0x1100 | 找不到 Windows 域控制器 |

## 文件 / 文件系统

| 名称 | 码 | 含义 |
|---|---|---|
| ERR PATH NOT FOUND | 0x0600 | 路径未找到 |
| ERR FILE NOT FOUND | 0x0700 | 文件未找到 |
| ERR FILE EXISTS | 0x0800 | 文件已存在 |
| ERR OPEN Failed | 0x0900 | 打开文件失败 |
| ERR READ Failed | 0x0A00 | 从设备读数据失败 |
| ERR WRITE failed | 0x0B00 | 写数据到设备失败 |
| ERR CREATE failed | 0x0C00 | 创建文件/目录失败 |
| ERR RNAMEFAILED | 0x2800 | 重命名失败 |
| ERR REMOVEFAILED | 0x3900 | 删除文件失败 |
| ERR MOVEFAILED | 0x3A00 | 移动文件失败 |
| ERR COPYFAILED | 0x3B00 | 复制文件失败 |
| ERR MKDIRFAILED | 0x3C00 | 创建目录失败 |
| ERR SEEK failed | 0x2600 | seek 失败 |
| ERR STAT failed | 0x2700 | stat 失败 |
| ERR PATH_CONFLICT | 0xA600 | 源和目标相同（同名或硬链接） |
| ERR_FAT_FILESIZE_TOO_LARGE | 0xA700 | FAT 文件系统下文件超过 4GB |
| ERR_FAT_FILENAME_ILLEGAL | 0xA800 | FAT 文件系统下文件名含非法字符 |
| ERR ENCKEY VERIFY | 0xAB00 | 共享加密：密钥不正确 |
| ERR ENCKEY LOST | 0xAC00 | 共享加密：本地密钥副本丢失 |

## 空间 / 配额

| 名称 | 码 | 含义 |
|---|---|---|
| ERR NOT ENOUGH QUOTA | 0x2400 | 用户配额不足 |
| ERR NOT ENOUGH VOLUME SPACE | 0x2500 | 卷可用空间不足 |
| ERR NOT ENOUGH SPACE | 0x2900 | 文件系统可用空间不足 |
| ERR_SIZE_TOO_SMALL | 0xBF00 | 磁盘容量太小 |
| ERR_VOLUME_SIZE_TOO_LARGE | 0x8200 | 指定卷大小超限 |
| ERR_VOLUME_NOT_FOUND | 0x8300 | 找不到卷 |
| ERR_VOLUME_READ_ONLY | 0x8400 | 卷只读 |
| ERR_QUOTA_NOT_FOUND | 0x9100 | 用户未设置卷配额 |
| ERR_QUOTA_PARAM_INVALID | 0x9200 | 配额文件损坏，或命令/配额类型非法 |
| ERR_QUOTA_MOUNTING | 0x9300 | 重新挂载文件系统以启用用户/组配额失败 |
| ERR_QUOTA_QUOTACHECK | 0x9400 | quotacheck 执行失败 |
| ERR_QUOTA_QUOTAON | 0x9500 | quotaon 执行失败 |
| ERR_QUOTA_QUOTAOFF | 0x9501 | quotaoff 执行失败 |

## 磁盘 / RAID / iSCSI

| 名称 | 码 | 含义 |
|---|---|---|
| ERR NO VOLUME ID | 0x6000 | 找不到卷 ID |
| ERR NO DISK ID | 0x6100 | 找不到磁盘 ID |
| ERR NOT ENOUGH SD | 0x6200 | 硬盘数量不足 |
| ERR SD SIZE NOT AIGN | 0x6300 | 所选硬盘容量不一致 |
| ERR DEVICE BUSY | 0x6400 | 卷被占用，无法销毁 |
| ERR INVALID SD | 0x6500 | 无效 SD |
| ERR FORMAT FAIL | 0x6600 | 重新格式化磁盘失败 |
| ERR CANNOT REBUILD DISK | 0x6700 | 重建磁盘失败 |
| ERR BROKEN RAID CONF | 0x6800 | RAID 信息不正确 |
| ERR DISK TOO SMALL | 0x6900 | 磁盘容量太小 |
| ERR CANNOT GET MNTINFO | 0x6A00 | 获取挂载信息失败 |
| ERR BROKEN DISK INFO | 0x6B00 | 磁盘信息不正确 |
| ERR_DISK_IO_FAILED | 0x6C00 | 磁盘 I/O 失败 |
| ERR_BAD_DISKSECTOR | 0x6D00 | 发现坏道 |
| ERR_READ_GEO | 0x3000 | 读取磁盘 geometry 失败 |
| ERR_FS_NOT_FOUND | 0xC200 | 找不到文件系统 |
| ERR_EXCEED_ISCSI_SIZE_IN_VOLUME | 0xC100 | iSCSI 文件预留大小超限 |

## 系统 / 未知

| 名称 | 码 | 含义 |
|---|---|---|
| ERR NOT ENOUGH MEMORY | 0x0100 | 内存分配不足 |
| ERR OUT OF MEMORY | 0x0200 | 操作耗尽内存 |
| ERR LOCK failed | 0x0400 | 无法锁定文件 |
| ERR UNLOCK failed | 0x0500 | 无法解锁文件 |
| ERR OP FAILURE | 0x2A00 | 指定操作执行失败 |
| ERR OP UNREGISTERED | 0x2D00 | 操作不被允许 |
| ERR DEV UNCONFIG | 0x2B00 | 设备未就绪 |
| ERR DEV UNMOUNTED | 0x2C00 | 设备未挂载 |
| ERR TIMER EXPIRED | 0x2E00 | 定时器超时 |
| ERR USER CANCEL | 0xA900 | 用户取消操作 |
| ERR INTERRUPTED | 0xAA00 | 被信号中断 |
| ERR_UNKNOWN | 0x8000 | 无法由所调函数判定错误 |
| ERR_SYS_UNKNOWN | 0x8100 | 系统出错，但所调函数无法给出真实错误 |
| ERR_FORK_FAIL | 0x9600 | fork 失败 |
| ERR_RAID_ENUM_FAIL | 0x9700 | 枚举系统 RID 设备失败 |
| ERR_ENUM_FAIL | 0x9800 | 枚举失败 |

## 维护记录

- 2026-09-27 周度巡检：本周无新增/新验证的错误码，上表为官方 CLI 指南原表 + DS918+ 实测补充。

## 排查套路

- 先看是不是 0x0300 ACCESS DENIED —— 没走 sudo -i 提权。
- 再看是不是 0x0D00 / 0x3100 —— synopsis 顺序或参数个数不对，跑 --help 核对。
- 名字类错误（USER/GROUP/SHARE EXISTS / NOT FOUND / INVALID）对照
cli-commands.md 里各自的字符数与禁用的符号集合——用户 64 字符、群组 15 字符、共享 32 字符，很容易踩。
- 0x8000 / 0x8100 拿不到有效信息时，配合 dmesg 与 /var/log/ 下的日志继续追。
