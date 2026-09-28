#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FileStation 上传 / 下载 / 列目录。

复用 robinFdr/synology-nas-cli 的 FileStation 用法思路（auth.cgi + format=sid、
SYNO.FileStation.Upload / Download / List、多文件、stdin 管道、--no-overwrite、
--output-dir），改用**纯标准库**实现，与 dsm_api.py 同一套凭据约定：

    SYNO_HOST        required，含端口，如 http://nas.example.com:5000
    SYNO_USER        required
    SYNO_PASS        required
    SYNO_VERIFY_SSL  optional，0 = 跳过 TLS 校验（自签名）

用法：
    syno.py --list /volume1/下载                     # 列目录（只读）
    syno.py a.mp4 b.mp4 --remote /volume1/video      # 上传多个文件
    ls *.m4a | syno.py --remote /volume1/audio       # 管道上传
    syno.py --download /volume1/video/a.mp4 --out .  # 下载
    syno.py a.mp4 --no-overwrite --remote /x/y       # 不覆盖已存在文件

上传走 multipart/form-data（SYNO.FileStation.Upload v2），下载走 SYNO.FileStation.Download v2。
只做文件传输，不含任何改配置 / 删文件能力。
"""
import argparse
import json
import mimetypes
import os
import ssl
import sys
import urllib.parse
import urllib.request
import uuid

AUTH_API = "SYNO.API.Auth"
AUTH_VERSIONS = (7, 6, 3, 2)


class FileStation:
    def __init__(self, host, user, password, verify_ssl=True):
        self.host = host.rstrip("/")
        self.user = user
        self.password = password
        self.sid = None
        self.ctx = None
        if not verify_ssl:
            self.ctx = ssl.create_default_context()
            self.ctx.check_hostname = False
            self.ctx.verify_mode = ssl.CERT_NONE
        handlers = []
        if self.ctx is not None:
            handlers.append(urllib.request.HTTPSHandler(context=self.ctx))
        self.opener = urllib.request.build_opener(*handlers)

    # --------------------------------------------------------------- login
    def login(self):
        last = None
        for ver in AUTH_VERSIONS:
            try:
                r = self._post("auth.cgi", {
                    "api": AUTH_API, "version": ver, "method": "login",
                    "account": self.user, "passwd": self.password,
                    "session": "FileStation", "format": "sid",
                })
            except Exception as e:  # noqa: BLE001
                last = e
                continue
            if r.get("success"):
                self.sid = r["data"]["sid"]
                return
            last = r
        raise RuntimeError(f"login failed: {last}")

    def _post(self, cgi, data):
        url = f"{self.host}/webapi/{cgi}"
        body = urllib.parse.urlencode(data).encode("utf-8")
        req = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        with self.opener.open(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))

    def _entry(self, data):
        if self.sid:
            data = dict(data)
            data["_sid"] = self.sid
        return self._post("entry.cgi", data)

    # ------------------------------------------------------------ list
    def list_folder(self, path):
        # FileStation.List 的 _sid 必须走 URL 查询参数（与 dsm_api.py 一致）
        params = {
            "api": "SYNO.FileStation.List", "version": "2", "method": "list",
            "folder_path": path,
        }
        if self.sid:
            params["_sid"] = self.sid
        url = f"{self.host}/webapi/entry.cgi?" + urllib.parse.urlencode(params)
        with self.opener.open(url, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))

    # ------------------------------------------------------------ upload
    def upload(self, local_file, remote_path, overwrite=True):
        filename = os.path.basename(local_file)
        size = os.path.getsize(local_file)
        ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        boundary = "----WorkBuddySyno" + uuid.uuid4().hex
        parts = []
        fields = {
            "api": "SYNO.FileStation.Upload",
            "version": "2",
            "method": "upload",
            "path": remote_path,
            "create_parents": "true",
            "overwrite": "true" if overwrite else "false",
        }
        if self.sid:
            fields["_sid"] = self.sid
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
            f"{self.host}/webapi/entry.cgi", data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                     "Content-Length": str(len(body))},
        )
        with self.opener.open(req, timeout=300) as resp:
            result = json.loads(resp.read().decode("utf-8", "replace"))
        if not result.get("success"):
            raise RuntimeError(f"upload failed: {result}")
        return result

    # ------------------------------------------------------------ download
    def download(self, remote_file, output_dir="."):
        filename = remote_file.split("/")[-1]
        out_dir = os.path.abspath(os.path.expanduser(output_dir))
        local_path = os.path.join(out_dir, filename)
        params = {
            "api": "SYNO.FileStation.Download", "version": "2", "method": "download",
            "path": remote_file, "mode": "download",
        }
        if self.sid:
            params["_sid"] = self.sid
        url = f"{self.host}/webapi/entry.cgi?" + urllib.parse.urlencode(params)
        with self.opener.open(url, timeout=300) as resp:
            with open(local_path, "wb") as f:
                while True:
                    chunk = resp.read(1024 * 64)
                    if not chunk:
                        break
                    f.write(chunk)
        return local_path


def main():
    p = argparse.ArgumentParser(
        description="FileStation 上传/下载/列目录（纯标准库，凭据走环境变量）")
    p.add_argument("files", nargs="*", help="本地文件（上传）或 NAS 路径（下载）")
    p.add_argument("--host", default=os.environ.get("SYNO_HOST", ""))
    p.add_argument("--user", default=os.environ.get("SYNO_USER", ""))
    p.add_argument("--password", default=os.environ.get("SYNO_PASS", ""))
    p.add_argument("--remote", default=os.environ.get("SYNO_REMOTE_PATH", ""),
                   help="上传目标目录（env: SYNO_REMOTE_PATH）")
    p.add_argument("--list", metavar="FOLDER", help="列出目录内容后退出（只读）")
    p.add_argument("--download", action="store_true", help="下载而非上传")
    p.add_argument("--output-dir", default=".", help="下载到本地目录（默认当前目录）")
    p.add_argument("--no-overwrite", action="store_true", help="上传时不覆盖已存在文件")
    p.add_argument("--no-verify-ssl", action="store_true", help="跳过 TLS 校验（自签名）")
    args = p.parse_args()

    if not args.host or not args.user:
        p.error("需要 --host/--user（或 SYNO_HOST/SYNO_USER 环境变量）")

    password = args.password
    if not password:
        import getpass
        password = getpass.getpass(f"Password for {args.user}@{args.host}: ")

    fs = FileStation(args.host, args.user, password,
                     verify_ssl=not args.no_verify_ssl)
    fs.login()

    if args.list:
        print(json.dumps(fs.list_folder(args.list), indent=2, ensure_ascii=False))
        return 0

    raw = args.files
    if not raw and not sys.stdin.isatty():
        raw = [line.strip() for line in sys.stdin if line.strip()]

    if not raw:
        p.error("未指定文件")

    if args.download:
        for rf in raw:
            out = fs.download(rf, args.output_dir)
            print(f"✓ {rf} -> {out}")
        return 0

    if not args.remote:
        p.error("上传需要 --remote 或 SYNO_REMOTE_PATH")

    errors = []
    local_files = []
    for f in raw:
        ap = os.path.abspath(os.path.expanduser(f))
        if os.path.isfile(ap):
            local_files.append(ap)
        else:
            errors.append(ap)

    if errors:
        for e in errors:
            print(f"[ERROR] 文件不存在: {e}", file=sys.stderr)
        return 1

    for lf in local_files:
        fs.upload(lf, args.remote, overwrite=not args.no_overwrite)
        print(f"✓ {os.path.basename(lf)} -> {args.remote}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
