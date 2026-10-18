#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
采样 Synology NAS 各网卡的真实收发速率（每秒一行），用于**判定性能瓶颈在哪一侧**。

为什么需要它：
  只看客户端报出来的吞吐是判不出瓶颈的。本脚本直接读 NAS 上的 `/proc/net/dev`，
  在负载正在跑的时候连续采样，就能回答「NAS 到底往网络里发了多少」：
    * NAS TX ≈ 客户端收到的  -> 客户端没问题，瓶颈在 NAS 或后端存储
    * NAS TX 明显高于客户端   -> 客户端消费不动（CPU / 单连接往返 / rsize 太小）
  详见 references/perf-and-network.md 第一节。

判读要点：
  * TX 大 = 读（NAS -> 客户端）；RX 大 = 写（客户端 -> NAS）。别搞反。
  * 采样窗口必须**完整覆盖**负载段，否则尾部空转会拉低均值。
  * 一定要把 NAS 上的**所有网卡**都列进去，只盯一张会漏掉「流量其实走了另一张卡」。

实现：SSH 登录后反复 `cat /proc/net/dev` 取累计字节数做差，不需要 sudo、不需要改配置（只读）。

凭据走环境变量：
  NAS_HOST / NAS_USER / NAS_PASS   （NAS_PORT 可选，默认 22）
  密码登录需要 paramiko：pip install paramiko

用法：
  export NAS_HOST=<NAS_IP> NAS_USER=<管理员账号> NAS_PASS='<密码>'
  python3 nas_nic_sample.py --seconds 15
  python3 nas_nic_sample.py --ifaces eth0,eth2 --seconds 20
  python3 nas_nic_sample.py --ssh-port 2222 --seconds 10     # SSH 端口非 22

退出码：0 成功 / 1 出错 / 2 用法错误
"""
import argparse
import os
import sys
import time

try:
    import paramiko
except ImportError:
    sys.exit("[ERROR] 需要 paramiko：pip install paramiko（本脚本只走 SSH 密码登录）")


def read_counters(ssh, ifaces):
    """返回 {iface: (rx_bytes, tx_bytes)}，只取关心的网卡。"""
    _i, out, _e = ssh.exec_command("cat /proc/net/dev", timeout=20)
    text = out.read().decode("utf-8", "replace")
    res = {}
    for line in text.splitlines()[2:]:
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        name = name.strip()
        if name not in ifaces:
            continue
        f = rest.split()
        res[name] = (int(f[0]), int(f[8]))      # rx_bytes, tx_bytes
    return res


def detect_ifaces(ssh):
    """没指定时，自动挑出有 IPv4 地址的物理网卡。"""
    _i, out, _e = ssh.exec_command("ip -brief addr show", timeout=20)
    names = []
    for line in out.read().decode("utf-8", "replace").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "UP" and parts[0] != "lo":
            names.append(parts[0])
    return names


def main():
    ap = argparse.ArgumentParser(description="采样 NAS 网卡速率（只读）")
    ap.add_argument("--host", default=os.environ.get("NAS_HOST", ""))
    ap.add_argument("--user", default=os.environ.get("NAS_USER", ""))
    ap.add_argument("--password", default=os.environ.get("NAS_PASS", ""))
    ap.add_argument("--ssh-port", type=int,
                    default=int(os.environ.get("NAS_PORT", "22")))
    ap.add_argument("--ifaces", default="",
                    help="逗号分隔；不填则自动探测已 UP 的网卡")
    ap.add_argument("--seconds", type=int, default=15)
    ap.add_argument("--version", "-V", action="store_true")
    args = ap.parse_args()

    if args.version:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        try:
            from dsm_api import skill_version
            print(f"synology-nas-cli v{skill_version()}")
        except Exception:
            print("synology-nas-cli")
        return 0
    if not (args.host and args.user and args.password):
        ap.error("必须给 --host/--user/--password，或设 NAS_HOST / NAS_USER / NAS_PASS")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(args.host, port=args.ssh_port, username=args.user,
                    password=args.password, timeout=20)
    except Exception as e:
        print(f"[ERROR] SSH 连接失败：{e}", file=sys.stderr)
        return 1

    try:
        if args.ifaces:
            ifaces = [x.strip() for x in args.ifaces.split(",") if x.strip()]
        else:
            ifaces = detect_ifaces(ssh)
            if not ifaces:
                print("[ERROR] 没能自动识别网卡，请用 --ifaces 指定", file=sys.stderr)
                return 1
            print(f"# 自动识别网卡：{', '.join(ifaces)}")

        prev = read_counters(ssh, ifaces)
        prev_t = time.time()
        print(f"# 采样 {args.seconds}s，单位 MiB/s（TX=NAS发出，RX=NAS收到）")
        print(f"# {'秒':>4} " + " ".join(f"{n + ' RX':>10} {n + ' TX':>10}"
                                          for n in ifaces))
        peak = {n: [0.0, 0.0] for n in ifaces}
        acc = {n: [[], []] for n in ifaces}
        for k in range(args.seconds):
            time.sleep(1.0)
            cur = read_counters(ssh, ifaces)
            now = time.time()
            dt = now - prev_t
            row = []
            for n in ifaces:
                rx = (cur[n][0] - prev[n][0]) / dt / 1048576.0
                tx = (cur[n][1] - prev[n][1]) / dt / 1048576.0
                acc[n][0].append(rx)
                acc[n][1].append(tx)
                peak[n][0] = max(peak[n][0], rx)
                peak[n][1] = max(peak[n][1], tx)
                row.append(f"{rx:>10.1f} {tx:>10.1f}")
            print(f"  {k + 1:>4} " + " ".join(row))
            prev, prev_t = cur, now
        print()
        for n in ifaces:
            rx, tx = acc[n]
            print(f"# {n}: RX 峰值={peak[n][0]:.1f} 均值={sum(rx) / max(len(rx), 1):.1f} "
                  f"MiB/s | TX 峰值={peak[n][1]:.1f} 均值={sum(tx) / max(len(tx), 1):.1f} MiB/s")
    finally:
        ssh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
