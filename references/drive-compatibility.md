# 第三方硬盘兼容性（「硬盘未验证」怎么处理）

> **素材**：`007revad/Synology_HDD_db` v3.6.131 源码通读 + `修改群晖硬盘未验证.pdf` 操作记录
> + Synology 官方 Drive compatibility policies 页面
> **核对日期**：2026-11-09（上游当时最新 release 为 **v3.6.139**，2026-08-30 发布）
>
> ⚠️ **本篇不是纯实测**：脚本行为、数据库路径、参数开关均已对源码逐行核对（引用了行号），
> 但**未在本机真机执行**。落到客户设备前，先在测试机跑一遍并核对输出。
> ⚠️ **属改配置**：动的是 `/var/lib/disk-compatibility/*.db` 与 `/etc.defaults/synoinfo.conf`，
> 按本技能包的只读优先策略，必须用户明确点名才执行，执行前先备份。

---

## 1. 先分清两条路径（这是最容易被搞混的地方）

| | 路径 A：关掉兼容性检查 | 路径 B：把盘写进兼容库 |
|---|---|---|
| 动作 | `synosetkeyvalue … support_disk_compatibility no` | `syno_hdd_db.sh` 改兼容库 db 文件 |
| 本质 | DSM **不再检查** | DSM **认为该盘是官方验证过的** |
| 盘的状态 | 仍是「未验证」 | 变成 `compatibility: support` |
| 告警 | 消失 | 消失 |
| 存储池 / 阵列 | 可建 | 可建 |
| 数据去重 | **可用** | 可用（脚本带 `-f` 时**失效**） |
| 群晖盘固件升级 | **可用** | 可用（脚本带 `-f` 时**失效**） |
| NVMe 建缓存 / 建卷 | 仍受限 | 可放开 |
| 第三方 SSD TRIM | 受限 | 可放开 |

**结论**：A 是「让 DSM 别看」的止血招，B 是「让 DSM 认」的正解。
25 系列（DS925+、DS1825+ 等 2025 机型）新机首次装系统时**两个都要用，且顺序不能反**：
先用 A 打通装机，再用 B 补库。

---

## 2. 路径 A：手动关掉兼容性检查

DSM 的配置分「当前生效」和「默认值（重启后据此重建）」两份，**两个都要写**：

```bash
/usr/syno/bin/synosetkeyvalue /etc.defaults/synoinfo.conf support_disk_compatibility no   # 管重启后
/usr/syno/bin/synosetkeyvalue /etc/synoinfo.conf          support_disk_compatibility no   # 管当前会话
```

注意 `synosetkeyvalue` 的写法是 **`synosetkeyvalue <文件> <键> <值>`**，三个参数之间是空格。
从 PDF 里复制粘贴时容易粘成一行（如 `support_disk_compatibilityno`），
那个键值对会被写成 `support_disk_compatibilityno`，等于没生效也看不出来。**先 `synogetkeyvalue` 回读确认。**

回滚：把 `no` 改回 `yes`，两个文件都改。

---

## 3. 路径 B：syno_hdd_db.sh（推荐）

### 3.1 它到底改什么

脚本里写死的路径（`syno_hdd_db.sh` 第 669–670 行）：

```bash
dbpath=/var/lib/disk-compatibility/          # 兼容库目录，改这里的 <model>_host.db / *.db.new
synoinfo="/etc.defaults/synoinfo.conf"       # 开关只写这一个文件
```

流程：取机型与 DSM 版本 → 枚举已装盘的型号与固件版本 → 检查是否已在库 →
不在库的按型号补进去（`"compatibility": "support"`）→ 首次运行时把原 db 备份。

### 3.2 落地步骤

1. 从 releases 下载 **Source code (zip)**，解压到 NAS 的共享文件夹。
   - ❌ **不要放 M.2 卷**：DSM 或存储管理器升级后，M.2 卷在脚本运行前不可用，脚本自己就起不来。
   - ❌ 不要从网页复制脚本正文，会拿到 HTML；也不要改换行符（见 §6.1）。
2. SSH 登录管理员账号，`sudo -i`（DSM 6+ 不能直接 ssh root）。
3. 加执行权限并跑：
   ```bash
   cd /volume1/<共享名>/Synology_HDD_db-main
   chmod +x ./syno_hdd_db.sh
   ./syno_hdd_db.sh -fr        # 首次：-f 强制不检查 + -r 关内存兼容告警
   reboot
   ```
