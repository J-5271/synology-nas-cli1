#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""局域网 NAS 发现器（纯标准库，多通道）

默认只走「被动/广播」通道，不做任何主机扫描：
  1) mDNS 服务枚举（224.0.0.251:5353，组播 PTR 查询）
  2) SSDP/UPnP M-SEARCH（239.255.255.250:1900，组播）
  3) HTTP(S) 指纹确认（只对上面两步命中的候选主机，取 title/server 头）
可选（**默认关闭**）：4) TCP 端口连通性探测 —— 会逐主机 connect，
  属于主动扫描，必须显式加 `--portscan`。

⚠️ 与 `syno_findhost.py` 的关系：
  - 想拿型号/序列号/DSM build/自定义 HTTP 端口 → 用 findhostd（本脚本拿不到这些）
  - 想找「改了协议/关了 findhostd/跨网段」的设备 → 用本脚本
  两者互补，实测 findhostd 能发现端口扫描完全漏掉的设备（自定义端口 888/889 之类）。

用法:
  python3 scripts/discover_nas.py                       # mDNS + SSDP + HTTP 指纹
  python3 scripts/discover_nas.py --subnet <网段>/24    # 手动指定网段（可重复）
  python3 scripts/discover_nas.py --portscan            # 额外做 TCP 端口探测（主动扫描）
  python3 scripts/discover_nas.py --json                # JSON 输出

