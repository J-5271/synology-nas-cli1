# Synology NAS 官方 CLI 管理命令

来源：ima「synology开发相关」知识库 — CLI Administrator Guide for Synology NAS
（© 2015-2021 Synology Inc.）。命令路径均为 /usr/syno/sbin/，
所有工具仅允许 super-user（root）执行，成功返回 0，出错返回 >0。

> 文档较老（2021，DSM 6 时代），DSM 7 上请以设备上 `<工具> --help` 为准。

## 1. synouser — 管理本地用户

```
synouser {--help}
synouser {--add} username passwd full_name expired email app_privilege
synouser {--del} username...
synouser {--rename} old_username new_username
synouser {--modify} username passwd full_name expired email
```

| 子命令 | 说明 |
|---|---|
| --add | 一次创建一个本地用户 |
| --del | 删除指定本地用户；system、admin、guest 账号不可删除 |
| --rename | 重命名本地用户；新名若已存在则失败；system/admin/guest 不可改名 |
| --modify | 修改指定用户的信息 |

`--setpw <username> <passwd>` 在官方示例中出现（用于改 admin 密码），但不在 synopsis 里，
用前先 `synouser --help` 确认本机支持。

### 参数限制

| 参数 | 限制 |
|---|---|
| username | 不区分大小写，1–64 个 UTF-8 字符；禁用 ! " # $ % & ' ( ) * + , / : ; < = > ? @ [ ] \ ^ { } |
| passwd | 区分大小写，最多 127 个可显示字符（字母、数字、符号、空格）；可为空密码；存储前加密 |
| full_name | 最多 64 个可显示 UTF-8 字符，可留空 |
| expired | 0 不过期，1 过期 |
| email | 邮箱，可留空 |
| app_privilege | 十进制。取 0（禁止访问任何应用）或下列值之和：FTP 0x01、File Station 0x02、Audio Station 0x04、Download Station 0x08；官方示例还用到 0x10（Surveillance Station） |

不足：创建用户时不会发送欢迎邮件。

### 示例

```bash
# 改 admin 密码（示例一律占位符，禁止把真实密码写进文档/脚本）
/usr/syno/sbin/synouser --setpw admin '<新密码>'

# 创建用户 syno，密码 '<密码>'，全名 "Synology Inc."，
# 可访问 FTP + File Station + Audio Station + Download Station + Surveillance Station = 31
/usr/syno/sbin/synouser --add syno '<密码>' "Synology Inc." 0 synology@example.com 31
```

校验官方示例：21 = 0x15 = 0x01(FTP) + 0x04(Audio) + 0x10(Surveillance)。
若还要 File Station(0x02) + Download(0x08) 则为 31。

## 2. synogroup — 管理本地群组

```
synogroup {--help}
synogroup {--add} groupname username...
synogroup {--del} groupname...
synogroup {--rename} old_groupname new_groupname
synogroup {--member} groupname username...
```

| 子命令 | 说明 |
|---|---|
| --add | 创建群组，并把列出的 username 加入该群组 |
| --del | 删除群组；系统群组不可删除 |
| --rename | 群组改名；新名若已存在则失败；系统群组不可改名 |
| --member | 用给出的 username 列表覆盖该群组的成员名单 |

### 限制

groupname：不区分大小写，1–15 个 UTF-8 字符（比 username 短，注意！）；
禁用符号集合同上；首字符不能是减号或空格，末字符不能是空格。

## 3. synoshare — 管理共享文件夹

```
synoshare {--help}
synoshare {--add} sharename share_desc share_path user_list_na user_list_rw user_list_ro \
                  share_visible adv_private
synoshare {--del} {TRUE|FALSE} sharename...
synoshare {--rename} old_sharename new_sharename
synoshare {--setuser} sharename {NA|RO|RW} {+|-|=} user_list
```

| 子命令 | 说明 |
|---|---|
| --add | 创建新共享文件夹 |
| --del TRUE\|FALSE | TRUE：连配置带数据一起删；FALSE：只删配置，目录仍留在文件系统，必须手工删除目录，否则 DiskStation 重启后会用默认权限恢复该共享。只能删普通共享文件夹，不能删 Hybrid Share |
| --rename | 改名；新名已存在则失败 |
| --setuser | 改 ACL。第二段权限：NA 禁止访问 / RO 只读 / RW 读写；第三段动作：+ 追加、- 移除、= 替换整个列表 |

### 限制

| 参数 | 限制 |
|---|---|
| sharename | 不区分大小写，1–32 UTF-8 字符；首字符不能是减号或空格，末字符不能是空格。保留给系统：global、homes、home、printers、.、..、surveillance、usbbackup、usbshare、esatashare |
| share_desc | 区分大小写，最多 64 个可显示 Unicode 字符，可为空串 |
| share_path | 必须是合法目录；路径不存在时会自动创建 |
| user_list | 逗号分隔，组名前要加 @，如 'user1,user2,@group3'；用户或组不存在会报错 |
| share_visible | 1 在「网上邻居」显示，0 隐藏。隐藏不影响访问权限，有权限的用户仍可用 \\server\share 访问 |
| adv_private | 高级权限，十进制：0 或 禁用目录浏览 0x1、禁止修改已有文件 0x2、禁止下载文件 0x4 之和 |

### 示例

```bash
# 创建 share 'private'，ACL 全空，可见(1)，无高级限制(0)
/usr/syno/sbin/synoshare --add private "Comment" /volume1/private "" "" "" 1 0

# 给 syno 和 @stuff 组加 private 的读写权限
/usr/syno/sbin/synoshare --setuser private RW + syno,@stuff
```

