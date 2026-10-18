#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
管理 Synology 共享文件夹的 NFS 导出规则（读 + 写），走 DSM Web API。

为什么需要它：
  * `/etc/exports` 在 DSM 7 上普通管理员读不到，而且它**不是权威来源**；
    「这个共享到底有没有 NFS 导出」要看 DSM 共享文件夹的 NFS 权限设置。
  * 该设置只有 `load` / `save` 两个方法，**没有 add / delete**。
    改规则 = 读全量 → 改数组 → 整体 save 回去。手工做很容易把别人的规则覆盖掉。

API 契约（DSM 7.4.1-90080 实测）：
  api      SYNO.Core.FileServ.NFS.SharePrivilege
  version  1
  load     share_name=<共享文件夹名>            -> data.rule[]  （空数组 = 未导出）
  save     share_name=<共享文件夹名>
           rule=<JSON 数组的字符串>             ← 参数名是 rule，不是 rules
  注意：写操作走 POST（rule JSON 较长，GET 容易超长）。

认证与其它脚本一致，凭据只走环境变量：
  DSM_HOST / DSM_ACCOUNT / DSM_PASSWORD（可选 DSM_VERIFY_SSL=0）

用法：
  nas_nfs.py list                                  # 只读：列出所有共享的 NFS 规则
  nas_nfs.py list --share <共享名>                  # 只读：只看一个共享
  nas_nfs.py show --share <共享名>                  # 只读：打印完整 rule JSON
  nas_nfs.py set  --share <共享名> --client <网段> --yes
  nas_nfs.py revert --share <共享名> --yes          # 清空该共享的规则（= 未导出）

退出码：0 成功 / 1 出错 / 2 用法错误或守卫拦截（写操作没加 --yes）/ 3 无变化
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dsm_api import DSM, skill_version  # noqa: E402

API = "SYNO.Core.FileServ.NFS.SharePrivilege"
SHARE_API = "SYNO.Core.Share"

# 与 DSM 界面一致的默认值；root_squash="root" 即导出选项里的 no_root_squash
DEFAULT_RULE = {
    "async": True,
    "client": "",
    "crossmnt": True,
    "insecure": True,
    "privilege": "rw",
    "root_squash": "root",
    "security_flavor": {
        "kerberos": False,
        "kerberos_integrity": False,
        "kerberos_privacy": False,
        "sys": True,
    },
}


def _ok(resp):
    return isinstance(resp, dict) and resp.get("success")


def _err(resp):
    return json.dumps(resp, ensure_ascii=False) if resp else "无响应"


def load_rule(dsm, share):
    """返回该共享当前的规则数组（空数组 = 未导出）。"""
    r = dsm.call(API, "load", 1, {"share_name": share})
    if not _ok(r):
        sys.exit(f"[ERROR] load {share} 失败：{_err(r)}")
    data = r.get("data") or {}
    rule = data.get("rule")
    if rule is None:
        # 防御：不同 DSM 版本字段名可能不同，回退找唯一的 list 字段
        cands = [v for k, v in data.items() if isinstance(v, list)]
        rule = cands[0] if len(cands) == 1 else []
    return rule


def save_rule(dsm, share, rules):
    """整体覆盖 save。参数名固定为 rule（实测：写错名字不报错、也不生效）。"""
    payload = json.dumps(rules, ensure_ascii=False)
    r = dsm.call(API, "save", 1, {"share_name": share, "rule": payload}, post=True)
    if not _ok(r):
        # 个别版本只吃 GET
        r = dsm.call(API, "save", 1, {"share_name": share, "rule": payload})
    return r


def list_shares(dsm):
    r = dsm.call(SHARE_API, "list", 1, {"only_visible": "false"})
    if not _ok(r):
        return []
    return [s.get("name") for s in (r["data"].get("shares") or []) if s.get("name")]


def fmt_rule(rule):
    client = rule.get("client", "?")
    priv = rule.get("privilege", "?")
    rs = rule.get("root_squash", "?")
    flags = []
    if rule.get("async"):
        flags.append("async")
    if rule.get("insecure"):
        flags.append("insecure")
    if rule.get("crossmnt"):
        flags.append("crossmnt")
    sf = rule.get("security_flavor") or {}
    sec = ",".join(k for k, v in sf.items() if v) or "-"
    return f"{client:<24} {priv:<3} root_squash={rs:<6} sec={sec:<22} {' '.join(flags)}"


def cmd_list(dsm, args):
    shares = [args.share] if args.share else list_shares(dsm)
    if not shares:
        print("[WARN] 没取到共享文件夹列表（权限不足？用 --share 指定）", file=sys.stderr)
        return 1
    exported = 0
    for name in shares:
        rules = load_rule(dsm, name)
        if rules:
            exported += 1
            print(f"\n== {name}  （{len(rules)} 条导出规则）")
            for r in rules:
                print("   ", fmt_rule(r))
        elif args.share or args.all:
            print(f"\n== {name}  （未导出 / rule=[]）")
    print(f"\n合计：{len(shares)} 个共享，其中 {exported} 个有 NFS 导出规则。")
    print("复核（需 sudo）：exportfs -v")
    return 0


