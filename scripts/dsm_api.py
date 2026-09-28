#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Talk to a Synology DSM over its official Web API.

Verified against a real DS918+ (DSM with 1644 registered APIs):

  * Auth endpoint lives at ``/webapi/entry.cgi`` with ``api=SYNO.API.Auth``.
  * **maxVersion reported by SYNO.API.Info may not actually work.**
    That box advertises maxVersion=7 but v7 login returns error 103,
    while **v6 works**. So always try v7 first then fall back to v6.
  * Discover what exists with ``/webapi/query.cgi?api=SYNO.API.Info&...&query=all``
    — DSM error **102 = API does not exist** (wrong name, NOT permission denied),
    so check the registry before assuming you lack privileges.
  * HTTP-only DSM works fine, but credentials then travel in plaintext.

Credentials come from the environment; nothing is ever written to disk:

    DSM_HOST       required, include port   e.g. http://nas.example.com:5000
    DSM_ACCOUNT    required                 e.g. myadmin
    DSM_PASSWORD   required
    DSM_SESSION    optional, session name, default "NasCli"
    DSM_VERIFY_SSL optional, set 0 to skip TLS verification (self-signed)

Usage:
    dsm_api.py info              # system summary (read-only)
    dsm_api.py apis [filter]     # list registered APIs
    dsm_api.py call SYNO.Core.Share list
    dsm_api.py call SYNO.Core.System info 3 version=1
    dsm_api.py logout
    dsm_api.py raw SYNO.Core.Terminal get 1 'enable_ssh=true'   # POST via GET params