4. 成功标志：输出里有该盘型号、`"compatibility": "support"`，末尾
   `DSM successfully checked disk compatibility.` 与 `You may need to reboot…`。
5. 建开机任务兜底（见 §4）。

### 3.3 必带文件

同目录下必须有 `syno_hdd_db.sh` + `syno_hdd_vendor_ids.txt`；
只有当你用 M2D20 / M2D18 / E10M20-T1 这类 PCIe 转接卡且机型不官方支持时，才需要 `bin/dtc`。

---

## 4. 开机任务（DSM 升级后会重置，必须兜底）

**控制面板 → 任务计划 → 新增 → 触发的任务 → 用户定义的脚本**

| 项 | 值 |
|---|---|
| 用户 | **root**（必须，否则改不动系统文件） |
| 事件 | **开机** |
| 脚本 | `/volume1/<共享名>/Synology_HDD_db-main/syno_hdd_db.sh -nr --autoupdate=3` |
| 勾选 | 启用；建议勾「发送运行详情邮件」+「仅异常时发送」 |

`--autoupdate=3` 表示只自动更新「发布已满 3 天」的版本，避免抢到刚发出来还没人验证的 release。

---

## 5. 参数怎么选

| 参数 | 作用 | 建议 |
|---|---|---|
| `-n` / `--noupdate` | 阻止 DSM 自动更新兼容库（会覆盖你的修改） | **长期挂开机任务必带** |
| `-r` / `--ram` | 关内存兼容告警，并把「最大内存」对齐到实装值 | 装了非群晖内存就带 |
| `-f` / `--force` | 强制 DSM 不检查盘兼容性 | **最后手段**，见 §6.2 |
| `-i` / `--incompatible` | 把「不兼容」直接改成「支持」 | 同 `-f`，非必要不用 |
| `-s` / `--showedits` | 打印对 db 文件的具体修改 | **调试期建议带**，能看到到底写了什么 |
| `-S` / `--ssd` | 给内部 HDD 设 write_mostly，让 DSM 优先读内部 SSD | 有 SSD 且想提速时 |
| `--restore` | 撤销脚本的全部改动（不含 `-S`） | 回滚用；含 SSD 设置要 `--restore --ssd=restore` |
| `-e` / `--email` | 计划任务邮件里去掉颜色控制符 | 挂计划任务时建议带 |

---

## 6. 源码里挖出来的坑

### 6.1 `-f` 是个**双向开关**，不带它会把检查重新打开

`syno_hdd_db.sh` 第 2216–2240 行：

```bash
sdc=support_disk_compatibility
setting="$(/usr/syno/bin/synogetkeyvalue $synoinfo $sdc)"
if [[ $force == "yes" ]]; then
    … 写成 no → "Disabled support disk compatibility."
else
    … 如果当前是 no，就主动写回 yes → "Re-enabled support disk compatibility."
fi
```

也就是说：**「先手动跑 `-fr`，开机任务写成 `-nr`」这个组合，第二次运行就会把上次关掉的检查重新打开。**

在本方案下这不算错——盘这时候已经进库了，检查开着也不报错；但必须知道两件事：

- 别指望「不带 `-f`」能保留「免检查」状态。
- 反过来，开机任务长期带 `-f`，就等于**永久放弃数据去重 + 群晖盘固件升级**（README 原文：
  "Using this option will prevent data deduplication from being available, and prevent firmware
  updates on Synology brand drives"）。

### 6.2 脚本只写 `/etc.defaults/synoinfo.conf`

路径 A 手敲要写两个文件，脚本只写 `defaults` 那份（当前会话不立即生效，重启后才生效）。
所以**跑完脚本通常要重启**，这一点 README 也写了。

### 6.3 换行符 / 复制污染

`bash\r`、光标卡住不动、`syntax error near unexpected token` —— 三个症状都指向同一类根因：
文件是从网页复制的、或者被 Windows/Mac 编辑器改过行尾。
**只用 releases 里的 zip**，报错时先 `file ./syno_hdd_db.sh` 看一眼。

### 6.4 路径含空格要加引号；`sudo -s` 后面整条要引起来

```bash
sudo -s "/volume1/my scripts/syno_hdd_db.sh -n"
```

### 6.5 NVMe 显示 Unknown brand

