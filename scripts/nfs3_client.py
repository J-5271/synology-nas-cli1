#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
极简 NFSv3 客户端 + 性能基准（纯标准库 / 不需要管理员 / 不依赖系统 NFS 栈）。

为什么需要它：
  * Windows 默认不带 NFS 客户端（`mount.exe` / `nfsadmin.exe` / `nfsclnt.sys` 都没有），
    装它要管理员权限；权限受限的会话里根本装不上。
  * Linux 侧如果只想确认「NAS 的 NFS 导出是否正常」，装 nfs-common 也未必方便。
  * 这个脚本自己实现 ONC-RPC over TCP + XDR，只要能发一个 TCP 连接就能验证与压测。

能做的：
  verify         挂载与功能验证：EXPORT / MNT / GETATTR / READDIR / LOOKUP /
                 CREATE / WRITE / 回读校验 / REMOVE（全部走一遍，最后清理干净）
  rsize          探测服务端允许的单次 READ 最大字节数
  read[-sweep]   顺序读带宽（N 线程各占文件一段）
  write[-sweep]  顺序写带宽（N 线程各写一个新文件，跑完自动删）
  randread[-sweep] 随机读 IOPS（可指定 IO 大小）
  lat            空载与并发下的 RPC 往返延迟

实测过的坑（详见 references/nfs-service.md 第二节）：
  * RPC 头里含 proc，**不能缓存复用** —— 否则 MNT(1) 会被当 EXPORT(5) 发出去，
    服务端把导出列表首字段当状态码，客户端看到 "MNT 失败 status=1"，像是权限问题。
  * 单次 WRITE 超上限会被 nfsd **直接 RST**（不是返回错误码）；实测上限 1 MiB。
  * NFSv3 的 CREATE 返回 `post_op_fh3`，前面有一个布尔位，漏读会导致 BADHANDLE(10001)。
  * RPC over TCP 的记录标记可能多片段，要按最高位判断「最后一片」。

认证：AUTH_SYS（`--uid` / `--gid`）。默认 1026 / 100，对应 DSM 上 administrators 用户。
      凭据与地址只走命令行 / 环境变量（NAS_HOST），脚本不落盘。

用法：
  python3 nfs3_client.py verify --host <NAS_IP> --export /volume2/<共享名> --subdir <子目录>
  python3 nfs3_client.py read-sweep --host <NAS_IP> --export /volume2/<共享名> \\
      --subdir <目录> --file <大文件> --size-mib 8192 --sweep 1,4,8,16
  python3 nfs3_client.py write-sweep --host <NAS_IP> --export /volume2/<共享名> \\
      --subdir <目录> --size-mib 8192 --sweep 1,4,16
  python3 nfs3_client.py randread-sweep --host <NAS_IP> --export /volume2/<共享名> \\
      --subdir <目录> --file <大文件> --io-kib 32 --sweep 1,4,8,16 --count 2000
  python3 nfs3_client.py lat --host <NAS_IP> --export /volume2/<共享名> --subdir <目录>

