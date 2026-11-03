#!/bin/bash
# h265 队列转码（在 NAS 的 ffmpeg 容器内跑）
#
# 用法：
#   h265_queue.sh [-l 清单] [-m 媒体根] [-q 质量] [-d 暂存区]
#   h265_queue.sh                      # 默认读 /media/_h265_queue/list_sel.txt
#
# 设计要点（都是踩坑换来的）：
#   1) 列表走 fd 3，所有 ffmpeg 加 -nostdin —— 否则 ffmpeg 会吞掉列表，每轮只跑 1 个
#   2) flock 单实例 —— 两个进程用 -y 写同一个输出会产出坏文件
#   3) 三段校验：时长 ±1%、分辨率一致、体积必须变小
#   4) 原片不删，同卷 rename 搬到暂存区（删除可能被守卫静默拦截）
#   5) 每完成一条立刻追加进日志，中断也能知道跑到哪
set -u

QDIR=/media/_h265_queue
LIST="$QDIR/list_sel.txt"
ROOT=/media
Q=26
STAGE=""
LOG="$QDIR/progress.log"
FF=/usr/lib/jellyfin-ffmpeg/ffmpeg
FP=/usr/lib/jellyfin-ffmpeg/ffprobe

while [ $# -gt 0 ]; do
  case "$1" in
    -l) LIST="$2"; shift 2 ;;
    -m) ROOT="$2"; shift 2 ;;
    -q) Q="$2"; shift 2 ;;
    -d) STAGE="$2"; shift 2 ;;
    *) echo "未知参数 $1"; exit 2 ;;
  esac
done

mkdir -p "$QDIR" 2>/dev/null
touch "$LOG" 2>/dev/null

# 单实例互斥
exec 9>"$QDIR/.running.lock"
if ! flock -w 86400 9; then
  echo "LOCK_TIMEOUT $(date) 另一个实例还在跑" >> "$LOG"
  exit 1
fi

probe_dur() { "$FP" -v error -show_entries format=duration -of csv=p=0 "$1" 2>/dev/null | head -1; }
probe_res() { "$FP" -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "$1" 2>/dev/null | head -1; }
probe_vc()  { "$FP" -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$1" 2>/dev/null | head -1; }

TOTAL=$(grep -c . "$LIST" 2>/dev/null || echo 0)
echo "===== RUN $(date) 清单=$LIST 共 $TOTAL 条 Q=$Q =====" >> "$LOG"
idx=0

while IFS= read -r rel <&3; do
  [ -z "$rel" ] && continue
  idx=$((idx + 1))

  src="$ROOT/$rel"
  if [ ! -f "$src" ]; then
    printf 'MISS\t%s\n' "$rel" >> "$LOG"
    continue
  fi

  d=$(dirname "$src"); b=$(basename "$src"); stem="${b%.*}"
  final="$d/$stem.mkv"

  # 已经转过就跳过
  if [ -f "$final" ] && [ "$final" != "$src" ] && [ "$(probe_vc "$final")" = "hevc" ]; then
    printf 'EXIST\t%s\n' "$rel" >> "$LOG"
    continue
  fi

  printf 'START\t%s\t%s\t[%d/%d]\n' "$rel" "$(date +%H:%M:%S)" "$idx" "$TOTAL" >> "$LOG"
  out="$d/$stem.hevc.mkv"

  "$FF" -nostdin -hide_banner -loglevel error -i "$src" -map 0 \
      -c:v hevc_qsv -global_quality "$Q" -preset medium \
      -c:a copy -c:s copy -map_metadata 0 -y "$out" 2>>"$QDIR/ffmpeg_err.log"

  # 音轨/字幕不兼容时兜底重试
  if [ ! -s "$out" ]; then
    "$FF" -nostdin -hide_banner -loglevel error -i "$src" -map 0 \
        -c:v hevc_qsv -global_quality "$Q" -preset medium \
        -c:a aac -b:a 384k -y "$out" 2>>"$QDIR/ffmpeg_err.log"
  fi
  if [ ! -s "$out" ]; then
    printf 'FAIL\t%s\n' "$rel" >> "$LOG"
    continue
  fi

  # 三段校验
  od=$(probe_dur "$src"); nd=$(probe_dur "$out")
  or_=$(probe_res "$src"); nr=$(probe_res "$out")
  osz=$(stat -c%s "$src"); nsz=$(stat -c%s "$out")
  ok=1; why=""
  awk -v a="$od" -v b="$nd" 'BEGIN{ if (!(a>0 && b>a*0.99 && b<a*1.01)) exit 1 }' || { ok=0; why="$why 时长"; }
  [ "$or_" = "$nr" ] || { ok=0; why="$why 分辨率"; }
  [ "$nsz" -gt $((osz / 20)) ] || { ok=0; why="$why 过小"; }
  [ "$nsz" -lt "$osz" ] || { ok=0; why="$why 反而变大"; }

  if [ "$ok" != "1" ]; then
    rm -f "$out" 2>/dev/null
    printf 'VERIFY_FAIL\t%s\t%s\n' "$rel" "$why" >> "$LOG"
    continue
  fi

  mv -f "$out" "$final"

  # 原片搬暂存区，不直接删
  if [ -n "$STAGE" ] && [ "$src" != "$final" ]; then
    mkdir -p "$STAGE/$(dirname "$rel")" 2>/dev/null
    if mv -f "$src" "$STAGE/$rel" 2>/dev/null && [ ! -e "$src" ]; then
      :
    else
      printf 'STAGE_FAIL\t%s\n' "$rel" >> "$LOG"
    fi
  fi

  printf 'OK\t%s\t%sMB->%sMB\n' "$rel" "$((osz / 1048576))" "$((nsz / 1048576))" >> "$LOG"
done 3< "$LIST"

echo "ALLDONE $(date) 处理 $idx/$TOTAL" >> "$LOG"
