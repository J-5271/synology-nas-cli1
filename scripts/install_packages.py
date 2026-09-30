#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
套件离线安装 + 共享文件夹 + 日志归档配置（纯标准库，凭据走环境变量）。

背景与已验证路线（见 references/package-install.md）：
  NAS 通常连不上 Synology 的 CDN，Package Center 在线装会失败（error 400）。
  可靠路线是：本地拿到 .spk → FileStation 上传到共享文件夹 → 走
  SYNO.Core.Package.Installation 的 check+install 复合请求，用「磁盘路径」
  （/volume1/<共享>/x.spk）安装。日志归档（LogCenter）用 POST set，
  布尔字段必须传 Python True/False（否则 DSM 报 120）。

复用 dsm_api.py 的 DSM 传输层（同一套凭据约定 DSM_HOST / DSM_ACCOUNT /
DSM_PASSWORD）。所有「写」操作默认关闭，必须显式 --yes 才执行，符合技能
「只读优先、变更需确认」红线。

子命令：
  install        上传并安装一个或多个本地 .spk（离线安装）
  create-share   创建共享文件夹（SYNO.Core.Share create）
  create-folder  在共享文件夹内建子目录（FileStation.CreateFolder）
  set-log-archive 设置日志中心归档路径（SYNO.LogCenter.Setting.Storage set）
  setup          一条龙：建共享文件夹 → 子目录 → 安装套件 → 设置归档 → 清理安装包
  status         只读：列出已装套件 / 共享文件夹 / 当前日志归档设置

环境变量：
  DSM_HOST       必填，含端口，如 http://nas.example.com:5000
  DSM_ACCOUNT    必填
  DSM_PASSWORD   必填
  DSM_VERIFY_SSL 可选，0 = 跳过 TLS 校验（自签名）

