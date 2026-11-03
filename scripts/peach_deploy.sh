#!/bin/bash
# Peach 媒体库一键部署（群晖 DSM 7.x / Docker）
# 用法：
#   ./peach_deploy.sh --media /volume1/学习资料/AV --data /volume2/peach-data \
#                     --uid 1026 --gid 100 --port 8900 --image longmeidao/peach:0.50.0
# 说明：
#   1) 官方只推版本号与 edge 标签，没有 latest，拉取前必须写清 tag
#   2) 容器按 UID 1000 设计，DSM 没有这个账号，必须用 --user 覆盖成真实 uid
#   3) 媒体只读挂载，/data 独立持久化目录
set -u

MEDIA="/volume1/学习资料/AV"
DATA="/volume2/peach-data"
UID_N=1026
GID_N=100
PORT=8900
IMAGE="longmeidao/peach:0.50.0"
NAME="peach"

while [ $# -gt 0 ]; do
  case "$1" in
    --media) MEDIA="$2"; shift 2 ;;
    --data)  DATA="$2";  shift 2 ;;
    --uid)   UID_N="$2"; shift 2 ;;
    --gid)   GID_N="$2"; shift 2 ;;
    --port)  PORT="$2";  shift 2 ;;
    --image) IMAGE="$2"; shift 2 ;;
    --name)  NAME="$2";  shift 2 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "未知参数: $1"; exit 2 ;;
  esac
done

say() { echo "[$(date +%H:%M:%S)] $*"; }
die() { echo "!! $*" >&2; exit 1; }

say "镜像 = $IMAGE"
say "媒体 = $MEDIA (只读) "
say "数据 = $DATA"
say "运行身份 = $UID_N:$GID_N   端口 = $PORT   容器名 = $NAME"

# ---- 前置检查 ----
[ -d "$MEDIA" ] || die "媒体目录不存在: $MEDIA"
command -v docker >/dev/null 2>&1 || die "没有 docker 命令"
if docker inspect "$NAME" >/dev/null 2>&1; then
  die "容器 $NAME 已存在，先 docker rm -f $NAME 再来"
fi
if netstat -tln 2>/dev/null | grep -q ":$PORT "; then
  die "端口 $PORT 已被占用"
fi

# ---- 镜像是否存在 ----
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  say "本地无该镜像，尝试拉取（Docker Hub 直连超时就换镜像源）"
  docker pull "$IMAGE" || {
    say "直连失败，尝试镜像源"
    for m in docker.1ms.run docker.1panel.live hub.rat.dev dockerproxy.net; do
      if docker pull "$m/$IMAGE" 2>/dev/null; then
        docker tag "$m/$IMAGE" "$IMAGE" && break
      fi
    done
  }
  docker image inspect "$IMAGE" >/dev/null 2>&1 || die "镜像拉取失败，请手动拉取后重跑"
fi

# ---- 数据目录 ----
say "准备数据目录"
mkdir -p "$DATA" || die "创建 $DATA 失败"
chown -R "$UID_N:$GID_N" "$DATA" || say "! chown 失败，若容器报不可写就手动处理"

# ---- 权限自检：以目标 uid 读一次媒体 ----
say "权限自检"
if command -v setpriv >/dev/null 2>&1; then
  if ! setpriv --reuid="$UID_N" --regid="$GID_N" --clear-groups \
        ls "$MEDIA" >/dev/null 2>&1; then
    echo "   !! uid $UID_N 无法读取 $MEDIA"
    echo "   检查该目录 ACL：synoacltool -get \"$MEDIA\""
    echo "   需要有一条对应用户或 administrators 组的 r-x 授权"
  else
    echo "   OK: uid $UID_N 可读 $MEDIA"
  fi
else
  echo "   跳过（无 setpriv）"
fi

# ---- 起容器 ----
say "启动容器"
docker run -d --name "$NAME" \
  --restart unless-stopped \
  --user "$UID_N:$GID_N" \
  -e HOME=/tmp \
  -p "$PORT:8900" \
  -v "$MEDIA":/media:ro \
  -v "$DATA":/data \
  "$IMAGE" >/dev/null || die "docker run 失败"

sleep 8
say "容器状态"
docker ps --filter "name=$NAME" --format '{{.Names}}  {{.Status}}  {{.Ports}}'

say "最近日志"
docker logs --tail 20 "$NAME" 2>&1

say "健康检查"
if docker exec "$NAME" curl -fsS "http://127.0.0.1:8900/healthz?ready=1" >/dev/null 2>&1; then
  say "服务已就绪"
else
  say "健康检查未通过，看上面的日志"
fi

say "登录口令（没有默认密码，首次随机生成）"
docker exec "$NAME" peach token 2>/dev/null || \
  echo "   取不到口令，进容器手动跑：docker exec -it $NAME peach token"

cat <<EOF

部署完成。
  访问地址： http://<NAS局域网IP>:$PORT
  登录后用该口令进入，第一件事是设置访问密码。
  配置页里「媒体目录」填容器内路径：/media
  备份： docker stop $NAME && tar czf peach-data-\$(date +%F).tar.gz -C $(dirname "$DATA") $(basename "$DATA")
EOF
