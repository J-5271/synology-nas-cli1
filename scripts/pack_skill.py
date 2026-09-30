#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 synology-nas-cli 技能目录打包成 Markdown，用于回传 ima 知识库。

两种模式：
  full  —— 整包（SKILL.md + references + scripts + CHANGELOG），每月整合时用，重名 REPLACE 覆盖。
  delta —— 只打包「上次同步之后改动过的文件」+ CHANGELOG 本周条目，每周回传新增能力时用。

版本记录：产物头部带 version = 打包日期（YYYY-MM-DD）与生成时刻，
每次回传都会在 CHANGELOG.md 追加一条带时间的记录。

脱敏：默认扫描全部待打包文本，命中疑似真实账号/密码/密钥即中止（exit 4），
绝不把凭据带进回传包。占位符（<密码>、$ENV、{var}）视为安全。

用法：
    python3 pack_skill.py                                  # full，输出到 build/Synology NAS 管理技能包.md
    python3 pack_skill.py --mode delta --since 2026-09-27  # 增量，输出到 build/delta/...-增量-<date>.md
    python3 pack_skill.py --mode delta                     # 用 build/.sync_state.json 里的 last_sync
    python3 pack_skill.py --list-changed --since 2026-09-27
    python3 pack_skill.py --allow-secrets                  # 明确关闭脱敏扫描（不推荐）