退出码: 0 有结果 / 1 用法错误或无法确定网段 / 3 什么都没发现
"""
import argparse
import ipaddress
import json
import re
import socket
import ssl
import struct
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROBE_PORTS = [
    (5000, "DSM HTTP"), (5001, "DSM HTTPS"), (5005, "WebDAV HTTP"),
    (5006, "WebDAV HTTPS"), (6690, "Synology Drive"), (7000, "Audio/Photo"),
    (9997, "FindHost/UDP"), (9998, "FindHost/UDP"), (9999, "FindHost/UDP"),
    (22, "SSH"), (445, "SMB"), (139, "NetBIOS"), (873, "rsync"), (2049, "NFS"),
]
HTTP_PORTS = [5000, 5001, 80, 443, 8080]

MDNS_GROUP = "224.0.0.251"
MDNS_PORT = 5353
SSDP_GROUP = "239.255.255.250"
SSDP_PORT = 1900

NASHINT = re.compile(r"(?i)synology|dsm|diskstation|rackstation|virtual machine manager")


# ---------- 工具 ----------
def local_subnets():
    out = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        out.append(str(ipaddress.ip_network(s.getsockname()[0] + "/24", strict=False)))
        s.close()
    except Exception:
        pass
    if not out:
        try:
            host = socket.gethostbyname(socket.gethostname())
            out.append(str(ipaddress.ip_network(host + "/24", strict=False)))
        except Exception:
            pass
    return out


def dns_name(b, off):
    """解析 DNS 名字（含压缩指针）"""
    parts, jumped, seen = [], False, 0
    while True:
        if off >= len(b):
            return "", off
        l = b[off]
        if l == 0:
            off += 1
            break
        if l & 0xC0 == 0xC0:
            ptr = struct.unpack("!H", b[off:off + 2])[0] & 0x3FFF
            off += 2
            if ptr >= len(b):
                break
            sub, _ = dns_name(b, ptr)
            parts.append(sub)
            jumped = True
            break
        off += 1
        parts.append(b[off:off + l].decode("utf-8", "replace"))
        off += l
        seen += 1
        if seen > 32:
            break
    return (".".join(parts), off) if not jumped else (parts[-1], off)


def build_query(names, qtype):
    pkt = struct.pack("!HHHHHH", 0, 0, 1, 0, 0, 0)
    for n in names:
        raw = n.encode() if isinstance(n, str) else n   # 别对 bytes 再 encode
        for lbl in raw.split(b"."):
            pkt += bytes([len(lbl)]) + lbl
        pkt += b"\x00" + struct.pack("!HH", qtype, 1)
    return pkt


def parse_rr(b, off):
    name, off = dns_name(b, off)
    if off + 10 > len(b):
        return None
    qtype, _cls, ttl, rdlen = struct.unpack("!HHIH", b[off:off + 10])
    off += 10
    return dict(name=name, type=qtype, ttl=ttl, data=b[off:off + rdlen], next_off=off + rdlen)


# ---------- 通道 1: mDNS ----------
def mdns_scan(timeout=4.0):
    services = [
        b"_services._dns-sd._udp.local",
        b"_dsm._tcp.local",
        b"_smb._tcp.local",
        b"_afpovertcp._tcp.local",
        b"_http._tcp.local",
        b"_synology._tcp.local",
    ]
    pkt = build_query(services, 12)  # PTR
    found = {}
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        try:
            s.bind(("", MDNS_PORT))
        except OSError:
            s.bind(("", 0))
        try:
            s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                         socket.inet_aton(MDNS_GROUP) + socket.inet_aton("0.0.0.0"))
        except OSError:
            pass
        s.settimeout(0.6)
        try:
            s.sendto(pkt, (MDNS_GROUP, MDNS_PORT))
        except OSError as e:
            print("  [mDNS] 发送失败: %s" % e)
        end = time.time() + timeout
        while time.time() < end:
            try:
                data, addr = s.recvfrom(9000)
            except socket.timeout:
                continue
            except OSError:
                break
            rec = found.setdefault(addr[0], {"svc": set(), "hostname": "", "txt": ""})
            try:
                _tid, flags, qd, an, ns, ar = struct.unpack("!HHHHHH", data[:12])
                if not flags & 0x8000:
                    continue
                off, n = 12, qd + an + ns + ar
                for i in range(n):
                    if i < qd:
                        _, off = dns_name(data, off)
                        off += 4
                        continue
                    r = parse_rr(data, off)
                    if r is None:
                        break
                    off = r["next_off"]
                    if r["type"] == 12:                     # PTR
                        ptr, _ = dns_name(r["data"], 0)
                        rec["svc"].add(ptr)
                    elif r["type"] == 33 and len(r["data"]) >= 6:   # SRV
                        _, off2 = dns_name(r["data"], 6)
                        tgt, _ = dns_name(r["data"], off2)
                        rec["hostname"] = rec["hostname"] or tgt.rstrip(".")
                    elif r["type"] == 16:                   # TXT
                        txt, p = [], 0
                        while p + 1 <= len(r["data"]):
                            l = r["data"][p]
                            p += 1
                            if not l:
                                break
                            txt.append(r["data"][p:p + l].decode("utf-8", "replace"))
                            p += l
                        rec["txt"] = (rec["txt"] + " | " if rec["txt"] else "") + ",".join(txt)
            except Exception:
                continue
        s.close()
    except Exception as e:
        print("  [mDNS] 不可用: %s" % e)
    return found


# ---------- 通道 2: SSDP ----------
def ssdp_scan(timeout=3.0):
    sts = ["ssdp:all", "upnp:rootdevice",
           "urn:schemas-upnp-org:device:InternetGatewayDevice:1"]
    res = {}
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.settimeout(0.6)
    except Exception as e:
        print("  [SSDP] 不可用: %s" % e)
        return res
    for st in sts:
        msg = ("M-SEARCH * HTTP/1.1\r\nHOST: %s:%d\r\nMAN: \"ssdp:discover\"\r\n"
               "MX: 2\r\nST: %s\r\nUSER-AGENT: nas-discover/1.0\r\n\r\n"
               % (SSDP_GROUP, SSDP_PORT, st))
        try:
            s.sendto(msg.encode(), (SSDP_GROUP, SSDP_PORT))
        except OSError:
            pass
    end = time.time() + timeout
    while time.time() < end:
        try:
            data, addr = s.recvfrom(4096)
        except socket.timeout:
            continue
        except OSError:
            break
        txt = data.decode("utf-8", "replace")
        info = res.setdefault(addr[0], {"server": "", "st": set(), "loc": ""})
        for key, pat in (("server", r"(?i)^SERVER:\s*(.+)$"),
                         ("loc", r"(?i)^LOCATION:\s*(.+)$")):
            m = re.search(pat, txt, re.M)
            if m:
                info[key] = m.group(1).strip()
        m = re.search(r"(?i)^ST:\s*(.+)$", txt, re.M)
        if m:
            info["st"].add(m.group(1).strip())
    s.close()
    return res


# ---------- 通道 4: TCP 端口探测（默认关闭）----------
def tcp_probe(job):
    ip, port, timeout = job
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        return (ip, port, s.connect_ex((ip, port)) == 0)
    except OSError:
        return (ip, port, False)
    finally:
        s.close()


def port_scan(hosts, ports, timeout=0.45, workers=200):
    res = {str(h): [] for h in hosts}
    jobs = [(str(h), p, timeout) for h in hosts for p in ports]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for ip, port, ok in ex.map(tcp_probe, jobs):
            if ok:
                res[ip].append(port)
    return res


# ---------- 通道 3: HTTP 指纹 ----------
def http_probe(ip, port, scheme, timeout=2.0):
    url = "%s://%s:%d/" % (scheme, ip, port)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 nas-discover"})
        r = urlopen(req, timeout=timeout, context=ctx if scheme == "https" else None)
        body = r.read(65536).decode("utf-8", "replace")
        head = dict((k.lower(), v) for k, v in r.getheaders())
        title = ""
        m = re.search(r"(?is)<title[^>]*>(.*?)</title>", body)
        if m:
            title = re.sub(r"\s+", " ", m.group(1)).strip()[:120]
        return dict(url=url, code=r.status, server=head.get("server", ""),
                    title=title, loc=head.get("location", ""), ok=True)
    except HTTPError as e:
        return dict(url=url, code=e.code, server=str(e.headers.get("Server", "")),
                    title="", loc=str(e.headers.get("Location", "")), ok=True)
    except (URLError, OSError, Exception):
        return None


def main():
    ap = argparse.ArgumentParser(description="局域网 NAS 发现（默认只走广播/组播，只读）")
    ap.add_argument("--subnet", action="append", default=None,
                    help="网段，如 <网段>/24，可重复；仅 --portscan 时需要")
    ap.add_argument("--no-mdns", action="store_true")
    ap.add_argument("--no-ssdp", action="store_true")
    ap.add_argument("--portscan", action="store_true",
                    help="额外做 TCP 端口探测（主动扫描，默认关闭）")
    ap.add_argument("--timeout", type=float, default=0.45, help="单端口连接超时")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    quiet = a.json

    mdns, ssdp, openmap = {}, {}, {}
    steps = 3 if a.portscan else 2
    step = 0

    if not a.no_mdns:
        step += 1
        if not quiet:
            print("[%d/%d] mDNS 服务枚举 ..." % (step, steps))
        mdns = mdns_scan()
        if not quiet:
            if mdns:
                for ip, v in sorted(mdns.items()):
                    svc = ", ".join(sorted(v["svc"])[:8])
                    print("  %-15s %s%s" % (ip, svc[:110],
                                            ("  host=%s" % v["hostname"]) if v["hostname"] else ""))
            else:
                print("  无响应")

    if not a.no_ssdp:
        step += 1
        if not quiet:
            print("\n[%d/%d] SSDP/UPnP 发现 ..." % (step, steps))
        ssdp = ssdp_scan()
        if not quiet:
            if ssdp:
                for ip, v in sorted(ssdp.items()):
                    print("  %-15s server=%s st=%s"
                          % (ip, v["server"][:50], ",".join(sorted(v["st"]))[:70]))
            else:
                print("  无响应")

    if a.portscan:
        step += 1
        nets = a.subnet or local_subnets()
        if not nets:
            sys.stderr.write("无法确定本机网段，用 --subnet 指定\n")
            return 1
        hosts = []
        for n in nets:
            try:
                net = ipaddress.ip_network(n, strict=False)
            except ValueError as e:
                sys.stderr.write("网段无效 %s: %s\n" % (n, e))
                continue
            if net.prefixlen < 20:
                sys.stderr.write("网段 %s 过大（/%d），跳过\n" % (n, net.prefixlen))
                continue
            hosts += [str(h) for h in net.hosts()]
        try:
            hosts = sorted(set(hosts) - {socket.gethostbyname(socket.gethostname())})
        except Exception:
            hosts = sorted(set(hosts))
        if not quiet:
            print("\n[%d/%d] 扫描网段: %s（%d 主机 x %d 端口）..."
                  % (step, steps, ", ".join(nets), len(hosts), len(PROBE_PORTS)))
        openmap = port_scan(hosts, [p for p, _ in PROBE_PORTS], a.timeout)
        if not quiet:
            hits = [(ip, sorted(ps)) for ip, ps in openmap.items() if ps]
            if hits:
                for ip, ps in sorted(hits):
                    names = [n for p, n in PROBE_PORTS if p in ps][:6]
                    print("  %-15s open=%-45s %s" % (ip, str(ps)[:45], " ".join(names)))
            else:
                print("  未发现开放端口")

    candidates = sorted(set(openmap) | set(mdns) | set(ssdp))
    if not quiet:
        print("\n[%d/%d] HTTP(S) 指纹识别（%d 个候选）..." % (steps, steps, len(candidates)))

    confirmed, detail, seen_any = [], [], False
    for ip in candidates:
        ps = set(openmap.get(ip, []))
        ports = sorted(ps & set(HTTP_PORTS)) or ([5000, 5001] if not ps else [])
        for p in ports:
            for scheme in (["https", "http"] if p in (443, 5001, 5006) else ["http", "https"]):
                r = http_probe(ip, p, scheme)
                if not r:
                    continue
                seen_any = True
                syno = bool(NASHINT.search(r["title"] + r["server"] + r["loc"]))
                if syno and ip not in confirmed:
                    confirmed.append(ip)
                r.update(ip=ip, synology=syno)
                detail.append(r)
                if not quiet:
                    print("  %-15s %-30s code=%s server=%-22s title=%s %s"
                          % (ip, r["url"], r["code"], r["server"][:22],
                             r["title"][:50], "*** SYNOLOGY ***" if syno else ""))
                break
            else:
                continue
            break
    if not quiet and not seen_any:
        print("  没有任何 HTTP 响应")

    if a.json:
        out = {
            "confirmed": confirmed,
            "candidates": [
                {
                    "ip": ip,
                    "open_ports": sorted(set(openmap.get(ip, []))) or None,
                    "mdns_hostname": mdns.get(ip, {}).get("hostname") or None,
                    "mdns_services": sorted(mdns.get(ip, {}).get("svc", [])) or None,
                    "ssdp_server": ssdp.get(ip, {}).get("server") or None,
                }
                for ip in candidates
            ],
            "http": detail,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if confirmed else 3

    print("\n" + "=" * 72)
    if confirmed:
        print("确认的 Synology NAS:")
        for ip in confirmed:
            ps = sorted(set(openmap.get(ip, [])))
            print("  %s   端口: %s" % (ip, ps or "（未做端口探测）"))
            if ip in mdns:
                print("      hostname=%s  mDNS服务=%s"
                      % (mdns[ip]["hostname"], ", ".join(sorted(mdns[ip]["svc"])[:10])))
            if ip in ssdp:
                print("      SSDP server=%s" % ssdp[ip]["server"])
    else:
        print("未确认 Synology NAS。候选（有广播响应但 HTTP 指纹未命中）:")
        for ip in candidates:
            tag = []
            if ip in mdns:
                tag.append("mDNS:" + ",".join(sorted(mdns[ip]["svc"])[:5]))
            if ip in ssdp:
                tag.append("SSDP:" + ssdp[ip]["server"][:30])
            ps = sorted(set(openmap.get(ip, [])))
            if ps:
                tag.append("ports:" + str(ps))
            if tag:
                print("  %-15s %s" % (ip, " | ".join(tag)))
        if not any([mdns, ssdp, openmap]):
            print("  （无）")
    print("=" * 72)
    return 0 if confirmed else 3


if __name__ == "__main__":
    sys.exit(main())