> ⚠️ 权限粒度上限（2026-09-21 实测）：--setuser 只有 NA / RO / RW 三档，
> 做不了「能删文件但不能删文件夹」「只能删自己创建的」这类需求。
> 这类需求走 DSM 的 Windows ACL 自定义权限，机理是 ACL 把「删除」拆成
> Delete(D) 与 Delete subfolders and files(DC) 两个位。详见 SKILL.md
> 「细粒度权限：synoshare 做不到」一节。
> 另注：系统共享文件夹 photo / satashare / sdshare / surveillance / usbshare 不支持 Windows ACL；
> 单对象 ACL 上限 200 条。

## 4. synonet — 管理网络设置 ⚠️ 会导致断网

```
synonet {--help}
synonet {--DHCP} interface
synonet {--manual} interface ip mask [--dont restart service]
synonet {--set_gateway} gateway
synonet {--set_dns} dns
synonet {--set_mutu} interface MTU
synonet {--set_hostname} hostname [--dont restart service]
```

| 子命令 | 说明 |
|---|---|
| --DHCP | 设为 DHCP |
| --manual | 设静态 IP，后跟 IP 与掩码 |
| --set_gateway | 所有网卡都是静态 IP 时手动设置默认网关 |
| --set_dns | 所有网卡都是静态 IP 时手动设置 DNS |
| --set_mutu | (官方原文如此，非 set_mtu) 设 MTU，默认 1500，仅在千兆网络下生效 |
| --set_hostname | 修改服务器名 |

### 限制

- interface：只能是 eth0 或 eth1（eth1 需双网口机型）
- ip/mask/gateway/dns：IPv4 格式
- hostname：不区分大小写，1–15 个字符，字母/数字/下划线/减号，首字符必须是字母
- MTU：只能取 1500、2000、3000、4000、5000、6000、7000、8000、9000

### 示例

```bash
/usr/syno/sbin/synonet --manual eth0 192.168.14.64 255.255.0.0
/usr/syno/sbin/synonet --set_gateway 192.168.15.254
/usr/syno/sbin/synonet --set_dns 192.168.252.254
/usr/syno/sbin/synonet --set_hostname cn406e
```

## 5. synoservice — 管理服务

```
synoservice {--help}
synoservice {--list} [running]
synoservice {--enable|--disable} service...
synoservice {--start|--stop|--restart} service...
synoservice {--keyon|--keyoff} service...
synoservice {--detail} service...
```

| 子命令 | 说明 |
|---|---|
| --list | 列出所有可用服务；带 running 只列正在运行的 |
| --enable / --disable | 启用/禁用并保存设置，且立即启动/停止该服务 |
| --start / --stop / --restart | 启停/重启，不改设置；启动前会检查服务是否已启用 |
| --keyon / --keyoff | 只改保存的设置，不影响服务当前运行状态 |
| --detail | 显示该服务的全部相关信息 |

> 写 ds_configure.sh 做群装机时用 --keyon 而不是 --enable（那时服务还没起来）。

### 可用服务名（官方列出）

web(Web Station)、photo(Photo Station)、netbkp(网络备份)、download(Download Station)、
media(DLNA)、audio(Audio Station)、itunes、mysql、printer、
surveillance、userhome(User Home)、ftp、telnet、ssh、
nfs、afp、samba(CIFS)、filestation(File Station)、https

### 示例

```bash
/usr/syno/sbin/synoservice --enable ssh
/usr/syno/sbin/synoservice --list running
/usr/syno/sbin/synoservice --detail samba
```

> 注意：禁用 SSH 服务会立刻断开所有 SSH 连接（含正在跑的加密网络备份），
并建议之后重跑备份任务。

> ⚠️ 实测：DSM 7.3-81180 上 /usr/syno/sbin/synoservice 已不存在，改用 systemd。

## 6. synowin — 工作组 / ADS 域

```
synowin {--help}
synowin {--joinWorkgroup} workgroup
synowin {--joinDomai} short_domain_name|full_domain_name username password \
        [-d dns_ip] [-i kdc_ip] [-n netbios_name] [-f fqdn_name]
```

> ⚠️ 官方原文拼写就是 `--joinDomai`（缺 n），照抄别"修正"成 --joinDomain。

- --joinWorkgroup：加入工作组，会忽略 ADS 域设置
- --joinDomain：加入 ADS 域，需提供有 Domain Admin 权限的账号

### 限制

| 参数 | 限制 |
|---|---|
| workgroup | 1–15 字符；非法字符 [ ] ; " < > * + = n / \| ? ,。若含 &，Mac OS 10.4.4 及更早无法通过 samba 连接 |
| domain_name | 含点（synology.com）视为完整域名；不含点（synology）视为短域名 |
| kdc_ip | DC 的 IP，多个用逗号分隔；在最后一个 IP 后再加逗号 + *，可在全部失败后自动尝试其他 DC。若是你自定义过 DCs 请谨慎使用 |
| netbios_name | 域的 NetBIOS 名 |
| fqdn_name | 域的 FQDN |

## 通用提示

- 命令不在 PATH 里，请用绝对路径 /usr/syno/sbin/<工具>
- 返回非 0 时，去查 references/error-codes.md
- 忘记语法就跑 --help；怀疑本机没有该工具就 `ls /usr/syno/sbin/ | grep <工具>`