"""
import json
import os
import ssl
import sys
import urllib.parse
import urllib.request
import http.cookiejar

AUTH_API = "SYNO.API.Auth"
AUTH_VERSIONS = (7, 6, 3, 2)
SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 登录失败的常见错误码 → 给用户的下一步建议（见 references/dsm-web-api.md 第三节）
LOGIN_HINTS = {
    102: "API 不存在——先用 `dsm_api.py apis` 查注册表，别当成权限不足",
    103: "该 Auth 版本不可用——脚本会自动降版本重试，若全失败请报实测记录",
    105: "权限不足——确认账号在 administrators 群组",
    117: "需要二次验证（OTP）——脚本暂不支持 OTP 流程",
    400: "账号或密码错误——核对 DSM_ACCOUNT / DSM_PASSWORD",
    401: "账号被禁用——到 DSM 用户列表启用",
    403: "多次失败被锁定或需要二次验证——查 控制面板 > 安全性",
}


def skill_version():
    try:
        with open(os.path.join(SKILL_ROOT, "VERSION"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "未知"


class DSM:
    def __init__(self):
        self.host = os.environ.get("DSM_HOST", "").rstrip("/")
        self.account = os.environ.get("DSM_ACCOUNT", "")
        self.password = os.environ.get("DSM_PASSWORD", "")
        self.session = os.environ.get("DSM_SESSION", "NasCli")
        if not (self.host and self.account and self.password):
            sys.exit("[ERROR] DSM_HOST / DSM_ACCOUNT / DSM_PASSWORD must be set")

        self.ctx = None
        if os.environ.get("DSM_VERIFY_SSL", "1") == "0":
            self.ctx = ssl.create_default_context()
            self.ctx.check_hostname = False
            self.ctx.verify_mode = ssl.CERT_NONE

        self.cj = http.cookiejar.CookieJar()
        handlers = [urllib.request.HTTPCookieProcessor(self.cj)]
        if self.ctx is not None:
            handlers.append(urllib.request.HTTPSHandler(context=self.ctx))
        self.opener = urllib.request.build_opener(*handlers)
        self.sid = None

    # ------------------------------------------------------------ transport
    def _get(self, cgi, params):
        url = f"{self.host}/webapi/{cgi}?" + urllib.parse.urlencode(params)
        with self.opener.open(url, timeout=40) as r:
            return json.loads(r.read().decode("utf-8", "replace"))

    def _post(self, cgi, params):
        url = f"{self.host}/webapi/{cgi}"
        body = urllib.parse.urlencode(params).encode("utf-8")
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        with self.opener.open(req, timeout=40) as r:
            return json.loads(r.read().decode("utf-8", "replace"))

    # --------------------------------------------------------------- login
    def login(self):
        """POST 优先（密码不进 URL，不落进访问日志/代理日志），POST 不通回退 GET。"""
        last = None
        for ver in AUTH_VERSIONS:
            params = {
                "api": AUTH_API, "version": ver, "method": "Login",
                "account": self.account, "passwd": self.password,
                "session": self.session, "format": "sid",
            }
            try:
                r = self._post("entry.cgi", params)
            except Exception:
                try:
                    r = self._get("entry.cgi", params)
                except Exception as e:
                    last = {"_exc": str(e)}
                    continue
            if r.get("success"):
                self.sid = r["data"]["sid"]
                self.auth_version = ver
                return True
            last = r
        code = (last or {}).get("error", {}).get("code") if isinstance(last, dict) else None
        hint = LOGIN_HINTS.get(code, "")
        print(f"[ERROR] login failed for {self.account}@{self.host}: "
              f"{json.dumps(last, ensure_ascii=False)}", file=sys.stderr)
        if hint:
            print(f"        下一步：{hint}", file=sys.stderr)
        return False

    def logout(self):
        if not self.sid:
            return True
        try:
            self._get("entry.cgi", {"api": AUTH_API, "version": self.auth_version,
                                    "method": "Logout", "session": self.session,
                                    "_sid": self.sid})
            self.sid = None
            return True
        except Exception as e:
            print(f"[WARN] logout failed: {e}", file=sys.stderr)
            return False

    # ------------------------------------------------------------- api call
    def call(self, api, method, version=1, extra=None, cgi="entry.cgi", retry=True):
        if not self.sid and not self.login():
            return None
        params = {"api": api, "version": version, "method": method, "_sid": self.sid}
        if extra:
            params.update(extra)
        r = self._get(cgi, params)
        code = (r.get("error") or {}).get("code")
        # 119 = session expired -> re-login once and retry
        if code == 119 and retry:
            print("[INFO] session expired, re-authenticating", file=sys.stderr)
            self.sid = None
            if self.login():
                return self.call(api, method, version, extra, cgi, retry=False)
        return r


def show(d, keys=None, limit=0):
    print(json.dumps(d, ensure_ascii=False, indent=1))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    if sys.argv[1] in ("--version", "-V"):
        print(f"synology-nas-cli v{skill_version()}")
        return 0
    cmd = sys.argv[1]

    dsm = DSM()
    if cmd == "logout":
        if not dsm.login():
            return 1
        return 0 if dsm.logout() else 1

    if not dsm.login():
        return 1
    try:
        if cmd == "info":
            for label, api, method, ver, keys in [
                ("SYSTEM", "SYNO.Core.System", "info", 3,
                 ("model", "serial", "version", "version_string",
                  "cpu_vendor", "cpu_clock_speed", "ram_size", "time")),
                ("SSH / TELNET", "SYNO.Core.Terminal", "get", 3, None),
            ]:
                r = dsm.call(api, method, ver)
                print(f"\n===== {label} =====")
                if isinstance(r, dict) and r.get("success"):
                    data = r["data"]
                    if keys:
                        data = {k: v for k, v in data.items() if k in keys}
                    show(data)
                else:
                    print("  ", json.dumps(r, ensure_ascii=False)[:200])
            r = dsm.call("SYNO.Core.Share", "list", 1, {"only_visible": "false"})
            if isinstance(r, dict) and r.get("success"):
                print(f"\n===== SHARED FOLDERS (total {r['data'].get('total')}) =====")
                for s in (r["data"].get("shares") or [])[:20]:
                    print("  ", s.get("name"))

        elif cmd == "apis":
            filt = sys.argv[2] if len(sys.argv) > 2 else ""
            r = dsm.call("SYNO.API.Info", "Query", 1, {"query": "all"}, cgi="query.cgi")
            apis = (r or {}).get("data") or {}
            print(f"registered APIs: {len(apis)}")
            for k, v in sorted(apis.items()):
                if not filt or filt.lower() in k.lower():
                    print(f"  {k:<50} path={v.get('path')} "
                          f"v{v.get('minVersion')}-{v.get('maxVersion')}")

        elif cmd == "call" and len(sys.argv) >= 4:
            api, method = sys.argv[2], sys.argv[3]
            ver = int(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4].isdigit() else 1
            extra = {}
            for a in sys.argv[4:]:
                if "=" in a:
                    k, v = a.split("=", 1)
                    extra[k] = v
            show(dsm.call(api, method, ver, extra or None))

        elif cmd == "raw" and len(sys.argv) >= 5:
            api, method = sys.argv[2], sys.argv[3]
            ver = int(sys.argv[4])
            extra = dict(a.split("=", 1) for a in sys.argv[5:] if "=" in a)
            show(dsm.call(api, method, ver, extra or None))

        else:
            print(__doc__)
            return 2
    finally:
        dsm.logout()
    return 0


if __name__ == "__main__":
    sys.exit(main())
