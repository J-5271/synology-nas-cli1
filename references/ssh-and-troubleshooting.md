# SSH 登录与常见故障处理

来源：Synology 官方知识中心 https://kb.synology.cn/zh-cn/
（SSH root 登录教程、SSH RSA 密钥登录教程、终端机帮助页、Telnet/SSH 标签页文章）。

## 一、启用 SSH（一次性）

| 设备 | 路径 |
|---|---|
| Synology NAS（DSM） | 控制面板 > 终端机和 SNMP > 终端机 → 勾选「启用 SSH 服务」 |
| Synology Router（SRM） | 控制面板 > 服务 > 系统服务 > 终端机 |

- 可修改 SSH 端口号。官方建议不要用默认 22。
- 可在「高级设置」里调 SSH 加密算法安全等级（高/中/低/自定义），
自定义可选加密 (ciphers)、KEX、MAC 三组算法；部分机型支持硬件加速密码，
勾选「仅使用硬件加速密码」可提升 SSH 相关服务（含加密网络备份、SFTP）速度。
⚠️ 提高安全等级或仅用硬件加速算法，可能让部分 SSH 客户端因兼容性连不上。
- 注意：网络备份、SFTP 等服务会自动启用 SSH 并打开 22 端口，
若要 SSH 登录 DSM 仍需在终端机页面勾选启用。

谁能登：

| 版本 | 账号 |
|---|---|
| DSM 6.0 / SRM 1.3 及以上 | administrators 群组中的用户（登录后 sudo -i） |
| DSM 5.2 / SRM 1.2 及更早 | root 直接登录 |

其它要点：

- SSH/Telnet 登录时密码不能为空
- 禁用 SSH 会立即断开所有 SSH 连接（含正在运行的加密网络备份任务），需重新执行备份

## 二、密码登录 + sudo -i（官方标准流程）

```bash
ssh <管理员账号>@<NAS_IP> -p <SSH端口>     # 例：ssh myadmin@<NAS_IP> -p 22
# 输入该管理员账号的密码
sudo -i                                     # 再输入一次同一个密码
```

Windows 早期版本（如 Win7）用 PuTTY：Host Name 填 myadmin@IP，Port 填 SSH 端口。

DSM 5.2 / SRM 1.2 及更早：`ssh root@<IP> -p <端口>`，密码用默认 admin 的密码。

## 三、RSA 密钥登录（DSM 6.2.4+，自动化推荐）

官方流程：

- 用 administrators 群组账号登录 DSM → 控制面板 > 终端机和 SNMP > 终端机 → 启用 SSH。
- 以管理员身份用密钥登录时：
  - 控制面板 > 用户和群组（DSM 7.0+）/ 用户（DSM 6.2.4）> 高级 > 用户主目录
→ 勾选「启用用户主目录服务」
- 确保 homes 共享文件夹保持默认权限，不要给非管理员任何读写权限
- 生成本地密钥：`ssh-keygen -t rsa -b 4096`（Win7 及更早用 PuTTYgen）
- 把 id_rsa.pub 的内容上传到 NAS，追加到相应用户的 ~/.ssh/authorized_keys
（root 则是 /root/.ssh/authorized_keys）。volumeX 指密钥文件所在卷，如 volume1。
- 若密钥生成时设了 passphrase，连接时会被要求输入。

macOS 上 .ssh 目录隐藏，Finder 里按 ⌘ + Shift + . 显示。

## 四、常见故障

### 1. scp 上传报 "No such file or directory"（命令语法明明是对的）

原因：自 OpenSSH 9.0 起旧版 scp/rcp 协议默认被弃用。客户端 ≥ 9.0 时上传失败。
用 `ssh -V` 确认客户端版本。

解决：给 scp 加 `-O`（大写字母 O） 强制走旧协议：

```bash
scp -O -P <端口> localfile.txt myadmin@<IP>:/volume1/homes/
```

注意 scp 的端口参数是大写 -P，与 ssh 的小写 -p 不同。

### 2. Could not chdir to home directory

