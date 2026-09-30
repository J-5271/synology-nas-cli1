#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Synology Assistant 同款局域网发现客户端（findhostd 协议）

协议逆向自官方 Synology Assistant 抓包（与 Qt5 版 DSAssistant.exe 完全一致）:
  UDP 9997/9998/9999，广播查询 -> NAS 单播/广播回应
  报文 = MAGIC(8B) + N 个 TLV(type:1, len:1, value:len)
  MAGIC = 12 34 56 78 53 59 4E 4F
  查询包: TLV(0x01,4,cmd=1) + TLV(0xa4,4,0x01020000) + TLV(0xa6,4,120) + ...
  回应包: TLV(0x01,4,cmd=2) + 型号/序列号/DSM版本/IP/MAC/HTTP端口 等

只读：仅发送标准查询包（cmd=1）。不发送任何会改变设备配置的命令
（cmd=0x02/0x05/0x06/0x09/0x0d 一律不涉），不改设备任何状态。

用法:
  python3 scripts/syno_findhost.py                  # 广播 + 监听，默认 8s
  python3 scripts/syno_findhost.py -t 5             # 超时 5s
  python3 scripts/syno_findhost.py --bcast <广播地址> # 手动指定广播地址，可重复
  python3 scripts/syno_findhost.py --minimal        # 只发最小查询包
  python3 scripts/syno_findhost.py --json           # JSON 输出，便于程序消费

⚠️ 最关键的实测结论：必须把套接字 bind 在 UDP 9999 上再发查询。
NAS 的应答是发往「查询方 IP 的 9999 端口」，不是查询包的临时源端口；
绑临时端口时 100% 收不到回应（官方 Assistant 也是 bind 0.0.0.0:9999）。
本机若正在运行 Synology Assistant，9999 会被它占住，先退出该程序再跑。