def cmd_show(dsm, args):
    rules = load_rule(dsm, args.share)
    print(json.dumps(rules, ensure_ascii=False, indent=1))
    return 0


def cmd_set(dsm, args):
    if not args.yes:
        print("[BLOCKED] 这是变更操作，必须在确认后追加 --yes 才会执行。", file=sys.stderr)
        print("          影响：立刻改变该共享对指定客户端的 NFS 访问权限。", file=sys.stderr)
        return 2

    old = load_rule(dsm, args.share)
    rule = json.loads(json.dumps(DEFAULT_RULE))  # deep copy
    rule["client"] = args.client
    rule["privilege"] = args.privilege
    rule["root_squash"] = args.root_squash
    rule["async"] = not args.sync
    rule["crossmnt"] = not args.no_crossmnt
    rule["insecure"] = not args.secure_ports
    if args.squash_uid is not None:
        rule["anonuid"] = args.squash_uid
    if args.squash_gid is not None:
        rule["anongid"] = args.squash_gid

    # 已存在同 client 的规则就替换，否则追加 —— 避免重复条目
    new = [r for r in old if r.get("client") != args.client] + [rule]
    if new == old:
        print("[SKIP] 规则无变化（返回 3）")
        return 3

    print(f"将把 {args.share} 的 NFS 规则设为：")
    for r in new:
        print("   ", fmt_rule(r))
    r = save_rule(dsm, args.share, new)
    if not _ok(r):
        print(f"[ERROR] save 失败：{_err(r)}", file=sys.stderr)
        return 1
    back = load_rule(dsm, args.share)
    print("\n已写入，复核：")
    for x in back:
        print("   ", fmt_rule(x))
    print("\n提示：NAS 侧再用 `sudo exportfs -v` 复核一次；"
          "DSM 重启后设置保留（这是持久配置）。")
    return 0


def cmd_revert(dsm, args):
    if not args.yes:
        print("[BLOCKED] 这会清空该共享的全部 NFS 导出规则，必须加 --yes。", file=sys.stderr)
        return 2
    old = load_rule(dsm, args.share)
    if not old:
        print("[SKIP] 该共享本来就没有 NFS 导出规则（返回 3）")
        return 3
    if args.client:
        new = [r for r in old if r.get("client") != args.client]
    else:
        new = []
    if new == old:
        print(f"[SKIP] 没有 client={args.client} 的规则（返回 3）")
        return 3
    print(f"将把 {args.share} 的 NFS 规则从 {len(old)} 条改为 {len(new)} 条：")
    for r in new:
        print("   ", fmt_rule(r))
    r = save_rule(dsm, args.share, new)
    if not _ok(r):
        print(f"[ERROR] save 失败：{_err(r)}", file=sys.stderr)
        return 1
    print("\n已回滚。复核（NAS 侧，需 sudo）：exportfs -v")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="Synology 共享文件夹的 NFS 导出规则管理（默认只读）")
    ap.add_argument("--version", "-V", action="store_true")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("list", help="只读：列出各共享的 NFS 导出规则")
    p.add_argument("--share", help="只查这个共享")
    p.add_argument("--all", action="store_true", help="连未导出的也打印出来")

    p = sub.add_parser("show", help="只读：打印某个共享的完整 rule JSON")
    p.add_argument("--share", required=True)

    p = sub.add_parser("set", help="变更：新增/替换一条导出规则")
    p.add_argument("--share", required=True)
    p.add_argument("--client", required=True,
                   help="客户端 IP 或网段；能用具体地址就别写 *")
    p.add_argument("--privilege", default="rw", choices=["rw", "ro"])
    p.add_argument("--root-squash", default="root", choices=["root", "nobody"],
                   help="root = 导出选项 no_root_squash")
    p.add_argument("--sync", action="store_true", help="去掉 async（默认 async）")
    p.add_argument("--secure-ports", action="store_true",
                   help="去掉 insecure（默认 insecure，Windows 客户端需要）")
    p.add_argument("--no-crossmnt", action="store_true")
    p.add_argument("--squash-uid", type=int, help="anonuid")
    p.add_argument("--squash-gid", type=int, help="anongid")
    p.add_argument("--yes", action="store_true", help="确认执行变更")

    p = sub.add_parser("revert", help="变更：清空导出规则（或只删某 client）")
    p.add_argument("--share", required=True)
    p.add_argument("--client", help="只删除这个 client 的规则；不给则清空全部")
    p.add_argument("--yes", action="store_true", help="确认执行变更")

    args = ap.parse_args()
    if args.version:
        print(f"synology-nas-cli v{skill_version()}")
        return 0
    if not args.cmd:
        ap.print_help()
        return 2

    dsm = DSM()
    if not dsm.login():
        return 1
    try:
        return {"list": cmd_list, "show": cmd_show,
                "set": cmd_set, "revert": cmd_revert}[args.cmd](dsm, args)
    finally:
        dsm.logout()


if __name__ == "__main__":
    sys.exit(main())