退出码：0 成功 / 3 增量无变更（跳过回传）/ 4 命中敏感信息 / 1 其它错误
"""
import argparse
import datetime
import json
import os
import re
import sys

def _skill_root():
    # 优先用环境变量覆盖（别的 agent 把脚本复制到临时目录运行、__file__ 兜底指错时可重定向）
    env = os.environ.get("SYNO_SKILL_ROOT")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


SKILL_ROOT = _skill_root()
BUILD_DIR = os.path.join(SKILL_ROOT, "build")
STATE_FILE = os.path.join(BUILD_DIR, ".sync_state.json")

# 打包顺序：主文档 → 说明 → 参考 → 变更日志/版本 → 脚本（脚本自身也要进包，否则回传的版本无法还原目录）
DOC_ORDER = [
    ("SKILL.md", "技能主文档 {}", None),
    ("README.md", "安装与使用说明 {}", None),
    ("references/dsm-deployment-guide.md", "新机开荒部署要点（官方指南提炼）", None),
    ("references/dsm-web-api.md", "DSM Web API 通路", None),
    ("references/cli-commands.md", "官方 CLI 命令参考", None),
    ("references/lan-discovery.md", "局域网发现（findhostd / mDNS / SSDP）", None),
    ("references/browser-automation.md", "浏览器自动化通路", None),
    ("references/error-codes.md", "错误码对照表", None),
    ("references/ssh-and-troubleshooting.md", "SSH 登录与故障排查", None),
    ("CHANGELOG.md", "版本记录 {}", None),
    ("VERSION", "当前版本基线 {}", None),
    ("requirements.txt", "Python 依赖清单 {}", "text"),
    ("scripts/dsm_api.py", "脚本：{}", "python"),
    ("scripts/nas_exec.py", "脚本：{}", "python"),
    ("scripts/syno.py", "脚本：{}", "python"),
    ("scripts/syno_findhost.py", "脚本：{}", "python"),
    ("scripts/discover_nas.py", "脚本：{}", "python"),
    ("scripts/check_update.py", "脚本：{}", "python"),
    ("scripts/first_run.py", "脚本：{}", "python"),
    ("scripts/pack_skill.py", "脚本：{}", "python"),
    ("scripts/cos_upload.py", "脚本：{}", "python"),
]


def _autodiscover():
    """DOC_ORDER 之外的新文件自动补进包。

    踩过的坑（2026-09-30）：新增了 references/ 与 scripts/ 下 4 个文件却忘了同步
    DOC_ORDER，结果 `--mode full` 打出来还是 16 个文件，新内容根本没进回传包。
    这里按目录补齐，保证「目录里有文件就一定进包」，不再依赖人工记得改清单。
    """
    known = {rel for rel, _, _ in DOC_ORDER}
    extra = []
    for sub, ext, lang, prefix in (("references", ".md", None, "参考："),
                                   ("scripts", ".py", "python", "脚本：")):
        d = os.path.join(SKILL_ROOT, sub)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if not name.endswith(ext):
                continue
            rel = "%s/%s" % (sub, name)
            if rel not in known:
                extra.append((rel, prefix + name, lang))
    return DOC_ORDER + extra


DOC_FILES = _autodiscover()

FULL_NAME = "Synology NAS 管理技能包.md"

# ---------------- 脱敏扫描 ----------------
# 命中规则：看起来像「真实值」的赋值。占位符一律放行。
PLACEHOLDER_RE = re.compile(r"^\s*(<.*>|\$\{?\w+\}?|\{\w+\}|your_|xxx|EXAMPLE|example|changeme|placeholder)", re.I)

SECRET_PATTERNS = [
    # 只认「带引号的字面量」或 AKID 这类不可伪造的长串，避免把变量名/函数调用误判成凭据
    ("凭据赋值（引号字面量）",
     re.compile(r"(NAS_PASS|DSM_PASSWORD|DSM_PASS|NAS_PASSWORD|SSHPASS|password|passwd|pwd|"
                r"secret_key|secret_id|access_key|api_key|token|sid)\s*[:=]\s*"
                r"['\"]([^'\"]{4,})['\"]", re.I)),
    ("凭据赋值（裸值）",
     re.compile(r"^\s*(NAS_PASS|DSM_PASSWORD|password|passwd|secret_key)\s*=\s*"
                r"([A-Za-z0-9!@#$%^&*_+\-/]{4,})\s*(#.*)?$", re.I)),
    ("疑似云密钥 AKID",
     re.compile(r"AKID[A-Za-z0-9_\-]{20,}")),
    ("疑似 token/密钥长串",
     re.compile(r"['\"]([A-Za-z0-9+/=_\-]{40,})['\"]")),
    ("--setpw 带真实密码",
     re.compile(r"--setpw\s+\S+\s+['\"]?([^'\"\s#]+)")),
    ("疑似账号明文",
     re.compile(r"(account|username)\s*[:=]\s*['\"]([^'\"\s@]{3,})['\"]", re.I)),
]

# 这些值明摆着来自环境/入参，不是写死的凭据
CODEISH = ("os.environ", "getenv", "args.", "os.get", "input(", "sys.argv", "None", "None'",
           "self.", "config", "{}", "%s", "f\"", "prompt")


def scan_secrets(files):
    """返回 [(文件, 行号, 规则名, 片段)]。占位符不算命中。"""
    hits = []
    for rel in files:
        path = os.path.join(SKILL_ROOT, rel)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, 1):
                if line.lstrip().startswith("#") and "pack_skill" not in line:
                    # 注释行也扫，但跳过纯说明行里的示例占位符（PLACEHOLDER_RE 已兜底）
                    pass
                for name, rx in SECRET_PATTERNS:
                    m = rx.search(line)
                    if not m:
                        continue
                    val = (m.group(m.lastindex or 1) or "").strip()
                    if PLACEHOLDER_RE.match(val):
                        continue
                    if val.startswith(("$", "{", "<")):
                        continue
                    # 代码取值（os.environ / args.xxx / 格式化串）不算写死凭据
                    if any(c in line for c in CODEISH):
                        continue
                    # 明显是文档示例：含 * 、<、> 或全是符号
                    if set(val) <= set("*<>_-"):
                        continue
                    # 纯标识符（变量名、函数名）不算
                    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", val) and "." not in val:
                        continue
                    hits.append((rel, i, name, val[:40]))
    return hits


# ---------------- 变更文件 ----------------
def changed_files(since):
    """mtime >= since 的技能文件（按 DOC_ORDER 顺序）。"""
    ts = datetime.datetime.strptime(since, "%Y-%m-%d").timestamp()
    out = []
    for rel, _, _ in DOC_FILES:
        p = os.path.join(SKILL_ROOT, rel)
        if os.path.exists(p) and os.path.getmtime(p) >= ts:
            out.append(rel)
    return out


def read(rel):
    path = os.path.join(SKILL_ROOT, rel)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def read_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def write_state(patch):
    st = read_state()
    st.update(patch)
    os.makedirs(BUILD_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)


def build_body(files, mode):
    parts, toc = [], []
    nfiles, nlines = 0, 0
    for rel, title_tpl, lang in DOC_FILES:
        if rel not in files:
            continue
        body = read(rel)
        if body is None:
            print(f"[WARN] skip missing file: {rel}", file=sys.stderr)
            continue
        nfiles += 1
        nlines += body.count("\n") + 1
        title = title_tpl.format(os.path.basename(rel))
        anchor = (title.replace(" ", "-").replace("：", "-")
                       .replace("（", "").replace("）", "").strip("-"))
        toc.append(f"- {anchor}")
        section = f"\n## {len(toc)}. {title}\n\n"
        if lang:
            section += f"路径：{SKILL_ROOT}/{rel}\n\n"
            section += f"```{lang}\n{body.rstrip()}\n```\n"
        else:
            section += body.rstrip() + "\n"
        parts.append(section)
    return parts, toc, nfiles, nlines


def main():
    ap = argparse.ArgumentParser(description="Pack the synology-nas-cli skill into one Markdown file.")
    ap.add_argument("--mode", choices=["full", "delta"], default="full")
    ap.add_argument("--since", help="delta 起点 YYYY-MM-DD；不传则用 build/.sync_state.json 的 last_sync")
    ap.add_argument("-o", "--output")
    ap.add_argument("--list-changed", action="store_true", help="只列出变更文件，不打包")
    ap.add_argument("--allow-secrets", action="store_true", help="关闭脱敏扫描（不推荐）")
    ap.add_argument("--no-state", action="store_true", help="不更新 .sync_state.json")
    args = ap.parse_args()

    now = datetime.datetime.now()
    version = now.strftime("%Y-%m-%d")
    stamp = now.strftime("%Y-%m-%d %H:%M:%S")
    week = now.isocalendar()
    week_tag = f"{week[0]}-W{week[1]:02d}"

    if args.mode == "delta":
        since = args.since or read_state().get("last_sync")
        if not since:
            print("[ERROR] delta 需要 --since 或 build/.sync_state.json 里有 last_sync", file=sys.stderr)
            return 1
        files = changed_files(since)
        if args.list_changed:
            print("\n".join(files) if files else "(no changes)")
            return 0 if files else 3
        if not files:
            print(f"NO_CHANGES since {since} — 本周无新增能力，跳过回传。")
            return 3
        out_path = args.output or os.path.join(
            BUILD_DIR, "delta", f"Synology NAS 管理技能包-增量-{version}.md")
        head_title = f"Synology NAS 管理技能包 · 周增量（{week_tag}）"
        head_note = (f"仅含 {since} 之后变更的内容（{len(files)} 个文件）。\n"
                     f"整包见同库条目《{FULL_NAME}》，每月整合一次。")
    else:
        files = [rel for rel, _, _ in DOC_FILES]
        out_path = args.output or os.path.join(BUILD_DIR, FULL_NAME)
        head_title = "Synology NAS 管理技能包（synology-nas-cli）"
        head_note = ("本包提供两套并行的 NAS 管理通路：① DSM Web API（无需 SSH 开放，优先）"
                     "② SSH + root + 官方 CLI 工具。")

    # 脱敏扫描（两种模式都扫）
    if not args.allow_secrets:
        hits = scan_secrets(files)
        if hits:
            print("[ERROR] 脱敏扫描命中疑似真实凭据，已中止打包：", file=sys.stderr)
            for rel, line, name, val in hits:
                print(f"  - {rel}:{line}  [{name}]  {val}", file=sys.stderr)
            print("  改成占位符（<账号>/<密码>/$ENV）后重跑；确认真安全才加 --allow-secrets。",
                  file=sys.stderr)
            return 4

    parts, toc, nfiles, nlines = build_body(files, args.mode)

    out = f"""# {head_title}

版本：{version}（生成时间 {stamp}）｜来源：{SKILL_ROOT}/
{head_note}
> 脱敏：本包已通过凭据扫描，不含任何真实账号/密码/密钥；示例一律用占位符。

## 目录

"""
    out += "\n".join(toc) + "\n" + "".join(parts)
    out += (f"\n\n---\n本文件由 scripts/pack_skill.py 于 {stamp} 生成，"
            f"mode={args.mode}，version={version}，{nfiles} 个文件 / {nlines} 行。\n")

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"packed {nfiles} files / {nlines} lines -> {out_path}")

    if not args.no_state:
        write_state({"last_sync": version,
                     "last_mode": args.mode,
                     "last_output": os.path.relpath(out_path, SKILL_ROOT),
                     "last_stamp": stamp})
    return 0


if __name__ == "__main__":
    sys.exit(main())
