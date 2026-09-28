#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把本地文件上传到 ima 的 COS（create_media 之后、add_knowledge 之前的第二步）。

ima 的入库是三步：create_media → 上传文件到 COS → add_knowledge。
本脚本干中间那步，只用标准库（不依赖 requests / cos-sdk）。

用法：
    python3 cos_upload.py --cred-file /path/to/create_media_response.json \
                          --file /path/to/local.md

--cred-file 里放 ima create_media 工具返回的完整 JSON（含 cos_credential 与 cos_key）。
"""
import argparse
import hashlib
import hmac
import json
import os
import sys
import urllib.parse
import urllib.request


def _hmac_sha1(key: bytes, msg: str) -> str:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha1).hexdigest()


def build_auth(cred: dict, method: str, cos_key: str, headers: dict) -> str:
    secret_id = cred["secret_id"]
    secret_key = cred["secret_key"]
    start = cred["start_time"]
    end = cred["expired_time"]
    keytime = f"{start};{end}"
    sign_key = _hmac_sha1(secret_key.encode("utf-8"), keytime)

    hl = sorted(k.lower() for k in headers)
    header_list = ";".join(hl)
    http_headers = "&".join(
        f"{urllib.parse.quote(k.lower(), safe='')}={urllib.parse.quote(str(headers[k]), safe='')}"
        for k in sorted(headers, key=lambda x: x.lower())
    )
    http_string = f"{method.lower()}\n{cos_key}\n\n{http_headers}\n"
    string_to_sign = f"sha1\n{keytime}\n{hashlib.sha1(http_string.encode('utf-8')).hexdigest()}\n"
    signature = _hmac_sha1(sign_key.encode("utf-8"), string_to_sign)

    return (f"q-sign-algorithm=sha1&q-ak={secret_id}&q-sign-time={keytime}"
            f"&q-key-time={keytime}&q-header-list={header_list}"
            f"&q-url-param-list=&q-signature={signature}")


def main():
    ap = argparse.ArgumentParser(description="Upload a file to ima COS with temporary credentials.")
    ap.add_argument("--cred-file", required=True, help="JSON file: full create_media response")
    ap.add_argument("--file", required=True, help="local file to upload")
    args = ap.parse_args()

    with open(args.cred_file, encoding="utf-8") as f:
        resp = json.load(f)
    cred = resp["cos_credential"]
    cos_key = resp["cos_key"]
    if not cos_key.startswith("/"):
        cos_key = "/" + cos_key

    path = os.path.abspath(args.file)
    if not os.path.exists(path):
        print(f"[ERROR] file not found: {path}", file=sys.stderr)
        return 2
    with open(path, "rb") as f:
        data = f.read()

    # bucket_name 已带 appid 后缀（如 ima-share-kb-1258344701），不要再拼一次
    bucket = cred["bucket_name"]
    if not bucket.endswith(f"-{cred['appid']}"):
        bucket = f"{bucket}-{cred['appid']}"
    # 两个候选 host：标准 COS 域名优先，失败再试凭证里给的 custom_domain。
    # 实测（2026-09-27）出现过标准域名 403 InvalidAccessKeyId、换 custom_domain 才通过的情况。
    hosts = [f"{bucket}.cos.{cred['region']}.myqcloud.com"]
    if cred.get("custom_domain"):
        hosts.append(cred["custom_domain"])

    last_err = None
    for host in hosts:
        url = f"https://{host}{urllib.parse.quote(cos_key, safe='/')}"
        headers = {
            "Host": host,
            "Content-Type": "application/octet-stream",
            "Content-Length": str(len(data)),
            "x-cos-security-token": cred["token"],
        }
        headers["Authorization"] = build_auth(cred, "put", cos_key,
                                              {k: v for k, v in headers.items()
                                               if k.lower() in ("host", "content-type",
                                                                "content-length",
                                                                "x-cos-security-token")})
        req = urllib.request.Request(url, data=data, headers=headers, method="PUT")
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                print(f"uploaded {len(data)} bytes -> HTTP {r.status} (host={host})")
                return 0
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code} via {host}: {e.read().decode('utf-8', 'replace')[:300]}"
            print(f"[WARN] {last_err}", file=sys.stderr)
        except urllib.error.URLError as e:
            last_err = f"URLError via {host}: {e.reason}"
            print(f"[WARN] {last_err}", file=sys.stderr)

    print(f"[ERROR] upload failed: {last_err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