退出码：0 成功 / 1 出错 / 2 用法错误
"""
import argparse
import os
import random
import socket
import struct
import sys
import threading
import time

PGM_PORTMAP = 100000
PGM_MOUNT = 100005
PGM_NFS = 100003
IPPROTO_TCP = 6

AUTH_NULL = 0
AUTH_SYS = 1

MOUNT_V3_EXPORT = 5
MOUNT_V3_MNT = 1

NFS3_GETATTR = 1
NFS3_LOOKUP = 3
NFS3_READ = 6
NFS3_WRITE = 7
NFS3_CREATE = 8
NFS3_REMOVE = 12
NFS3_READDIR = 16
NFS3_COMMIT = 21

UNCHECKED = 1
FILE_SYNC = 2
UNSTABLE = 0
SET_TO_SERVER_TIME = 0

FATTR_SIZE = 84
RECV = 1 << 20


# ---------------------------------------------------------------- XDR 编解码
def _pad4(n):
    return (-n) % 4


class W:
    __slots__ = ("b",)

    def __init__(self):
        self.b = bytearray()

    def u32(self, v):
        self.b += struct.pack(">I", v & 0xFFFFFFFF)
        return self

    def u64(self, v):
        self.b += struct.pack(">Q", v & 0xFFFFFFFFFFFFFFFF)
        return self

    def opa(self, data):
        self.u32(len(data))
        self.b += data
        self.b += b"\x00" * _pad4(len(data))
        return self

    def string(self, s):
        if isinstance(s, str):
            s = s.encode("utf-8")
        return self.opa(s)

    def boolean(self, v):
        return self.u32(1 if v else 0)

    def raw(self, data):
        self.b += data
        return self

    def out(self):
        return bytes(self.b)


class R:
    __slots__ = ("d", "o")

    def __init__(self, data):
        self.d = data
        self.o = 0

    def u32(self):
        v = struct.unpack_from(">I", self.d, self.o)[0]
        self.o += 4
        return v

    def u64(self):
        v = struct.unpack_from(">Q", self.d, self.o)[0]
        self.o += 8
        return v

    def opa(self):
        n = self.u32()
        v = self.d[self.o:self.o + n]
        self.o += n + _pad4(n)
        return v

    def string(self):
        return self.opa().decode("utf-8", "replace")

    def boolean(self):
        return bool(self.u32())

    def skip(self, n):
        self.o += n
        return self


# ------------------------------------------------------------------- RPC
class RpcError(Exception):
    pass


def _recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(min(n - len(buf), RECV))
        if not chunk:
            raise RpcError("连接被对端关闭")
        buf += chunk
    return buf


def _auth_sys(uid, gid, gids):
    w = W()
    w.u32(0)                  # stamp
    w.string("workbuddy")     # machinename
    w.u32(uid)
    w.u32(gid)
    w.u32(len(gids))
    for g in gids:
        w.u32(g)
    return w.out()


class Conn:
    """一条**持久** TCP 连接上的 ONC-RPC 通道。非线程安全 —— 每条线程自己 new 一个。

    ⚠️ 这里是本项目性能结论的关键之一：每次 RPC 都 socket.create_connection() 的实现，
    每读 1 MiB 就要付一次三次握手 + 慢启动，测出来的只是 RTT 的影子，不是 NAS 能力。
    """

    def __init__(self, host, port, uid=None, gid=None, gids=(0,), timeout=60):
        self.host = host
        self.port = port
        self.uid = uid
        self.gid = gid
        self.gids = tuple(gids)
        self.timeout = timeout
        self.sock = None
        if self.uid is None:
            self._cred = struct.pack(">II", AUTH_NULL, 0)
        else:
            body = _auth_sys(self.uid, self.gid, self.gids)
            self._cred = struct.pack(">II", AUTH_SYS, len(body)) + body

    def _ensure(self):
        if self.sock is None:
            s = socket.create_connection((self.host, self.port), timeout=self.timeout)
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 << 20)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 << 20)
            except OSError:
                pass
            self.sock = s
        return self.sock

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def _read_record(self):
        """按 RFC 5531 把多片段的记录拼回一条完整应答。"""
        parts = []
        while True:
            marker = struct.unpack(">I", _recv_exact(self.sock, 4))[0]
            last = marker & 0x80000000
            n = marker & 0x7FFFFFFF
            if n:
                parts.append(_recv_exact(self.sock, n))
            if last:
                break
        return parts[0] if len(parts) == 1 else b"".join(parts)

    def call(self, prog, vers, proc, args=b"", retries=2):
        last = None
        for _ in range(retries):
            try:
                return self._call_once(prog, vers, proc, args)
            except (socket.timeout, RpcError, OSError) as e:
                last = e
                self.close()
                time.sleep(0.3)
        raise last

    def _call_once(self, prog, vers, proc, args):
        self._ensure()
        xid = random.getrandbits(32)
        # 注意：proc 每次都重建，绝不能把带 proc 的头缓存复用（见文件头「实测过的坑」）
        head = (struct.pack(">IIIIII", xid, 0, 2, prog, vers, proc)
                + self._cred
                + struct.pack(">II", AUTH_NULL, 0))
        payload = head + args
        self.sock.sendall(struct.pack(">I", 0x80000000 | len(payload)) + payload)
        data = self._read_record()

        r = R(data)
        if r.u32() != xid:
            raise RpcError("xid 不匹配")
        if r.u32() != 1:
            raise RpcError("不是 REPLY 消息")
        if r.u32() != 0:
            raise RpcError("RPC 被拒绝")
        r.u32()                        # verifier flavor
        vl = r.u32()
        r.skip(vl + _pad4(vl))
        accept = r.u32()
        if accept != 0:
            raise RpcError(f"accept_stat={accept} (prog={prog} proc={proc})")
        return r


def rpc_oneshot(host, port, prog, vers, proc, args=b""):
    """无状态的一次性调用（只用于 PORTMAP 查端口）。"""
    c = Conn(host, port, timeout=20)
    try:
        return c.call(prog, vers, proc, args, retries=3)
    finally:
        c.close()


# ---------------------------------------------------------------- 属性
def _read_fattr(r):
    return {
        "type": r.u32(), "mode": r.u32(), "nlink": r.u32(),
        "uid": r.u32(), "gid": r.u32(),
        "size": r.u64(), "used": r.u64(),
        "rdev": (r.u32(), r.u32()), "fsid": r.u64(), "fileid": r.u64(),
        "atime": (r.u32(), r.u32()), "mtime": (r.u32(), r.u32()),
        "ctime": (r.u32(), r.u32()),
    }


def _read_post_op_attr(r):
    return _read_fattr(r) if r.boolean() else None


class Nfs3:
    """面向单个 export 的 NFSv3 客户端（内部持有长连接）。"""

    _ports = {}

    def __init__(self, host, uid=1026, gid=100, gids=(100, 101), timeout=60):
        self.host = host
        self.uid = uid
        self.gid = gid
        self.gids = tuple(gids)
        if host not in Nfs3._ports:
            Nfs3._ports[host] = (self._getport(PGM_MOUNT, 3),
                                 self._getport(PGM_NFS, 3))
        self.mount_port, self.nfs_port = Nfs3._ports[host]
        self.nfs = Conn(host, self.nfs_port, uid, gid, gids, timeout)
        self.mount = Conn(host, self.mount_port, uid, gid, gids, timeout)

    def _getport(self, prog, vers):
        w = W().u32(prog).u32(vers).u32(IPPROTO_TCP).u32(0)
        return rpc_oneshot(self.host, 111, PGM_PORTMAP, 2, 3, w.out()).u32()

    def close(self):
        self.nfs.close()
        self.mount.close()

    # ---- MOUNT
    def export(self):
        r = self.mount.call(PGM_MOUNT, 3, MOUNT_V3_EXPORT)
        out = []
        while r.boolean():
            path = r.string()
            groups = []
            while r.boolean():
                groups.append(r.string())
            out.append((path, groups))
        return out

    def mnt(self, path):
        r = self.mount.call(PGM_MOUNT, 3, MOUNT_V3_MNT, W().string(path).out())
        st = r.u32()
        if st != 0:
            raise RpcError(f"MNT 失败 status={st}"
                           "（1=PERM/请求错或不在导出规则里，2=NOENT/路径写错，"
                           "13=ACCES/路径被改写）")
        return r.opa()

    # ---- NFS
    def getattr(self, fh):
        r = self.nfs.call(PGM_NFS, 3, NFS3_GETATTR, W().opa(fh).out())
        st = r.u32()
        if st != 0:
            raise RpcError(f"GETATTR status={st}")
        return _read_fattr(r)

    def lookup(self, dirfh, name):
        r = self.nfs.call(PGM_NFS, 3, NFS3_LOOKUP, W().opa(dirfh).string(name).out())
        st = r.u32()
        if st != 0:
            return None, st
        fh = r.opa()
        attrs = _read_post_op_attr(r)
        _read_post_op_attr(r)
        return (fh, attrs), 0

    def readdir(self, fh):
        entries, cookie = [], 0
        while True:
            r = self.nfs.call(PGM_NFS, 3, NFS3_READDIR,
                              W().opa(fh).u64(cookie).raw(b"\x00" * 8).u32(32768).out())
            st = r.u32()
            if st != 0:
                raise RpcError(f"READDIR status={st}")
            _read_post_op_attr(r)
            r.skip(8)                     # cookieverf
            n = 0
            while r.boolean():
                entries.append({"fileid": r.u64(), "name": r.string(),
                                "cookie": r.u64()})
                n += 1
            if r.boolean() or n == 0:     # eof
                break
            if entries:
                cookie = entries[-1]["cookie"]
        return entries

    def read(self, fh, offset, count):
        r = self.nfs.call(PGM_NFS, 3, NFS3_READ,
                          W().opa(fh).u64(offset).u32(count).out())
        st = r.u32()
        if st != 0:
            raise RpcError(f"READ status={st}")
        _read_post_op_attr(r)
        r.u32()                           # 回包里的 count 是声明长度，真实长度看 opa
        r.boolean()                       # eof
        return r.opa()

    def create(self, dirfh, name):
        w = W().opa(dirfh).string(name)
        w.u32(UNCHECKED)
        w.boolean(False)                  # 不显式设 mode
        w.boolean(True).u32(self.uid)
        w.boolean(True).u32(self.gid)
        w.boolean(False)                  # 不设 size
        w.u32(SET_TO_SERVER_TIME)
        w.u32(SET_TO_SERVER_TIME)
        r = self.nfs.call(PGM_NFS, 3, NFS3_CREATE, w.out())
        st = r.u32()
        if st != 0:
            raise RpcError(f"CREATE status={st}")
        # CREATE3resok: obj = post_op_fh3 = 布尔「是否跟随」+ filehandle
        if not r.boolean():
            raise RpcError("CREATE 未返回 filehandle")
        return r.opa()

    def write(self, fh, offset, data, sync=FILE_SYNC):
        w = W().opa(fh).u64(offset).u32(len(data)).u32(sync).opa(data)
        r = self.nfs.call(PGM_NFS, 3, NFS3_WRITE, w.out())
        st = r.u32()
        if st != 0:
            raise RpcError(f"WRITE status={st}")
        if r.boolean():                   # wcc_data.before
            r.skip(24)
        _read_post_op_attr(r)
        n = r.u32()
        committed = r.u32()
        return n, committed

    def commit(self, fh, offset=0, count=0):
        r = self.nfs.call(PGM_NFS, 3, NFS3_COMMIT,
                          W().opa(fh).u64(offset).u32(count).out())
        st = r.u32()
        if st != 0:
            raise RpcError(f"COMMIT status={st}")
        if r.boolean():
            r.skip(24)
        return r.u64()                    # verifier

    def remove(self, dirfh, name):
        r = self.nfs.call(PGM_NFS, 3, NFS3_REMOVE, W().opa(dirfh).string(name).out())
        return r.u32()


# ---------------------------------------------------------------- 工具
def human(bps):
    return f"{bps / 1048576:.1f} MiB/s"


def pct(sorted_vals, p):
    if not sorted_vals:
        return 0.0
    k = min(len(sorted_vals) - 1,
            max(0, int(round(p / 100.0 * len(sorted_vals) + 0.5)) - 1))
    return sorted_vals[k]


def resolve_dir(cli, root_fh, subdir):
    if not subdir or subdir == ".":
        return root_fh
    cur = root_fh
    for part in subdir.strip("/").split("/"):
        res, st = cli.lookup(cur, part)
        if not res:
            raise RpcError(f"LOOKUP {part} status={st}")
        cur = res[0]
    return cur


def probe_rsize(cli, fh, file_size):
    """探出服务端允许的单次 READ 字节数（实测多数 DSM 为 1 MiB）。"""
    for want in (8 << 20, 4 << 20, 2 << 20, 1 << 20,
                 512 << 10, 256 << 10, 128 << 10, 64 << 10):
        if want > file_size:
            continue
        try:
            d = cli.read(fh, 0, want)
        except RpcError:
            continue
        if d:
            return len(d)
    return 64 << 10


# ---------------------------------------------------------------- 子命令
def cmd_verify(cli, args):
    print(f"# NFS 挂载验证  host={args.host}  export={args.export}")
    print(f"# AUTH_SYS uid={args.uid} gid={args.gid} gids=[100,101]")
    print()
    print(f"[1] PORTMAP          mountd={cli.mount_port}  nfsd={cli.nfs_port}")

    print("[2] MOUNT/EXPORT")
    exp = cli.export()
    for path, _g in exp:
        print(f"      {path}{'  <== 目标' if path == args.export else ''}")
    if args.export not in [p for p, _ in exp]:
        print("      !! 目标 export 不在导出列表里")

    print(f"[3] MOUNT/MNT {args.export}")
    fh = cli.mnt(args.export)
    a = cli.getattr(fh)
    print(f"      OK  fh={len(fh)}B  uid={a['uid']} gid={a['gid']} "
          f"mode={oct(a['mode'] & 0o7777)}  size={a['size']}")

    print(f"[4] READDIR {args.export}")
    try:
        for e in cli.readdir(fh):
            print(f"      {e['name']}")
    except RpcError as e:
        print(f"      !! {e}（权限 711 时非属主列不出目录）")

    print(f"[5] LOOKUP {args.subdir}")
    dfh = resolve_dir(cli, fh, args.subdir)
    a = cli.getattr(dfh)
    print(f"      OK  uid={a['uid']} gid={a['gid']} mode={oct(a['mode'] & 0o7777)}")
    for e in cli.readdir(dfh):
        print(f"        {e['name']}")

    p, st = cli.lookup(dfh, "__wb_probe.txt")
    if p:
        print(f"[6] READ __wb_probe.txt : {cli.read(p[0], 0, 4096)!r}")
    else:
        print(f"[6] __wb_probe.txt 不存在 (status={st})")

    # 写 + 回读校验 + 清理（单次 WRITE 不要超 1 MiB，见文件头）
    name = f"__wb_nfs_verify_{os.getpid()}.bin"
    cli.remove(dfh, name)
    tfh = cli.create(dfh, name)
    payload = os.urandom(1 << 20)
    t0 = time.time()
    tot = 0
    for i in range(4):
        n, _c = cli.write(tfh, i * len(payload), payload)
        tot += n
    dt = time.time() - t0
    size = cli.getattr(tfh)["size"]
    ok = cli.read(tfh, 0, len(payload)) == payload
    st_rm = cli.remove(dfh, name)
    print(f"[7] WRITE 4 MiB         : {tot} B / {dt:.2f}s = {human(tot / max(dt, 1e-9))}"
          f"  服务端 size={size}")
    print(f"      回读校验           : {'一致 OK' if ok else '不一致 FAIL'}")
    print(f"      REMOVE             : {'OK' if st_rm == 0 else 'status=' + str(st_rm)}")
    return 0


def cmd_rsize(cli, args):
    root = cli.mnt(args.export)
    dfh = resolve_dir(cli, root, args.subdir)
    res, st = cli.lookup(dfh, args.file)
    if not res:
        print(f"LOOKUP {args.file} 失败 status={st}")
        return 1
    fh, attrs = res
    print(f"探测结果 rsize = {probe_rsize(cli, fh, attrs['size'])} 字节")
    return 0


def _sweep(args):
    return [int(x) for x in args.sweep.split(",") if x.strip()]


def cmd_read(cli, args):
    root = cli.mnt(args.export)
    dfh = resolve_dir(cli, root, args.subdir)
    res, st = cli.lookup(dfh, args.file)
    if not res:
        print(f"LOOKUP {args.file} 失败 status={st}")
        return 1
    fh, attrs = res
    size = attrs["size"]
    rsize = probe_rsize(cli, fh, size) if args.rsize == 0 else args.rsize
    total = min(args.size_mib << 20, size)
    nthr = args.threads

    print(f"# 顺序读  export={args.export}  file={args.subdir}/{args.file}")
    print(f"# 文件={size / (1 << 30):.1f} GiB  读取量={total / (1 << 30):.1f} GiB  "
          f"rsize={rsize / 1024:.0f} KiB")
    print(f"# {'threads':>8} {'MiB/s':>10} {'GiB':>8} {'秒':>8} {'RPC数':>9} "
          f"{'平均RPC延迟ms':>13} {'P95ms':>8}")

    per = total // nthr
    span = max(size - per, 1)
    lock = threading.Lock()
    agg = {"bytes": 0, "rpcs": 0, "lats": []}

    def worker(tid):
        c = Nfs3(args.host, args.uid, args.gid, (100, 101))
        try:
            o = (tid * per) % span
            got, rpcs, lats = 0, 0, []
            while got < per and o < size:
                want = min(rsize, per - got, size - o)
                t0 = time.perf_counter()
                d = c.read(fh, o, want)
                lats.append((time.perf_counter() - t0) * 1000.0)
                if not d:
                    break
                got += len(d)
                o += len(d)
                rpcs += 1
            with lock:
                agg["bytes"] += got
                agg["rpcs"] += rpcs
                agg["lats"].extend(lats)
        finally:
            c.close()

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(nthr)]
    t0 = time.perf_counter()
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    dt = time.perf_counter() - t0
    b, lats = agg["bytes"], sorted(agg["lats"])
    print(f"  {nthr:>8} {b / dt / 1048576:>10.1f} {b / (1 << 30):>8.2f} {dt:>8.2f} "
          f"{agg['rpcs']:>9} {sum(lats) / max(len(lats), 1):>13.2f} "
          f"{pct(lats, 95):>8.2f}")
    return 0


def cmd_read_sweep(cli, args):
    rc = 0
    for n in _sweep(args):
        args.threads = n
        rc = cmd_read(cli, args) or rc
    return rc


def _write_once(cli, args):
    root = cli.mnt(args.export)
    dfh = resolve_dir(cli, root, args.subdir)
    total = args.size_mib << 20
    nthr = args.threads
    mode = UNSTABLE if args.unstable else FILE_SYNC
    mode_name = "UNSTABLE(写回)" if args.unstable else "FILE_SYNC(落盘确认)"

    print(f"# 顺序写  export={args.export}  dir={args.subdir}  "
          f"写入量={total / (1 << 30):.1f} GiB  语义={mode_name}")
    print(f"# {'threads':>8} {'MiB/s':>10} {'GiB':>8} {'秒':>8} {'RPC数':>9} "
          f"{'平均RPC延迟ms':>13} {'P95ms':>8}")

    per = total // nthr
    chunk = min(args.wsize << 10, 1 << 20)   # 单次 WRITE 不要超 1 MiB
    blk = os.urandom(chunk)
    names = [f"__wb_w_{os.getpid()}_{i}.bin" for i in range(nthr)]
    for nm in names:
        cli.remove(dfh, nm)
    fhs = [cli.create(dfh, nm) for nm in names]
    lock = threading.Lock()
    agg = {"bytes": 0, "rpcs": 0, "lats": []}

    def worker(tid):
        c = Nfs3(args.host, args.uid, args.gid, (100, 101))
        try:
            fh = fhs[tid]
            got, rpcs, lats = 0, 0, []
            while got < per:
                want = min(chunk, per - got)
                t0 = time.perf_counter()
                n, _cm = c.write(fh, got, blk[:want], sync=mode)
                lats.append((time.perf_counter() - t0) * 1000.0)
                if n <= 0:
                    break
                got += n
                rpcs += 1
            with lock:
                agg["bytes"] += got
                agg["rpcs"] += rpcs
                agg["lats"].extend(lats)
        finally:
            c.close()

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(nthr)]
    t0 = time.perf_counter()
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    dt = time.perf_counter() - t0

    t1 = time.perf_counter()
    if args.unstable:
        for fh in fhs:
            cli.commit(fh, 0, 0)
    dt_sync = time.perf_counter() - t1

    b, lats = agg["bytes"], sorted(agg["lats"])
    print(f"  {nthr:>8} {b / dt / 1048576:>10.1f} {b / (1 << 30):>8.2f} {dt:>8.2f} "
          f"{agg['rpcs']:>9} {sum(lats) / max(len(lats), 1):>13.2f} "
          f"{pct(lats, 95):>8.2f}")
    if args.unstable:
        print(f"#   └ COMMIT 用时 {dt_sync:.2f}s"
              f"（若接近 0，说明服务端本来就没开写回，UNSTABLE 无收益）")

    if not args.keep:
        for nm in names:
            cli.remove(dfh, nm)
        print(f"# 已清理 {nthr} 个测试文件")
    return 0


def cmd_write(cli, args):
    return _write_once(cli, args)


def cmd_write_sweep(cli, args):
    rc = 0
    for n in _sweep(args):
        args.threads = n
        rc = _write_once(cli, args) or rc
    return rc


def cmd_randread(cli, args):
    root = cli.mnt(args.export)
    dfh = resolve_dir(cli, root, args.subdir)
    res, st = cli.lookup(dfh, args.file)
    if not res:
        print(f"LOOKUP {args.file} 失败 status={st}")
        return 1
    fh, attrs = res
    iosize = args.io_kib << 10
    span = min(attrs["size"], args.size_mib << 20)
    max_off = max(span - iosize, 0)
    nthr = args.threads

    print(f"# 随机读  file={args.subdir}/{args.file}  IO={args.io_kib} KiB  "
          f"span={span / (1 << 30):.2f} GiB  每线程IO数={args.count}")
    print(f"# {'threads':>8} {'IOPS':>10} {'MiB/s':>10} {'秒':>8} "
          f"{'平均延迟ms':>12} {'P95ms':>8} {'P99ms':>8}")

    lock = threading.Lock()
    agg = {"bytes": 0, "rpcs": 0, "lats": []}

    def worker(tid):
        c = Nfs3(args.host, args.uid, args.gid, (100, 101))
        rnd = random.Random(1000 + tid)
        try:
            got, rpcs, lats = 0, 0, []
            for _ in range(args.count):
                off = rnd.randrange(0, max_off + 1, 4096) if max_off else 0
                t0 = time.perf_counter()
                d = c.read(fh, off, iosize)
                lats.append((time.perf_counter() - t0) * 1000.0)
                if not d:
                    break
                got += len(d)
                rpcs += 1
            with lock:
                agg["bytes"] += got
                agg["rpcs"] += rpcs
                agg["lats"].extend(lats)
        finally:
            c.close()

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(nthr)]
    t0 = time.perf_counter()
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    dt = time.perf_counter() - t0
    lats = sorted(agg["lats"])
    print(f"  {nthr:>8} {agg['rpcs'] / dt if dt else 0:>10.0f} "
          f"{agg['bytes'] / dt / 1048576:>10.1f} {dt:>8.2f} "
          f"{sum(lats) / max(len(lats), 1):>12.2f} {pct(lats, 95):>8.2f} "
          f"{pct(lats, 99):>8.2f}")
    return 0


def cmd_randread_sweep(cli, args):
    rc = 0
    for n in _sweep(args):
        args.threads = n
        rc = cmd_randread(cli, args) or rc
    return rc


def cmd_lat(cli, args):
    root = cli.mnt(args.export)
    dfh = resolve_dir(cli, root, args.subdir)
    res, st = cli.lookup(dfh, args.file)
    if not res:
        print(f"LOOKUP {args.file} 失败 status={st}")
        return 1
    fh = res[0]

    lats = []
    for _ in range(200):
        t0 = time.perf_counter()
        cli.getattr(fh)
        lats.append((time.perf_counter() - t0) * 1000.0)
    lats.sort()
    print(f"# 空载 GETATTR: avg={sum(lats) / len(lats):.3f}ms  p50={pct(lats, 50):.3f}  "
          f"p95={pct(lats, 95):.3f}  max={lats[-1]:.3f}")

    nthr = args.threads
    lock = threading.Lock()
    all_lats = []

    def worker(tid):
        c = Nfs3(args.host, args.uid, args.gid, (100, 101))
        try:
            loc = []
            for _ in range(args.count):
                t0 = time.perf_counter()
                c.getattr(fh)
                loc.append((time.perf_counter() - t0) * 1000.0)
            with lock:
                all_lats.extend(loc)
        finally:
            c.close()

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(nthr)]
    t0 = time.perf_counter()
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    dt = time.perf_counter() - t0
    all_lats.sort()
    print(f"# {nthr} 并发 GETATTR x{args.count}: IOPS={len(all_lats) / dt:.0f}  "
          f"avg={sum(all_lats) / len(all_lats):.3f}ms  p50={pct(all_lats, 50):.3f}  "
          f"p95={pct(all_lats, 95):.3f}  p99={pct(all_lats, 99):.3f}  "
          f"max={all_lats[-1]:.3f}")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="极简 NFSv3 客户端与性能基准（纯标准库，不需要管理员）")
    ap.add_argument("cmd", nargs="?",
                    choices=["verify", "rsize", "read", "read-sweep", "write",
                             "write-sweep", "randread", "randread-sweep", "lat"])
    ap.add_argument("--version", "-V", action="store_true")
    ap.add_argument("--host", default=os.environ.get("NAS_HOST", ""),
                    help="NAS 地址；也可用环境变量 NAS_HOST")
    ap.add_argument("--export", default="", help="如 /volume2/<共享名>（注意带 volume 前缀）")
    ap.add_argument("--subdir", default=".", help="export 下的子目录")
    ap.add_argument("--file", default="", help="基准用的已存在大文件（相对 --subdir）")
    ap.add_argument("--uid", type=int, default=1026)
    ap.add_argument("--gid", type=int, default=100)
    ap.add_argument("--size-mib", type=int, default=8192)
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--sweep", default="1,4,8,16")
    ap.add_argument("--rsize", type=int, default=0, help="0=自动探测，单位字节")
    ap.add_argument("--wsize", type=int, default=1024, help="写块 KiB（上限 1024）")
    ap.add_argument("--io-kib", type=int, default=32)
    ap.add_argument("--count", type=int, default=200)
    ap.add_argument("--unstable", action="store_true",
                    help="WRITE 用 UNSTABLE + 末尾 COMMIT（测写回语义）")
    ap.add_argument("--keep", action="store_true", help="写基准后不删测试文件")
    args = ap.parse_args()

    if args.version:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        try:
            from dsm_api import skill_version
            print(f"synology-nas-cli v{skill_version()}")
        except Exception:
            print("synology-nas-cli")
        return 0
    if not args.cmd:
        ap.print_help()
        return 2
    if not args.host:
        ap.error("必须给 --host <NAS_IP>（或设 NAS_HOST）")
    if not args.export:
        ap.error("必须给 --export /volumeN/<共享名>")

    cli = Nfs3(args.host, args.uid, args.gid, (100, 101))
    try:
        if cli.mount_port in (0, None) or cli.nfs_port in (0, None):
            print("!! PORTMAP 查询失败 —— NFS 服务可能未开启")
            return 1
        return {
            "verify": cmd_verify, "rsize": cmd_rsize,
            "read": cmd_read, "read-sweep": cmd_read_sweep,
            "write": cmd_write, "write-sweep": cmd_write_sweep,
            "randread": cmd_randread, "randread-sweep": cmd_randread_sweep,
            "lat": cmd_lat,
        }[args.cmd](cli, args)
    except RpcError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1
    finally:
        cli.close()


if __name__ == "__main__":
    sys.exit(main())
