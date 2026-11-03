#!/usr/bin/env bash
# peach_pull.sh —— 国内环境拉 Docker Hub 镜像的可续传封装
#
# 解决三个真实痛点（DSM 7.4.1 实测）：
#   1. registry-1.docker.io 直连超时 / DNS 被投毒 → 自动切国内镜像源
#   2. 大镜像拉一半断掉 → 循环重试，已完成的层会被复用，不会从头再来
#   3. 非 TTY 下 docker pull 只在**状态变化**时打印，日志长时间不动是正常的
#      → 本脚本不按日志大小判停滞，只看进程退出码 + 镜像是否真的落地
#
# 用法：
#   ./peach_pull.sh                                   # 默认拉 longmeidao/peach 的最新发布标签
#   ./peach_pull.sh --image longmeidao/peach --tag 0.50.0
#   ./peach_pull.sh --src docker.1ms.run --tries 8
#
# 退出码：0 成功；1 全部源/次数都用尽
set -uo pipefail

IMAGE="longmeidao/peach"
TAG="0.50.0"
SRCS="docker.1ms.run docker.xuanyuan.me docker.m.daocloud.io"
TRIES=3
PER_TIMEOUT=1200

while [ $# -gt 0 ]; do
  case "$1" in
    --image) IMAGE="$2"; shift 2 ;;
    --tag)   TAG="$2"; shift 2 ;;
    --src)   SRCS="$2"; shift 2 ;;
    --tries) TRIES="$2"; shift 2 ;;
    --timeout) PER_TIMEOUT="$2"; shift 2 ;;
    -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

command -v docker >/dev/null 2>&1 || { echo "没有 docker 命令" >&2; exit 2; }

have(){ docker images --format '{{.Repository}}:{{.Tag}}' | grep -qx "$1"; }

# 0) 先做一次连通性判断，把「被墙」和「镜像不存在」分开
echo "== 连通性自检 =="
code=$(curl -sS -m 8 -o /dev/null -w '%{http_code}' https://registry-1.docker.io/v2/ 2>/dev/null || echo 000)
case "$code" in
  401) echo "  registry-1.docker.io 可达（401 = 正常鉴权挑战），先试直连" ;;
  000) echo "  registry-1.docker.io 不可达 —— 大概率 DNS 被投毒 / 被墙，直接走镜像源" ;;
  403) echo "  registry-1.docker.io 403 —— 有出口但被限流，优先走镜像源" ;;
  *)   echo "  registry-1.docker.io 返回 $code，按不可用处理" ;;
esac

TARGETS="$SRCS"
[ "$code" = "401" ] && TARGETS="docker.io $SRCS"

for attempt in $(seq 1 "$TRIES"); do
  for src in $TARGETS; do
    if [ "$src" = "docker.io" ]; then
      full="$IMAGE:$TAG"
    else
      full="$src/$IMAGE:$TAG"
    fi
    echo "== [第 $attempt/$TRIES 轮] 拉取 $full =="
    # 关键：不判断「日志不动」，只等进程退出
    timeout "$PER_TIMEOUT" docker pull --platform linux/amd64 "$full"
    rc=$?
    if have "$full"; then
      echo "== 成功：$full（退出码 $rc）=="
      docker tag "$full" "$IMAGE:$TAG" 2>/dev/null || true
      docker images | grep -F "$IMAGE" || true
      exit 0
    fi
    echo "  未成功（退出码 $rc），换下一个源"
  done
  [ "$attempt" -lt "$TRIES" ] && { echo "== 本轮全失败，10 秒后重试（已完成的层会复用）=="; sleep 10; }
done

cat >&2 <<'MSG'
== 全部失败 ==
排查顺序：
  1. curl -sS -o /dev/null -w '%{http_code}\n' https://registry-1.docker.io/v2/
     回 000 → 出口问题；回 31.13.x.x 之类的解析结果 → DNS 被投毒，只能走镜像源
  2. 确认 tag 真的存在。官方仓库只推版本号与 edge，**没有 latest**：
     https://hub.docker.com/r/longmeidao/peach/tags
  3. 注意 /v2/.../manifests/<tag> 返回 401 是正常鉴权挑战，不代表 tag 不存在
MSG
exit 1
