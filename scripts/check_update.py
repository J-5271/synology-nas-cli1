#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_update.py —— 检查技能包是否有新版本（纯标准库，可选依赖 requests）。

用途：
  - 对比「本地 VERSION / .update_state.json」与 GitHub 公开仓库的最新 Release / tag / commit
  - 输出人类可读摘要 或 --json 供自动化消费
  - 供无法访问 GitHub 的用户做兜底：失败时打印腾讯文档版本记录地址

用法：
  python scripts/check_update.py                 # 人类可读摘要
  python scripts/check_update.py --json          # 机器可读（供自动化/脚本）
  python scripts/check_update.py --mark-seen     # 把当前远端状态写回 .update_state.json
  python scripts/check_update.py --set-version 1.1.0   # 手动改本地版本基线

退出码：
  0  有更新（或已 --mark-seen / --set-version 成功）
  3  无更新（已是最新）
  4  查询失败（网络不通 / GitHub 不可达 / 仓库不存在）

隐私：只访问公开只读接口（api.github.com），不发送任何本机信息，不读取 NAS 凭据。
"""

import argparse
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request

REPO_OWNER = "J-5271"
REPO_NAME = "synology-nas-cli1"
REPO_URL = "https://github.com/J-5271/synology-nas-cli1"
RELEASES_URL = "https://github.com/J-5271/synology-nas-cli1/releases"
API_BASE = "https://api.github.com/repos/J-5271/synology-nas-cli1"

# 兜底：GitHub 不可达时，让用户去这里看最新版本记录（腾讯文档）
MIRROR_URL = os.environ.get(
    "NASKILL_MIRROR_URL",
    "https://docs.qq.com/aio/DQ05IdUxxR3ZtUndG",  # 腾讯文档《synology-nas-cli 版本更新记录》
)

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION_FILE = os.path.join(SKILL_ROOT, "VERSION")
STATE_FILE = os.path.join(SKILL_ROOT, ".update_state.json")

UA = {"User-Agent": "synology-nas-cli-update-checker", "Accept": "application/vnd.github+json"}


# --------------------------------------------------------------------------- IO
def _get(url, timeout=15):
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def read_version():
    try:
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            return f.read().strip() or "0.0.0"
    except OSError:
        return "0.0.0"


def read_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _norm(v):
    """去掉 v 前缀与前后空白，便于比较。"""
    return (v or "").strip().lstrip("vV")


def _vtuple(v):
    """语义化版本 → 可比较元组；非标准版本返回 (0,)。"""
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)", _norm(v))
    if not m:
        return (0,)
    return tuple(int(x) for x in m.groups())


def newer(a, b):
    """a 是否比 b 新（均为字符串版本号）。无法解析时按字符串不等判断。"""
    ta, tb = _vtuple(a), _vtuple(b)
    if ta == (0,) or tb == (0,):
        return _norm(a) != _norm(b)
    return ta > tb


# ------------------------------------------------------------------- 远端查询
def fetch_latest(timeout=15):
    """返回 dict: {version, name, published_at, url, notes, commit, source}。"""
    out = {
        "version": "",
        "name": "",
        "published_at": "",
        "url": RELEASES_URL,
        "notes": "",
        "commit": "",
        "source": "",
    }

    # 1) 最新 Release（优先）
    try:
        rel = _get(API_BASE + "/releases/latest", timeout)
        if isinstance(rel, dict) and rel.get("tag_name"):
            out.update(
                version=_norm(rel.get("tag_name", "")),
                name=rel.get("name") or rel.get("tag_name", ""),
                published_at=rel.get("published_at") or rel.get("created_at") or "",
                url=rel.get("html_url") or RELEASES_URL,
                notes=(rel.get("body") or "").strip(),
                source="release",
            )
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
    except (urllib.error.URLError, OSError, ValueError):
        raise

    # 2) 没 Release 就退到 tag 列表
    if not out["version"]:
        try:
            tags = _get(API_BASE + "/tags?per_page=5", timeout)
            if tags:
                out.update(
                    version=_norm(tags[0].get("name", "")),
                    name=tags[0].get("name", ""),
                    url="%s/releases/tag/%s" % (REPO_URL, tags[0].get("name", "")),
                    source="tag",
                )
        except urllib.error.HTTPError:
            pass

    # 3) 再退到 main HEAD（dev 基线，未打 tag 时的唯一可比对象）
    try:
        br = _get(API_BASE + "/branches/main", timeout)
        sha = (br.get("commit") or {}).get("sha", "")
        if sha:
            out["commit"] = sha
            if not out["version"]:
                out["version"] = "main@" + sha[:7]
                out["source"] = "branch"
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, ValueError):
        pass

    # 4) commit 列表：用于算「本地水位之后新增了哪些 commit」
    try:
        cs = _get(API_BASE + "/commits?sha=main&per_page=30", timeout)
        out["_commits"] = [
            {
                "sha": c.get("sha", "")[:7],
                "message": ((c.get("commit") or {}).get("message") or "").splitlines()[0]
                if (c.get("commit") or {}).get("message")
                else "",
                "date": ((c.get("commit") or {}).get("author") or {}).get("date", ""),
            }
            for c in cs
        ]
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, ValueError):
        out["_commits"] = []

    return out


def diff_commits(remote_commits, since_sha):
    """返回 since_sha 之后新增的 commit（按时间正序）。since_sha 为空则全返回前 10。"""
    if not remote_commits:
        return []
    out = []
    for c in remote_commits:
        if since_sha and (
            c["sha"] == since_sha[:7] or remote_sha_match(c, since_sha)
        ):
            break
        out.append(c)
    if not since_sha:
        out = out[:10]
    return out


def remote_sha_match(c, full_sha):
    return full_sha.startswith(c["sha"])


# ----------------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser(description="检查 synology-nas-cli 技能包是否有新版本")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--mark-seen", action="store_true", help="把当前远端状态写回水位文件")
    ap.add_argument("--set-version", metavar="X.Y.Z", help="手动设置本地版本基线")
    ap.add_argument("--timeout", type=int, default=15, help="单次 HTTP 超时秒数，默认 15")
    ap.add_argument("--repo", help="覆盖仓库，格式 owner/name（默认 %s/%s）" % (REPO_OWNER, REPO_NAME))
    ap.add_argument("--version", action="store_true", help="显示技能包版本后退出")
    args = ap.parse_args()

    if args.version:
        print("synology-nas-cli v%s" % read_version())
        return 0

    global API_BASE, REPO_URL, RELEASES_URL
    if args.repo:
        API_BASE = "https://api.github.com/repos/" + args.repo
        REPO_URL = "https://github.com/" + args.repo
        RELEASES_URL = REPO_URL + "/releases"

    if args.set_version:
        with open(VERSION_FILE, "w", encoding="utf-8") as f:
            f.write(_norm(args.set_version) + "\n")
        if args.json:
            print(json.dumps({"ok": True, "version": _norm(args.set_version)}, ensure_ascii=False))
        else:
            print("本地版本基线已设为 %s" % _norm(args.set_version))
        return 0

    local_version = read_version()
    state = read_state()

    try:
        remote = fetch_latest(args.timeout)
    except Exception as e:  # noqa: BLE001 —— 网络类异常一律走兜底
        msg = "GitHub 查询失败：%s" % e
        if args.json:
            print(json.dumps({"ok": False, "error": msg, "mirror": MIRROR_URL}, ensure_ascii=False))
        else:
            print(msg)
            print("若无法访问 GitHub，可到腾讯文档《版本更新记录》查看最新版本：")
            print("  " + MIRROR_URL)
        return 4

    since_sha = state.get("last_commit", "")
    new_commits = diff_commits(remote.pop("_commits", []), since_sha)

    # 远端没打 tag / 没发 Release 时版本号是 main@<sha>，无法做语义化比较
    # —— 此时只认 commit 水位差，避免「本地 1.0.0 vs 远端 main@xxx」被误判成有更新
    comparable = _vtuple(remote["version"]) != (0,)
    has_ver_update = comparable and newer(remote["version"], local_version)
    has_commit_update = bool(new_commits) and remote.get("commit", "")[:7] != since_sha[:7]
    has_update = has_ver_update or has_commit_update

    payload = {
        "ok": True,
        "has_update": has_update,
        "local_version": local_version,
        "remote_version": remote["version"],
        "remote_name": remote["name"],
        "published_at": remote["published_at"],
        "url": remote["url"],
        "repo": REPO_URL,
        "source": remote["source"],
        "notes": remote["notes"],
        "new_commits": new_commits,
        "mirror": MIRROR_URL,
    }

    if args.mark_seen:
        state.update(
            last_version=remote["version"],
            last_commit=remote.get("commit", ""),
            last_checked=_now(),
        )
        write_state(state)
        payload["marked"] = True

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if has_update else 3

    # 人类可读
    print("仓库：%s" % REPO_URL)
    print("本地基线：%s    远端最新：%s    （来源：%s）" % (local_version, remote["version"], remote["source"] or "-"))
    if remote["published_at"]:
        print("发布时间：%s" % remote["published_at"])
    print("-" * 60)
    if not has_update:
        print("✅ 已是最新，无需更新。")
        return 3

    print("🆕 有新版本：%s → %s" % (local_version, remote["version"]))
    print("更新地址：%s" % remote["url"])
    if remote["notes"]:
        print("\n【发布说明】")
        print(remote["notes"][:4000])
    if new_commits:
        print("\n【新增提交 %d 条】" % len(new_commits))
        for c in new_commits:
            print("  %s  %s  %s" % (c["sha"], (c["date"] or "")[:10], c["message"]))
    print("\n无法访问 GitHub 时，版本记录镜像：%s" % MIRROR_URL)
    return 0


def _now():
    import datetime

    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    sys.exit(main())