说明 DSM 不认识该盘厂商 ID，脚本会提示你补进 `syno_hdd_vendor_ids.txt`（格式 `0x<VID>="厂商名"`）。
该文件里已经预置了 Solidigm / Lexar / 致钛 / 梵想 / 雷克沙 / 光威 等 20 个常见国产与非国产 ID。

---

## 7. 2025 系列 / DSM 7.3 的政策现状（官方口径）

官方政策页：<https://kb.synology.com/en-global/DSM/tutorial/Drive_compatibility_policies>

按项目 `2025_plus_models.md`（2025-10-07 更新）：

- **DSM 7.3 已移除 DSM 7.2.2 时代对 2025 Plus 机型的大部分限制**，仍保留两条：
  1. 第三方 NVMe **不能建缓存、不能建存储卷**；
  2. 用未验证第三方盘时存储管理器**仍大量告警**。
- 这两条都能用 `syno_hdd_db.sh` 解决。

DSM 7.2.2 时代的硬限制（了解即可，用于判断老客户设备的状态）：
新机只有未验证 HDD 时**装不上 DSM**；第三方盘不能做热备、不能扩池、不能建 SSD 缓存、
不能删池重建。装机阶段绕过法：

```bash
# 浏览器访问 http://<NAS-IP>:5000/webman/start_telnet.cgi 开启 telnet
telnet <NAS-IP>          # 登录名 root，密码 101-0101
touch /tmp/installable_check_pass     # VM 里要循环 touch，否则会被清掉
# 刷新安装页 → 装 DSM → 装完再补 §2 的 synosetkeyvalue
```

> 这段是社区做法，不是官方支持能力。写进方案要标明「非官方支持路径」。

---

## 8. 只读核对（动手之前先跑这个）

```bash
# 机型 / DSM 版本
cat /etc/VERSION

# 看某个盘在库里被标成什么（把 <model> 换成实际机型，如 ds925+）
python3 -c "
import json,glob
for f in glob.glob('/var/lib/disk-compatibility/*host*.db*'):
    print('==',f)
"
grep -o '"[A-Z0-9]\{6,\}": *{[^}]*"compatibility": *"[a-z]*"' /var/lib/disk-compatibility/<model>_host.db | head

# 当前兼容性检查开关（两个文件各看一次）
/usr/syno/bin/synogetkeyvalue /etc.defaults/synoinfo.conf support_disk_compatibility
/usr/syno/bin/synogetkeyvalue /etc/synoinfo.conf          support_disk_compatibility

# 脚本会认到的盘
lsblk -o NAME,SIZE,MODEL,SERIAL
```

判读：`support` = 已验证；`not_supported` / `incompatible` = 需要补库；
`support_disk_compatibility=no` = 检查已关（告警会消失，但盘本身仍是未验证）。

---

## 9. 风险与回滚

| 风险 | 说明 / 应对 |
|---|---|
| 非官方支持 | 出问题群晖工单可能不认。客户环境必须在方案里明示这是非官方路径 |
| DSM 升级重置 | 大版本升级会重写兼容库 → 靠开机任务兜底 + `-n` 防止 DSM 覆盖 |
| `-f` 副作用 | 去重失效、群晖盘不能升固件。只在该盘死活显示不支持时才用 |
| 改错 db 文件 | 脚本首次运行会备份原文件；也可 `--restore` 一键回滚 |
| 放 M.2 卷 | 升级后 M.2 卷不可用 → 脚本起不来 → 开机任务静默失败 |
| 扇区/固件差异 | 同型号不同固件版本可能表现不同，脚本是按「型号+固件」匹配的 |

---

## 10. 版本与供应链

| 项 | 值（2026-11-09 实时核对） |
|---|---|
| 本地副本 | v3.6.131（2025-06-19 的文件） |
| 上游最新 release | **v3.6.139**（2026-08-30） |
| 仓库 | `007revad/Synology_HDD_db`，约 6.0k ★，**MIT**，长期活跃（最近提交 < 1 个月） |

**取用前先看 release 页**，v3.6.131 恰好是「修 DSM 7.4 的 rules db 文件」那一版，
7.4 能跑，但之后 8 个版本的修复（含备份逻辑、6TB 容量的 `size_gb` 修正等）都没吃到。

许可证 MIT，可自由使用与二次分发；但**群晖的兼容库文件本身不适用 MIT**，
本方案只是本地改写设备上的数据库，不涉及分发群晖受版权保护的文件。