用户主目录不存在或 homes 未启用。参见第三节第 2 步启用「用户主目录服务」。
一般不影响命令执行，但会刷屏。

### 3. 收到「SSH 设置异常变更，NAS 可能已被入侵」的 DSM 通知

DSM 6.2 场景下官方建议：先备份数据，再重装 DSM。
用 Hyper Backup 备份共享文件夹、套件和系统设置后再重置。

### 4. 改网络后失联

`synonet --manual / --set_gateway / --set_dns` 会改变 NAS 网络配置。
操作前确认有物理控制台 / KVM / IPMI 兜底，否则别动。

### 5. 首次连接 host key 校验

自动化脚本建议用 `-o StrictHostKeyChecking=accept-new`（首次自动接受，后续严格比对），
避免交互卡死；但别用 `-o UserKnownHostsFile=/dev/null` 全盘关闭校验。

### 6. 公网能开网页 ≠ SSH 也能连

DSM 网页端口（如 5000 / 自定义端口）被路由器转发了，不代表 SSH 端口也转发了。
实测一台 DSM 在公网只暴露 3000，22 / 5000 / 5001 全部 Connection refused，
但同一台机器在内网 <NAS_IP>:22 正常返回 SSH-2.0-OpenSSH_8.2。

排查顺序：`ping <ip>` → 扫端口 → 看 DSM 里 SYNO.Core.Terminal 的 ssh_port → 再谈认证。

### 7. 自动化执行时的两个坑（脚本已处理，手搓时要注意）

① 密码登录别用 `echo pw | ssh`
SSH 客户端从 /dev/tty 读密码，stdin 喂不进去，会一直卡在 password: 提示。
用 paramiko 之类的库在进程内认证，或者干脆配密钥。

② sudo -i 会吞掉命令里的换行
实测：`sudo -i bash -c $'echo AAA\necho BBB'` 实际执行成 `echo AAAecho BBB`，
换行被静默丢弃（不加 sudo 时正常）。所以多行脚本必须先压平成单行（用 ; 或 && 连接）
再交给 sudo，行尾的反斜杠续行要先合并。
scripts/nas_exec.py 里的 flatten() 就是干这个的。
（后续实测更严重：连 $变量 都会在执行前被展开成空，最终改用 base64 中转。）

### 8. timeout 命令在 macOS 上不存在

写自动化脚本时别依赖 GNU timeout，macOS 默认没有。用脚本自身的超时参数
（nas_exec.py --timeout）或 Python 的 subprocess.run(timeout=...)。

## 五、其它实用命令（非官方文档内容，设备上验证过再用于生产）

Synology CLI 指南未收录但常用于 NAS 运维的命令，DSM 版本差异大，
执行前务必在设备上确认其存在与语法：

| 用途 | 命令 |
|---|---|
| 查看 DSM 版本 | `cat /etc/VERSION`（含 major/minor/buildnumber/smallfixnumber） |
| 磁盘空间 | `df -h`（关注 /volume*、/dev/mapper/*） |
| 套件管理 | `synopkg list` / `synopkg start\|stop\|...` |
| 服务管理（DSM 7） | `systemctl restart <svc>` / `synosystemctl`（DSM 7 引入，与 synoservice 并存） |

惯用法：先 discover 后 execute

```bash
ls /usr/syno/sbin/ | grep -i syno    # 本机实际有哪些 CLI 工具
<工具> --help                         # 该版本的真实语法
```

不确定的东西，先查官方知识库 https://kb.synology.cn/zh-cn/，不要凭记忆下命令。

## 六、维护记录

- 2026-09-27 周度巡检：本周无新增 SSH 故障案例。现有条目对应的实测环境为
  DS918+ / DSM 7.3-81180（内网 <NAS_IP>:22，OpenSSH_8.2）。
- 相关补充：DSM 共享文件夹的细粒度权限（能删文件不能删文件夹）不属于 SSH/CLI 范畴，
  见 SKILL.md「细粒度权限：synoshare 做不到」一节。