退出码: 0 有发现 / 3 无回应 / 1 用法或绑定失败
"""
import argparse
import json
import socket
import struct
import sys
import time

MAGIC = b"\x12\x34\x56\x78\x53\x59\x4e\x4f"
PORTS = [9999, 9998, 9997]

# 回应包字段 -> (显示名, 解析方式)
FIELDS = {
    0x01: ("command", "i"),
    0x10: ("flags", "i"),
    0x11: ("server_name", "s"),
    0x12: ("ip", "ip"),
    0x13: ("netmask", "ip"),
    0x14: ("dns1", "ip"),
    0x15: ("dns2", "ip"),
    0x18: ("field18", "i"),
    0x19: ("mac", "s"),
    0x1e: ("gateway", "ip"),
    0x20: ("subtype", "i"),
    0x21: ("server_name2", "s"),
    0x29: ("mac2", "s"),
    0x48: ("field48", "i"),
    0x49: ("dsm_build", "i"),
    0x70: ("arch", "s"),
    0x71: ("field71", "i"),
    0x73: ("serial_short", "s"),
    0x75: ("http_port", "i"),
    0x76: ("https_port", "i"),
    0x77: ("version", "s"),
    0x78: ("model", "s"),
    0x7b: ("field7b", "i"),
    0x7c: ("mac3", "s"),
    0x80: ("field80", "i"),
    0x90: ("field90", "i"),
    0xa0: ("fielda0", "i"),
    0xa3: ("fielda3", "i"),
    0xa4: ("proto", "hex"),
    0xa6: ("fielda6", "i"),
    0xa7: ("fielda7", "i"),
    0xc0: ("serial", "s"),
    0xc1: ("category", "s"),
}

SHOW_KEYS = ["server_name", "model", "category", "version", "dsm_build", "serial",
             "serial_short", "ip", "netmask", "gateway", "dns1", "mac",
             "http_port", "https_port", "proto", "flags"]


def tlv(t, v):
    assert len(v) <= 255
    return bytes([t, len(v)]) + v


def i32(v):
    return struct.pack("<I", v & 0xFFFFFFFF)


def build_query(minimal=False):
    """构造标准查询包（与官方 Assistant 抓包一致）"""
    p = MAGIC
    if minimal:
        return p + tlv(0x01, i32(1))
    p += tlv(0xA4, bytes([0x00, 0x00, 0x02, 0x01]))
    p += tlv(0xA6, i32(120))
    p += tlv(0x01, i32(1))                    # command = 1 (search)
    p += tlv(0xB0, struct.pack("<Q", 0x1C0))
    p += tlv(0xB1, struct.pack("<Q", 0))
    p += tlv(0xB8, struct.pack("<Q", 0x1C0))
    p += tlv(0xB9, struct.pack("<Q", 0))
    for _ in range(4):
        p += tlv(0x7C, b"00:11:32:00:00:00")
    return p


def parse(data):
    """解析 MAGIC + TLV"""
    if len(data) < 8 or data[:8] != MAGIC:
        return None
    out, off, n = {}, 8, 0
    while off + 2 <= len(data):
        t = data[off]
        l = data[off + 1]
        v = data[off + 2:off + 2 + l]
        off += 2 + l
        n += 1
        name, kind = FIELDS.get(t, ("t%02x" % t, "raw"))
        try:
            if kind == "i":
                val = int.from_bytes(v, "little")
            elif kind == "ip":
                val = ".".join(map(str, v)) if len(v) == 4 else v.hex()
            elif kind == "s":
                val = v.rstrip(b"\x00").decode("utf-8", "replace")
            elif kind == "hex":
                val = "0x%08x" % int.from_bytes(v, "little")
            else:
                val = v.hex()
        except Exception:
            val = repr(v)
        # 同名 TLV 出现多次只保留第一个非空值
        if name not in out or (not out[name] and val):
            out[name] = val
        if n > 400:
            break
    return out


def local_info():
    """取本机 IP（用于算广播地址 + 过滤自身回显）"""
    res = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        res.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            a = info[4][0]
            if a not in res and not a.startswith("127."):
                res.append(a)
    except Exception:
        pass
    return res


def main():
    ap = argparse.ArgumentParser(description="Synology findhostd 局域网发现（只读）")
    ap.add_argument("-t", "--timeout", type=float, default=8.0)
    ap.add_argument("--bcast", action="append", default=None, help="广播地址，可重复")
    ap.add_argument("--source-port", type=int, default=9999,
                    help="默认 9999，必须；改了收不到回应")
    ap.add_argument("--no-retry", action="store_true", help="只发一轮，不重复")
    ap.add_argument("--minimal", action="store_true", help="只发最小查询包")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    a = ap.parse_args()

    pkt = build_query(a.minimal)
    quiet = a.json

    targets = list(a.bcast or [])
    if not targets:
        targets = ["255.255.255.255"]
        for ip in local_info():
            b = ".".join(ip.split(".")[:3]) + ".255"
            if b not in targets:
                targets.append(b)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("", a.source_port))
    except OSError as e:
        sys.stderr.write("bind 失败: %s\n" % e)
        return 1
    own = set(local_info())

    if not quiet:
        print("查询包 (%d 字节): %s..." % (len(pkt), pkt[:32].hex(" ")))
        print("广播目标: %s   端口: %s" % (", ".join(targets), PORTS))
        print("监听源端口: %d   (本机 IP: %s)\n" % (sock.getsockname()[1], ", ".join(own) or "?"))

    rounds = sent = 0
    devices = {}
    end = time.time() + a.timeout
    while time.time() < end:
        sent = 0
        for b in targets:
            for p in PORTS:
                try:
                    sock.sendto(pkt, (b, p))
                    sent += 1
                except OSError as e:
                    if not quiet:
                        print("  发送失败 %s:%d %s" % (b, p, e))
        rounds += 1
        deadline = min(time.time() + 1.5, end)
        sock.settimeout(0.3)
        while time.time() < deadline:
            try:
                data, addr = sock.recvfrom(8192)
            except socket.timeout:
                continue
            except OSError:
                break
            info = parse(data)
            if not info:
                continue
            ip = addr[0]
            if ip in own:
                continue                        # 自身广播回显
            if info.get("command") not in (2, None):
                continue                        # 只收 cmd=2 的应答
            prev = devices.get(ip)
            if prev is None or len(info) > len(prev):
                devices[ip] = info
        if a.no_retry:
            break
    sock.close()

    ordered = sorted(devices, key=lambda s: [int(x) for x in s.split(".")])

    if a.json:
        print(json.dumps({
            "count": len(devices),
            "rounds": rounds,
            "packets_per_round": sent,
            "devices": [dict(devices[ip], source_ip=ip) for ip in ordered],
        }, ensure_ascii=False, indent=2))
        return 0 if devices else 3

    print("（已发 %d 轮 x %d 包）" % (rounds, sent))
    print("\n" + "=" * 78)
    if not devices:
        print("未收到任何 findhostd 回应（已发 %d 个广播包）" % sent)
        print("排查: 同广播域? / DSM 是否停用了 findhostd? / 本机防火墙是否拦了 UDP 9997-9999 出向?")
        print("      / 本机 Synology Assistant 是否占着 UDP 9999（先退出它）?")
        return 3
    print("发现 %d 台设备（Synology Assistant 同款协议）:\n" % len(devices))
    for ip in ordered:
        d = devices[ip]
        print("● %s   (回应 cmd=%s, 字段数 %d)" % (ip, d.get("command", "?"), len(d)))
        for k in SHOW_KEYS:
            if k in d and d[k] not in ("", None):
                print("    %-13s %s" % (k, d[k]))
        extra = [k for k in d if k.startswith("t") or k.startswith("field")]
        if extra:
            print("    其它字段    %s" % ", ".join("%s=%s" % (k, d[k]) for k in sorted(extra)))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
