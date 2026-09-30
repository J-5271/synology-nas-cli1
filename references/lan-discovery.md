# 局域网发现：把 NAS 找出来（findhostd / mDNS / SSDP）

不知道 NAS 的 IP、不知道 DSM 端口是多少时，先做发现，再谈连接。
两条脚本互补，**实测单用哪一条都会漏设备**。

## 一、选哪条

| | `scripts/syno_findhost.py` | `scripts/discover_nas.py` |
|---|---|---|
| 协议 | findhostd（Synology Assistant 同款，私有） | mDNS + SSDP/UPnP（标准）+ HTTP 指纹 |
| 能拿到 | 型号、序列号、DSM 版本、build、架构、MAC、**自定义 HTTP/HTTPS 端口** | 主机名、 advertised 服务、SSDP server 串、HTTP title |
| 拿不到 | 关了 findhostd / 跨网段 / 未装 DSM 的裸机 | 序列号、DSM build、自定义端口 |
| 行为 | 广播查询 + 监听（不发任何改配置的命令） | 默认纯组播/广播；端口探测**默认关闭** |
| 典型漏网 | 未装 DSM 的机器（如刚重置的 DS220+） | 把 DSM 端口改成 888/889 的设备（端口扫描完全看不到） |

**结论：两条都跑。** 实测一台把端口改成 888/889 的 DS3018xs，端口扫描全表没命中，
findhostd 一次就报出来了；反过来一台没装 DSM 的 DS220+ 只回应 SSDP，findhostd 不理它。

## 二、findhostd 协议规格（逆向自官方 Assistant 抓包）

- 传输：UDP **9997 / 9998 / 9999**，广播查询（也可单播到已知 IP）
- 报文：`MAGIC(8B)` + N 个 `TLV(type:1, len:1, value:len)`
  - `MAGIC = 12 34 56 78 53 59 4E 4F`
  - 查询 `TLV(0x01, 4, cmd=1)`；应答 `cmd=2`
- 查询包完整构造（与 Qt5 版 `DSAssistant.exe` 抓包一致，源码 `CFindHostUDP.cpp`）：

  ```
  MAGIC
  TLV(0xA4, 4, 00 00 02 01)
  TLV(0xA6, 4, i32(120))
  TLV(0x01, 4, i32(1))          # command = 1 (search)
  TLV(0xB0, 8, u64(0x1C0))      TLV(0xB1, 8, u64(0))
  TLV(0xB8, 8, u64(0x1C0))      TLV(0xB9, 8, u64(0))
  TLV(0x7C, "00:11:32:00:00:00") × 4
  ```
  最小包 `MAGIC + TLV(0x01,4,1)` 也能触发应答（`--minimal`）。

- 应答字段（常用）：

  | type | 含义 | type | 含义 |
  |---|---|---|---|
  | 0x11 | 设备名 | 0x12 | IP |
  | 0x13 | 掩码 | 0x1e | 网关 |
  | 0x14 | DNS | 0x19 | MAC |
  | 0x49 | DSM build | 0x70 | 架构（如 `geminilake_220+`） |
  | 0x73 | 短序列号 | 0xc0 | 完整序列号 |
  | 0x75 | HTTP 端口 | 0x76 | HTTPS 端口 |
  | 0x77 | 版本（如 `7.3`） | 0x78 | 型号（如 `DS220+`） |
  | 0xc1 | 类别 `DSM` / `SRM` | | |

### ⚠️ 头号坑：套接字必须 bind 在 UDP 9999

NAS 的应答是发往**查询方 IP 的 9999 端口**，不是查询包的临时源端口。
用临时端口发，**包括单播到已知 NAS IP 在内，100% 收不到回应**。

```python
sock.bind(("", 9999))     # 必须，改了就收不到
sock.sendto(pkt, ("<广播地址>", 9999))
```

判定依据：本机官方 Assistant 也 bind `0.0.0.0:9999`（`netstat -ano -p UDP` 可见）。
**本机正在运行 Synology Assistant 时 9999 被它占住**，先退出该程序再跑脚本。

### 用法

```bash
python3 scripts/syno_findhost.py                    # 广播 + 监听，默认 8s
python3 scripts/syno_findhost.py -t 15              # 局域网设备多时放宽超时
python3 scripts/syno_findhost.py --bcast <广播地址>  # 手动指定，可重复
python3 scripts/syno_findhost.py --json             # JSON 输出，便于程序消费
```

排查无回应：同广播域？ / DSM 是否停用 findhostd？ / 本机防火墙拦了 UDP 9997-9999 出向？ /
本机 Assistant 占着 9999？ / 设备还没装 DSM（裸机不回应 findhostd）？

## 三、`discover_nas.py`（mDNS + SSDP + HTTP 指纹）

```bash
python3 scripts/discover_nas.py                        # 只走组播/广播 + HTTP 指纹
python3 scripts/discover_nas.py --subnet <网段>/24     # 手动指定网段（可重复）
python3 scripts/discover_nas.py --portscan             # 额外做 TCP 端口探测（主动扫描）
python3 scripts/discover_nas.py --json
```

- **端口探测默认关闭**，必须显式 `--portscan`。理由同安全红线「不主动做端口扫描」——
  只有用户明确要求清点暴露面时才开。
- 不做端口探测时不需要网段，也不枚举主机，纯听组播；开了 `--portscan` 才需要
  （默认取本机 `/24`，前缀短于 /20 直接拒绝）。
- HTTP 指纹是最终确认手段：title / server / location 里命中
  `synology|dsm|diskstation|rackstation` 才算「确认」。
  DSM 桌面页 title 形如 `<设备名> - Synology NAS`。

### 实测过的两个坑

- mDNS 查询构造：`services` 列表里已有 `bytes`，别再 `.encode()`
  （会 `AttributeError: 'bytes' object has no attribute 'encode'`）。
- SSDP 的 `SERVER` 头是识别 Synology 最快的通道，比 TCP 扫描准 ——
  DSM 改了网页端口后 5000/5001 照样探不到，但 SSDP 串还在。

## 四、退出码

| 码 | 含义 |
|---|---|
| 0 | 有发现 |
| 1 | 用法错误 / bind 失败 / 无法确定网段 |
| 3 | 什么都没发现 |

## 五、脱敏提醒（强制）

发现脚本的**运行输出包含真实 IP、MAC、序列号**。这些是运行时打印，不入库；
但一旦要贴进技能包 / 提交到公开仓库 / 填收集表，必须替换成占位符
（`<NAS_IP>`、`<MAC>`、`<序列号>`），规则同 SKILL.md「脱敏规范」。

## 六、维护记录

- 2026-09-30：新增。findhostd 协议逆向完成并在本机网段实测（4 台设备：
  DS220+ / DS918+ / DS3018xs / RT2600ac），两个脚本一并入库。
