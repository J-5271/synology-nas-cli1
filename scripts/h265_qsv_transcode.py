#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""h265 / HEVC QSV 并行转码（Intel Quick Sync，默认 Q26）

流程：读台账 → 按视频码率筛选 → N 路并行 → 三段校验 → 原片搬暂存区 → 回写台账

用法：
  python h265_qsv_transcode.py --root Z:\\AV --csv Z:\\AV_转码台账.csv \\
         --stage Z:\\_原片待删 --min-bitrate 6 --workers 2
  python h265_qsv_transcode.py --list split_local.txt --workers 2
  python h265_qsv_transcode.py --min-bitrate 6 --dry-run

设计要点（都是实测踩出来的）：
  1) 三段校验：时长 ±1%、分辨率一致、体积必须变小（防「越压越大」）
  2) 原片不删，同卷 rename 搬到暂存区；搬完立刻 exists() 复核（删除可能被守卫静默拦截）
  3) 半成品临时文件也走 rename，不留垃圾
  4) 每完成一条立刻追加 jsonl，中断可追溯
  5) 已存在 hevc 成品直接跳过，重复跑不会重复编码
"""
import argparse
import csv
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

_lock = threading.Lock()


def log(msg):
    with _lock:
        print(msg, flush=True)


class Coder:
    def __init__(self, root, csv_path, stage, bindir, q):
        self.root = root
        self.csv_path = csv_path
        self.stage = stage
        self.ffmpeg = os.path.join(bindir, "ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        self.ffprobe = os.path.join(bindir, "ffprobe.exe" if os.name == "nt" else "ffprobe")
        self.q = q
        self.results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

    # ---------- 探测 ----------
    def probe(self, path):
        r = subprocess.run([self.ffprobe, "-v", "quiet", "-print_format", "json",
                            "-show_streams", "-show_format", path],
                           capture_output=True, text=True)
        try:
            j = json.loads(r.stdout or "{}")
        except Exception:
            return None
        v = [s for s in j.get("streams", []) if s.get("codec_type") == "video"]
        if not v:
            return None
        try:
            dur = float(j.get("format", {}).get("duration") or 0)
        except Exception:
            dur = 0.0
        return {"w": v[0].get("width"), "h": v[0].get("height"),
                "dur": dur, "vcodec": v[0].get("codec_name", "")}

    # ---------- 编码（三级兜底） ----------
    def encode(self, src, out):
        base = [self.ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
                "-i", src, "-map", "0",
                "-c:v", "hevc_qsv", "-global_quality", str(self.q), "-preset", "medium"]
        tries = [
            (["-c:a", "copy", "-c:s", "copy"], "copy"),
            (["-c:a", "aac", "-b:a", "512k", "-c:s", "srt"], "aac512+srt"),
            (["-c:a", "aac", "-b:a", "512k", "-sn"], "aac512+无字幕"),
        ]
        err = ""
        for extra, tag in tries:
            cmd = base + extra + ["-map_metadata", "0", "-y", out]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 0:
                return True, tag
            err = (r.stderr or "")[-400:]
            if os.path.exists(out):
                self.discard(out, os.path.basename(out))
        return False, err

    def verify(self, src, out):
        a, b = self.probe(src), self.probe(out)
        if not a or not b:
            return False, "探测失败"
        if (a["w"], a["h"]) != (b["w"], b["h"]):
            return False, "分辨率 %sx%s→%sx%s" % (a["w"], a["h"], b["w"], b["h"])
        if a["dur"] > 0 and abs(b["dur"] - a["dur"]) > max(2.0, a["dur"] * 0.01):
            return False, "时长 %.0f→%.0f" % (a["dur"], b["dur"])
        so, sn = os.path.getsize(src), os.path.getsize(out)
        if sn < so * 0.02:
            return False, "体积异常偏小"
        if sn >= so:
            return False, "反而变大"
        return True, ""

    # ---------- 原片搬运 ----------
    def stage_original(self, src, rel):
        if not self.stage:
            return True
        dst = os.path.join(self.stage, rel)
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.exists(dst):
                base, ext = os.path.splitext(dst)
                dst = "%s.%d%s" % (base, int(time.time()), ext)
            os.replace(src, dst)
        except Exception as e:
            log("  ! 原片移动失败 %s: %s" % (rel, e))
            return False
        if os.path.exists(src):
            log("  ! 原片移动后仍存在 %s" % rel)
            return False
        return True

    def discard(self, path, name):
        if not os.path.exists(path):
            return
        if self.stage:
            dst = os.path.join(self.stage, "_tmp", name)
            try:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                os.replace(path, dst)
                return
            except Exception:
                pass
        try:
            os.remove(path)
        except Exception:
            pass

    # ---------- 单条处理 ----------
    def handle(self, row):
        rel = row["相对路径"]
        src = os.path.join(self.root, rel)
        d, name = os.path.split(src)
        stem = os.path.splitext(name)[0]
        final = os.path.join(d, stem + ".mkv")

        if not os.path.exists(src):
            if os.path.exists(final) and os.path.abspath(final) != os.path.abspath(src):
                p = self.probe(final)
                if p and p["vcodec"] == "hevc":
                    return {"rel": rel, "status": "已转码",
                            "old": 0, "new": round(os.path.getsize(final) / 2 ** 30, 2),
                            "ratio": "", "note": "原片已归档"}
            return {"rel": rel, "status": "文件不存在"}

        old = os.path.getsize(src)
        old_gb = old / 2 ** 30

        if os.path.exists(final) and os.path.abspath(final) != os.path.abspath(src):
            p = self.probe(final)
            if p and p["vcodec"] == "hevc":
                return {"rel": rel, "status": "跳过_已存在"}

        tmp = os.path.join(d, stem + ".hevc.qsv-tmp.mkv")
        log("  开始 %s  %.2f GB  %s min" % (rel, old_gb, row.get("时长分钟", "")))
        t0 = time.time()
        ok, tag = self.encode(src, tmp)
        cost = (time.time() - t0) / 60
        if not ok:
            self.discard(tmp, os.path.basename(tmp))
            return {"rel": rel, "status": "失败", "note": str(tag)[:150], "min": round(cost, 1)}

        ok, why = self.verify(src, tmp)
        if not ok:
            self.discard(tmp, os.path.basename(tmp))
            return {"rel": rel, "status": "校验失败", "note": why, "min": round(cost, 1)}

        new = os.path.getsize(tmp)
        os.replace(tmp, final)
        if os.path.abspath(final) != os.path.abspath(src):
            self.stage_original(src, rel)

        new_gb = new / 2 ** 30
        log("  完成 %s  %.2f → %.2f GB (%d%%) %.0f min [%s]" %
            (rel, old_gb, new_gb, 100 * new_gb / old_gb if old_gb else 0, cost, tag))
        return {"rel": rel, "status": "已转码", "old": round(old_gb, 2),
                "new": round(new_gb, 2), "ratio": "%d%%" % (100 * new_gb / old_gb if old_gb else 0),
                "note": tag, "min": round(cost, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=r"Z:\AV", help="媒体根目录")
    ap.add_argument("--csv", default=r"Z:\AV_转码台账.csv", help="台账 CSV")
    ap.add_argument("--stage", default=r"Z:\_原片待删", help="原片暂存区，留空表示不搬")
    ap.add_argument("--bindir", default=r"D:\wokecode\h265-tool\bin\ffmpeg\bin")
    ap.add_argument("--q", type=int, default=26, help="QSV 质量值，26 ≈ x265 CRF26")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--min-bitrate", type=float, default=10.0)
    ap.add_argument("--max-bitrate", type=float, default=1e9)
    ap.add_argument("--list", help="只处理该清单里的相对路径（每行一条），忽略码率区间")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    with open(a.csv, encoding="utf-8-sig", newline="") as fh:
        rd = csv.DictReader(fh)
        hdr = rd.fieldnames
        rows = list(rd)

    def num(r, k):
        try:
            return float(r[k])
        except Exception:
            return 0.0

    if a.list:
        want = []
        with open(a.list, encoding="utf-8-sig") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    want.append(line.replace("/", "\\"))
        wset = set(want)
        order = {p: i for i, p in enumerate(want)}
        pool = [r for r in rows if r["相对路径"].replace("/", "\\") in wset
                and r["状态"] == "待转码"]
        pool.sort(key=lambda r: order.get(r["相对路径"].replace("/", "\\"), 99999))
    else:
        pool = [r for r in rows if r["状态"] == "待转码"
                and a.min_bitrate <= num(r, "视频码率Mbps") < a.max_bitrate]
        pool.sort(key=lambda r: -num(r, "视频码率Mbps"))

    todo = pool[: a.limit]
    print("待处理池 %d 个，本次取 %d 个，%d 路并行，Q%d" % (len(pool), len(todo), a.workers, a.q))
    for r in todo[:10]:
        print("  %7sGB %6sM %6smin  %s" %
              (r["大小GB"], r["视频码率Mbps"], r["时长分钟"], r["相对路径"]))
    if len(todo) > 10:
        print("  ... 其余 %d 个" % (len(todo) - 10))
    if a.dry_run or not todo:
        return

    coder = Coder(a.root, a.csv, a.stage, a.bindir, a.q)
    os.makedirs(coder.results_dir, exist_ok=True)
    jsonl = os.path.join(coder.results_dir, "h265_progress.jsonl")
    t0 = time.time()
    results = []

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(coder.handle, r): r for r in todo}
        for f in as_completed(futs):
            try:
                res = f.result()
            except Exception as e:
                res = {"rel": futs[f]["相对路径"], "status": "异常", "note": str(e)[:120]}
            results.append(res)
            with _lock:
                with open(jsonl, "a", encoding="utf-8") as jf:
                    jf.write(json.dumps(res, ensure_ascii=False) + "\n")
            log("  [%d/%d] %s  %s" % (len(results), len(todo), res["status"], res.get("rel", "")))

    by_rel = {r["rel"]: r for r in results}
    for row in rows:
        res = by_rel.get(row["相对路径"])
        if not res:
            continue
        row["状态"] = res["status"]
        if res["status"] == "已转码":
            row["转码后GB"] = res.get("new", "")
            row["压缩率"] = res.get("ratio", "")
            row["备注"] = "QSV Q%d %s; 耗时%sin" % (a.q, res.get("note", ""), res.get("min", 0))
        elif res.get("note"):
            row["备注"] = res["note"]

    tmp_csv = a.csv + ".tmp"
    with open(tmp_csv, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=hdr, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp_csv, a.csv)

    n_ok = sum(1 for r in results if r["status"] == "已转码")
    so = sum(r.get("old", 0) for r in results)
    sn = sum(r.get("new", 0) for r in results)
    print("\n完成 %d/%d，%.1f GB → %.1f GB，总耗时 %.2f h" %
          (n_ok, len(results), so, sn, (time.time() - t0) / 3600))


if __name__ == "__main__":
    main()