退出码：0 成功 / 1 执行失败 / 2 用法错误 / 4 推送自查未过（本脚本不涉及）
"""
import argparse
import json
import mimetypes
import os
import sys
import urllib.request
import uuid

# 复用技能内 dsm_api 的传输层（同一套凭据与登录回退）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dsm_api import DSM, skill_version  # noqa: E402


# --------------------------------------------------------------------------
# 凭据 / 代理：本地 NAS 必须绕过本机可能存在的 MITM 代理（如 127.0.0.1:60575）
# 否则 FileStation 上传会撞代理、ProxyError 10054。把 NAS host 加进 NO_PROXY。
# --------------------------------------------------------------------------
def _bypass_proxy_for(host):
    if not host:
        return
    # 取出 host 中的主机名或 IP（去掉 http:// 与端口）
    h = host.rstrip("/")
    for prefix in ("https://", "http://"):
        if h.startswith(prefix):
            h = h[len(prefix):]
    h = h.split("/")[0].split(":")[0]
    if not h:
        return
    for var in ("NO_PROXY", "no_proxy"):
        cur = os.environ.get(var, "")
        if h not in cur.split(","):
            os.environ[var] = (cur + "," + h).strip(",") if cur else h


def _api_version(dsm, api_name):
    """查询某 API 的 minVersion（安装用）/ maxVersion，失败回退 1。"""
    r = dsm.call("SYNO.API.Info", "Query", 1, {"query": api_name}, cgi="query.cgi")
    info = ((r or {}).get("data") or {}).get(api_name) or {}
    return info


# --------------------------------------------------------------------------
# 只读查询
# --------------------------------------------------------------------------
def list_shares(dsm):
    r = dsm.call("SYNO.Core.Share", "list", 1, {"only_visible": "false"})
    shares = ((r or {}).get("data") or {}).get("shares") or []
    return [s.get("name") for s in shares]


def list_packages(dsm):
    r = dsm.call("SYNO.Core.Package", "list", 1,
                 {"additional": json.dumps(["status", "startable"])})
    pkgs = ((r or {}).get("data") or {}).get("packages") or []
    return pkgs


def get_log_storage(dsm):
    return dsm.call("SYNO.LogCenter.Setting.Storage", "get", 1)


# --------------------------------------------------------------------------
# 文件传输：复用 dsm.opener（已按 NO_PROXY 生效），multipart 上传到共享根路径
# 注意：FileStation 用「共享根路径」如 /nas管理，不是 /volume1/nas管理
# --------------------------------------------------------------------------
def fs_upload(dsm, local_file, share_root, overwrite=True):
    filename = os.path.basename(local_file)
    size = os.path.getsize(local_file)
    ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    boundary = "----WorkBuddySyno" + uuid.uuid4().hex
    fields = {
        "api": "SYNO.FileStation.Upload",
        "version": "2",
        "method": "upload",
        "path": share_root,
        "create_parents": "true",
        "overwrite": "true" if overwrite else "false",
        "_sid": dsm.sid,
    }
    parts = []
    for k, v in fields.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode())
        parts.append(f"{v}\r\n".encode())
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {ctype}\r\n\r\n".encode()
    )
    head = b"".join(parts)
    tail = f"\r\n--{boundary}--\r\n".encode()
    with open(local_file, "rb") as f:
        body = head + f.read() + tail
    req = urllib.request.Request(
        f"{dsm.host}/webapi/entry.cgi", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                 "Content-Length": str(len(body))},
    )
    with dsm.opener.open(req, timeout=300) as resp:
        result = json.loads(resp.read().decode("utf-8", "replace"))
    if not result.get("success"):
        raise RuntimeError(f"upload failed: {result}")
    return result


def fs_create_folder(dsm, share_root, name):
    params = {
        "api": "SYNO.FileStation.CreateFolder", "version": "2",
        "method": "create", "folder_path": share_root, "name": name,
        "force_parent": "true", "_sid": dsm.sid,
    }
    return dsm._post("entry.cgi", params)


def fs_delete(dsm, share_root, filename):
    params = {
        "api": "SYNO.FileStation.Delete", "version": "2", "method": "start_delete_task",
        "path": f"{share_root}/{filename}", "recursive": "true", "_sid": dsm.sid,
    }
    return dsm._post("entry.cgi", params)


# --------------------------------------------------------------------------
# 共享文件夹
# --------------------------------------------------------------------------
def create_share(dsm, name, vol_path="/volume1"):
    # 与 synology_api.Share.create_folder 等价：method=create，shareinfo 作为
    # JSON 字符串参数。注意：部分机型 Web API 建共享文件夹会返回 403，
    # 此时请改用 references/browser-automation.md 的浏览器路线。
    shareinfo = {
        "name": name, "vol_path": vol_path, "desc": "",
        "enable_recycle_bin": True, "recycle_bin_admin_only": True,
    }
    params = {
        "api": "SYNO.Core.Share", "method": "create",
        "version": 1, "name": name,
        "shareinfo": json.dumps(shareinfo), "_sid": dsm.sid,
    }
    return dsm._post("entry.cgi", params)


# --------------------------------------------------------------------------
# 套件离线安装：SYNO.Entry.Request 复合 check+install，path 用磁盘绝对路径
# --------------------------------------------------------------------------
def install_package(dsm, spk_file, share_root, vol_path="/volume1", pid=None):
    filename = os.path.basename(spk_file)
    disk_path = f"{vol_path}/{share_root.lstrip('/')}/{filename}"
    pid = pid or filename.split("-")[0]
    inst_info = _api_version(dsm, "SYNO.Core.Package.Installation")
    entry_info = _api_version(dsm, "SYNO.Entry.Request")
    inst_ver = inst_info.get("minVersion", 1)
    entry_ver = entry_info.get("maxVersion", 1)

    # 先上传 .spk 到共享根路径
    print(f"[*] 上传 {filename} -> {share_root}")
    fs_upload(dsm, spk_file, share_root, overwrite=True)

    compound = [
        {
            "api": "SYNO.Core.Package.Installation", "method": "check",
            "version": inst_ver, "id": pid, "install_type": "",
            "install_on_cold_storage": False, "breakpkgs": None,
            "blCheckDep": False, "replacepkgs": None,
        },
        {
            "api": "SYNO.Core.Package.Installation", "method": "install",
            "version": inst_ver, "type": 0, "volume_path": vol_path,
            "path": disk_path, "check_codesign": True, "force": True,
            "installrunpackage": True, "extra_values": "{}",
        },
    ]
    params = {
        "api": "SYNO.Entry.Request", "method": "request", "version": entry_ver,
        "mode": "sequential", "stop_when_error": "true",
        "_sid": dsm.sid, "compound": json.dumps(compound),
    }
    print(f"[*] 安装 {pid}（磁盘路径 {disk_path}）")
    return dsm._post("entry.cgi", params)


# --------------------------------------------------------------------------
# 日志归档：先 get 当前设置，再 set（布尔字段必须转 true/false 字符串）
# --------------------------------------------------------------------------
def set_log_archive(dsm, disk_path, archive=True, enable_time=True):
    cur = get_log_storage(dsm)
    data = ((cur or {}).get("data") or {}).copy()
    data["path"] = disk_path
    data["archive"] = archive
    data["enable_time"] = enable_time
    params = {
        "api": "SYNO.LogCenter.Setting.Storage", "method": "set",
        "version": 1, "_sid": dsm.sid,
    }
    for k, v in data.items():
        if isinstance(v, bool):
            params[k] = "true" if v else "false"
        else:
            params[k] = v
    return dsm._post("entry.cgi", params)


# --------------------------------------------------------------------------
# 命令实现
# --------------------------------------------------------------------------
def ensure_confirm(args):
    if not args.yes:
        sys.exit("[ERROR] 这是变更操作，必须加 --yes 确认（参考 --help）")


def cmd_install(args):
    ensure_confirm(args)
    dsm = DSM()
    if not dsm.login():
        return 1
    try:
        for spk in args.files:
            install_package(dsm, spk, args.share, vol_path=args.volume,
                            pid=args.pid)
        print("[✓] 安装请求已提交（安装为异步，稍后 status 复核）")
    finally:
        dsm.logout()
    return 0


def cmd_create_share(args):
    ensure_confirm(args)
    dsm = DSM()
    if not dsm.login():
        return 1
    try:
        r = create_share(dsm, args.name, vol_path=args.volume)
        if (r or {}).get("success"):
            print(f"[✓] 共享文件夹 {args.name} 已创建")
        else:
            code = ((r or {}).get("error") or {}).get("code")
            print(f"[✗] 创建失败：{json.dumps(r, ensure_ascii=False)}")
            if code == 403:
                print("    该机型 Web API 建共享文件夹返回 403，"
                      "请改用 references/browser-automation.md 的浏览器路线。")
            return 1
    finally:
        dsm.logout()
    return 0


def cmd_create_folder(args):
    ensure_confirm(args)
    dsm = DSM()
    if not dsm.login():
        return 1
    try:
        r = fs_create_folder(dsm, args.share, args.name)
        if (r or {}).get("success"):
            print(f"[✓] {args.share}/{args.name} 已创建")
        else:
            print(f"[✗] 创建失败：{json.dumps(r, ensure_ascii=False)}")
            return 1
    finally:
        dsm.logout()
    return 0


def cmd_set_log_archive(args):
    ensure_confirm(args)
    dsm = DSM()
    if not dsm.login():
        return 1
    try:
        disk = f"{args.volume}/{args.share.lstrip('/')}/{args.sub}"
        r = set_log_archive(dsm, disk)
        if (r or {}).get("success"):
            print(f"[✓] 日志归档已设为 {disk}")
        else:
            print(f"[✗] 设置失败：{json.dumps(r, ensure_ascii=False)}")
            return 1
    finally:
        dsm.logout()
    return 0


def cmd_setup(args):
    ensure_confirm(args)
    dsm = DSM()
    if not dsm.login():
        return 1
    try:
        # 1) 共享文件夹
        if args.name not in list_shares(dsm):
            r = create_share(dsm, args.name, vol_path=args.volume)
            if (r or {}).get("success"):
                print(f"[✓] 共享文件夹 {args.name} 已创建")
            else:
                code = ((r or {}).get("error") or {}).get("code")
                print(f"[!] 共享文件夹创建失败 {json.dumps(r, ensure_ascii=False)}")
                if code == 403:
                    print("    请改用浏览器路线手动建共享文件夹后继续。")
                    return 1
        else:
            print(f"[=] 共享文件夹 {args.name} 已存在，跳过")
        # 2) 子目录
        for sub in args.subs:
            r = fs_create_folder(dsm, args.name, sub)
            print(f"[{'✓' if (r or {}).get('success') else '✗'}] 子目录 {args.name}/{sub}")
        # 3) 安装套件
        for spk in args.files:
            install_package(dsm, spk, args.name, vol_path=args.volume, pid=args.pid)
        # 4) 日志归档
        if args.sub:
            disk = f"{args.volume}/{args.name.lstrip('/')}/{args.subs[0]}"
            r = set_log_archive(dsm, disk)
            print(f"[{'✓' if (r or {}).get('success') else '✗'}] 日志归档 -> {disk}")
        # 5) 清理安装包
        if args.clean:
            for spk in args.files:
                fs_delete(dsm, args.name, os.path.basename(spk))
                print(f"[✓] 已删除安装包 {os.path.basename(spk)}")
        print("[✓] setup 完成（套件安装为异步，稍后用 status 复核）")
    finally:
        dsm.logout()
    return 0


def cmd_status(args):
    dsm = DSM()
    if not dsm.login():
        return 1
    try:
        print("=== 共享文件夹 ===")
        for s in list_shares(dsm):
            print("  ", s)
        print("=== 已装套件 ===")
        for p in list_packages(dsm):
            add = p.get("additional") or {}
            print(f"   {p.get('id'):<24} v{p.get('version'):<16} "
                  f"status={add.get('status')}")
        print("=== 日志归档设置 ===")
        print(json.dumps(get_log_storage(dsm), ensure_ascii=False, indent=1))
    finally:
        dsm.logout()
    return 0


def main():
    p = argparse.ArgumentParser(
        description="套件离线安装 + 共享文件夹 + 日志归档（纯标准库）")
    sub = p.add_subparsers(dest="cmd")

    pi = sub.add_parser("install", help="上传并安装本地 .spk")
    pi.add_argument("files", nargs="+", help="本地 .spk 文件路径")
    pi.add_argument("--share", required=True, help="上传目标共享根路径，如 nas管理")
    pi.add_argument("--volume", default="/volume1")
    pi.add_argument("--pid", help="套件 ID（默认取文件名首段）")
    pi.add_argument("--yes", action="store_true")
    pi.set_defaults(func=cmd_install)

    ps = sub.add_parser("create-share", help="创建共享文件夹")
    ps.add_argument("--name", required=True)
    ps.add_argument("--volume", default="/volume1")
    ps.add_argument("--yes", action="store_true")
    ps.set_defaults(func=cmd_create_share)

    pf = sub.add_parser("create-folder", help="在共享文件夹内建子目录")
    pf.add_argument("--share", required=True)
    pf.add_argument("--name", required=True, help="子目录名")
    pf.add_argument("--yes", action="store_true")
    pf.set_defaults(func=cmd_create_folder)

    pl = sub.add_parser("set-log-archive", help="设置日志中心归档路径")
    pl.add_argument("--share", required=True)
    pl.add_argument("--sub", required=True, help="归档子目录名（在共享文件夹内）")
    pl.add_argument("--volume", default="/volume1")
    pl.add_argument("--yes", action="store_true")
    pl.set_defaults(func=cmd_set_log_archive)

    pu = sub.add_parser("setup", help="一条龙：建共享文件夹→子目录→安装→归档→清理")
    pu.add_argument("--name", required=True, help="共享文件夹名")
    pu.add_argument("--subs", nargs="*", default=[], help="共享文件夹内子目录列表")
    pu.add_argument("--files", nargs="*", default=[], help="本地 .spk 文件列表")
    pu.add_argument("--volume", default="/volume1")
    pu.add_argument("--pid", help="套件 ID（默认取文件名首段）")
    pu.add_argument("--clean", action="store_true", help="安装后删除 .spk")
    pu.add_argument("--yes", action="store_true")
    pu.set_defaults(func=cmd_setup)

    pst = sub.add_parser("status", help="只读：列共享文件夹/套件/日志归档")
    pst.set_defaults(func=cmd_status)

    p.add_argument("--version", action="store_true", help="显示技能包版本")
    args = p.parse_args()
    if args.version:
        print(f"synology-nas-cli v{skill_version()}")
        return 0
    if not getattr(args, "cmd", None):
        p.print_help()
        return 2
    _bypass_proxy_for(os.environ.get("DSM_HOST", ""))
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
