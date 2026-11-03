#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""以磁盘实况对账转码台账

批次中断时 CSV 收尾写不进去，台账会停在「待转码」，实际早已转完；
直接重跑会重复扫描甚至重复编码。这个脚本按文件说话：

  同名 .mkv 存在且视频编码是 hevc   → 已转码
  源文件和成品都不存在               → 源文件缺失
  其它                               → 保持原状态

用法：
  python h265_ledger_check.py --root Z:\\AV --csv Z:\\AV_转码台账.csv [--dry-run]
"""
import argparse
import collections
import csv
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor

OLD_EXT = (".mp4", ".ts", ".avi", ".wmv", ".mov", ".m4v", ".flv", ".rmvb", ".mkv")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=r"Z:\AV")
    ap.add_argument("--csv", default=r"Z:\AV_转码台账.csv")
    ap.add_argument("--ffprobe", default=r"D:\wokecode\h265-tool\bin\ffmpeg\bin\ffprobe.exe")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    def codec(path):
        try:
            r = subprocess.run([a.ffprobe, "-v", "quiet", "-select_streams", "v:0",
                                "-show_entries", "stream=codec_name", "-of", "csv=p=0", path],
                               capture_output=True, text=True, timeout=120)
        except Exception:
            return ""
        return (r.stdout or "").strip().splitlines()[0] if r.stdout.strip() else ""

    def judge(row):
        rel = row["相对路径"]
        src = os.path.join(a.root, rel)
        d, name = os.path.split(src)
        final = os.path.join(d, os.path.splitext(name)[0] + ".mkv")
        has_fin = os.path.exists(final) and os.path.abspath(final) != os.path.abspath(src)
        if has_fin and codec(final) == "hevc":
            return ("已转码", final)
        if not os.path.exists(src):
            return ("源文件缺失", None)
        return (None, None)

    with open(a.csv, encoding="utf-8-sig", newline="") as fh:
        rd = csv.DictReader(fh)
        hdr = rd.fieldnames
        rows = list(rd)

    todo = [r for r in rows if r["状态"] != "已转码"]
    print("待核对 %d 行（全表 %d 行）" % (len(todo), len(rows)))

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        verdicts = list(ex.map(judge, todo))

    changed = 0
    for row, (st, final) in zip(todo, verdicts):
        if not st:
            continue
        old = row["状态"]
        if st == "已转码":
            gb = os.path.getsize(final) / 2 ** 30
            try:
                src_gb = float(row["大小GB"])
            except Exception:
                src_gb = 0
            row["状态"] = "已转码"
            row["转码后GB"] = "%.2f" % gb
            row["压缩率"] = ("%.0f%%" % (100 * gb / src_gb)) if src_gb else ""
            if not row.get("备注"):
                row["备注"] = "对账补录"
        else:
            row["状态"] = "源文件缺失"
            if not row.get("备注"):
                row["备注"] = "源片及其成品均不存在"
        if row["状态"] != old:
            changed += 1
            if changed <= 12:
                print("  %-14s → %-8s %s" % (old, row["状态"], row["相对路径"][:52]))

    print("\n状态变更 %d 行%s" % (changed, "" if not a.dry_run else "（dry-run 未写入）"))
    if a.dry_run or not changed:
        return

    bak = a.csv + ".bak"
    if not os.path.exists(bak):
        shutil.copy2(a.csv, bak)
        print("原台账已备份到 %s" % bak)

    tmp = a.csv + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=hdr, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, a.csv)

    print("对账后状态分布:")
    for k, v in collections.Counter(r["状态"] for r in rows).most_common():
        print("  %-22s %d" % (k, v))


if __name__ == "__main__":
    main()
