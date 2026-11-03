# Peach（蜜桃）媒体库在群晖上的部署与运维

> 适用对象：DSM 7.x，Docker / Container Manager 已安装。
> 官方依据：仓库 `peach-mitao/peach` 的 `docs/DOCKER.md`（2026-11-03 抓取），
> 镜像仓库 <https://hub.docker.com/r/longmeidao/peach>，官网 <https://peach.video>。
> 实测机型：DS423+ / DSM 7.4.1-90080 update1 / Docker root dir `/volume2/@docker`。

Peach 是 **单用户、本地优先** 的个人媒体库：扫描目录 → 识别番号 → 抓元数据与封面 →
生成播放墙 → 浏览器播放。数据全部落在 `/data` 的 SQLite 里，**扫描不改动原文件**。
项目 AGPL-3.0，明确面向成年人管理自己的收藏，仓库不含任何媒体。

---

## 一、先记住这五个坑

| # | 坑 | 现象 | 解法 |
|---|---|---|---|
| 1 | **没有 `latest` 标签** | `docker pull longmeidao/peach` 报 manifest unknown | 官方只推**版本号**与 `edge`，必须写明 tag，如 `longmeidao/peach:0.50.0` |
| 2 | **容器固定以 UID 1000 运行** | 扫得到目录但播放/抽帧失败，日志报权限 | DSM 没有 uid 1000，用 `--user <真实uid>:<gid>` 覆盖；DSM 上 `jie` 是 `1026:100` |
| 3 | **媒体目录 ACL 不放行** | 同上 | 目标目录的 ACL 里必须有该用户或 `administrators` 组的 `r-x` 权限，用 `synoacltool -get` 核实 |
| 4 | **把整个共享挂进去** | 转码临时目录、回收站被当成作品扫进库 | `/media` 只挂**具体媒体子目录**，不要挂共享根 |
| 5 | **`/data` 不是独立卷** | 重建容器后整个库、观看记录、刮削结果全丢 | `/data` 必须挂持久目录，并 `chown` 到容器实际运行的 uid |

补充：镜像当前目标平台是 **linux/amd64**，ARM 机型（DS223 等）官方未验收。
镜像内置健康检查 `/healthz?ready=1`。

### 补充：镜像从哪来（国内必读）

国内 NAS 拉 Docker Hub 基本必挂，而且**报错都在骗人**——真正原因通常不是「镜像不存在」。

**第一步：分清是「DNS 被投毒」还是「镜像确实没有」。**

```bash
nslookup hub.docker.com
# 正常应回到 Docker 的 CDN 段；回到 31.13.x.x（Meta 的段）就是被投毒
curl -sS -m 10 -o /dev/null -w '%{http_code}\n' https://registry-1.docker.io/v2/
# 000 = 连不上（被墙/被投毒）；401 = 正常，只是要鉴权
```

**第二步：走国内镜像源。** 实测（DS423+ / DSM 7.4.1-90080，2026-11-03）：

| 源 | 实测结果 | 备注 |
|---|---|---|
| `docker.1ms.run` | ✅ 可用，能正常代理拉取 | 首选 |
| `docker.xuanyuan.me` | ⚠️ 可用但会 `403 TOOMANYREQUESTS` | 免费节点繁忙，重试或换源 |
| `docker.m.daocloud.io` | ⚠️ 有**仓库白名单** | 未收录的仓库报 `not in allowlist`，与本镜像无关的失败 |
| `docker.1panel.live` / `hub.rat.dev` / `dockerproxy.net` | ❌ 实测无此镜像 | 不要浪费时间 |
| `registry-1.docker.io` 直连 | ❌ 443 超时 | 必须走上面的源 |

用法是**把源名拼在镜像名前**，不是改 daemon 配置（daemon 里预置的那堆 mirror 在 DSM 上大多是死的）：

```bash
docker pull docker.1ms.run/longmeidao/peach:0.50.0
# 拉完打个短标签，后续命令不用再带源名
docker tag docker.1ms.run/longmeidao/peach:0.50.0 longmeidao/peach:0.50.0
```

> ⚠️ **`401 UNAUTHORIZED` 不代表 tag 不存在。** 用 `curl` 探测 `/v2/<repo>/manifests/<tag>`
> 拿到 401 是 Docker Registry v2 的**正常鉴权挑战**（要先去 `auth` 换 token）。
> 想判断某个 tag 在不在，只有两种可靠办法：①真 `docker pull` 一次；②先走 token 流程再查。
> 直接看 401 就断言「镜像没有」会误判。

> ⚠️ **拉取耗时不可用「已经下了几层」判断。** `docker pull` 在非 TTY 下只在**状态变化**时
> 打印一行（`Pulling fs layer` → `Download complete` → `Pull complete`），大层下载期间可能
> 好几分钟一个字都不出。**日志不增长 ≠ 卡死**。按这个去判停滞并把进程杀掉，会永远拉不完。
> 判断是否真的在动，看 `/volume2/@docker` 的体积增长或网卡流量，别看日志行数。

**一个坑套一个坑**：`pull` 中途断掉不用从头来——已 `Pull complete` 的层会被复用，
所以「失败就重来」是有效策略。`scripts/peach_pull.sh` 就是把它固化下来的：
先做连通性自检分流，再按源 × 轮次重试，只以「镜像是否真的落地」判成功。

DSM 上还有一个坑：**没有 `pgrep`（只有 `pkill`）**。用 `pgrep` 写的守护逻辑会
`command not found` 返回非 0，于是每个循环都被判成「进程已退出」，短时间内并发起
十几个 `docker pull`，互相拖死。要判进程存活用 `ps -ef | grep -F <pattern> | grep -v grep`。

---

## 二、部署（实测可用命令）

```bash
# 0) 变量按实际改；DSM 上 media 目录的属主/ACL 要先确认可读
IMG=longmeidao/peach:0.50.0
NAME=peach
MEDIA=/volume1/学习资料/AV        # 只挂具体媒体目录
DATA=/volume2/peach-data          # 放 SSD 卷，减少 HDD 读写噪音
UID_N=1026                        # jie
GID_N=100                         # users

# 1) 先把镜像搞下来（国内必看上一节；拉取中断可反复重跑，已完成的层会复用）
scp scripts/peach_pull.sh root@<NAS>:/volume1/homes/<user>/ && \
  ssh root@<NAS> "bash /volume1/homes/<user>/peach_pull.sh --image longmeidao/peach --tag 0.50.0"
# 也可以直接用 skills 里的部署脚本，它内部会处理镜像缺失
#   bash scripts/peach_deploy.sh --media /volume1/学习资料/AV --data /volume2/peach-data --uid 1026 --gid 100

# 2) 数据目录，属主必须是容器运行身份
mkdir -p "$DATA"
chown -R "$UID_N:$GID_N" "$DATA"

# 3) 起容器（媒体只读挂载）
docker run -d --name "$NAME" \
  --restart unless-stopped \
  --user "$UID_N:$GID_N" \
  -e HOME=/tmp \
  -p 8900:8900 \
  -v "$MEDIA":/media:ro \
  -v "$DATA":/data \
  "$IMG"

# 4) 取登录口令（没有通用初始密码，每次全新数据卷都会随机生成）
docker exec "$NAME" peach token

# 5) 健康检查
docker exec "$NAME" curl -fsS "http://127.0.0.1:8900/healthz?ready=1" && echo OK
```

浏览器打开 `http://<NAS局域网IP>:8900`，用第 3 步的口令登录，**登录后第一件事是设置访问密码**。

### 端口与绑定

- 容器内固定监听 `0.0.0.0:8900`，宿主机端口随便映射。
- `docker run -p 8900:8900` 会绑到 `0.0.0.0`（局域网可达）。
- 官方 compose 默认只绑 `127.0.0.1`（只有 NAS 本机能访问），要局域网访问得在 `.env` 里设
  `PEACH_BIND=<NAS局域网IP>` / `PEACH_PORT` / `PEACH_MEDIA_ROOT`。
- DSM 防火墙若开了「仅允许指定端口」，要放行映射后的端口。
- 注意：`.env` / compose 里的 `127.0.0.1` 在**另一台电脑**上打不开，这是最常见的“起来了但访问不了”。

---

## 三、首次配置要点

1. 配置页 → 媒体目录 → 填**容器内路径**（`/media`），选来源与读取策略，保存。
2. 勾选扫描即开始处理；大库首次扫描很吃 CPU，建议避开转码高峰。
3. 路径有三层概念，别搞混：

| 位置 | 示例 | 用途 |
|---|---|---|
| 宿主机目录 | `/volume1/学习资料/AV` | `docker run -v` 的左边 |
| 容器内目录 | `/media` | 配置页里填的 |
| 数据库路径前缀 | `R:\media` | `[media.locations]`，**由 Peach 自己管理** |

已有库时**不要改** `[media.locations]`——它必须继续匹配数据库里已存的路径前缀，
改了不会同步老记录，只会让老影片全部找不到。只搬动实际目录时，改 `[media.mounts]` 和挂载即可。

配置文件在 `/data/config.toml`，手改前先备份；`/data` 里同时有 SQLite、凭据和图片缓存。

---

## 四、与转码流水线的对接约定

本机/NAS 都在跑 h265 QSV 转码（见 `h265-transcode-pipeline.md`），对接 Peach 有三条硬约定：

1. **文件名/目录名保留番号**。Peach 靠 `ABP-557` 这种编号识别作品；转码输出是
   `<原名>.mkv`，目录名就是番号，能正常识别，不需要回头改名。
2. **只挂 `AV` 目录**。转码用的 `_h265_queue`、原片暂存区 `_原片待删` 都在上一级，
   不挂进去就不会被误扫。
3. **别让 Peach 做转码**。它支持 VAAPI/NVENC，但 NAS 只有一颗核显，会和转码队列抢硬件；
   转码归流水线，Peach 只负责索引和播放。

`_多版本/` 那类同名多版本目录，正好交给 Peach 的「重复项 / 多版本」管理，比 CSV 记「待人工判断」直观。

---

## 五、排错速查

| 现象 | 排查 |
|---|---|
| 容器起了但浏览器打不开 | 先确认端口有没有映射到 `0.0.0.0`；再从 NAS 本机 `curl 127.0.0.1:8900` 验证 |
| 能浏览但点播放失败 | 十有八九是 uid/ACL：`docker exec -u <uid> <name> ls /media` 看得到吗 |
| 扫不出影片 | 目录没加进配置页，或 `[media.mounts]` 与挂载路径不一致 |
| 抽帧/缩略图全黑 | 视频色深或编码超出 VAAPI 解码范围，属正常回退；配置页可改「抽帧解码方式」为软件 |
| 升级镜像后库打不开 | 数据库有待执行的迁移，先备份 `/data` 再按官方 OPERATIONS 的迁移流程处理 |

导出诊断报告（不含数据库和媒体）：

```bash
docker exec peach python -m peach.support_bundle /tmp/peach-support.zip
docker cp peach:/tmp/peach-support.zip ./peach-support.zip
```

---

## 六、备份与卸载

```bash
# 备份：/data 就是全部身家
docker stop peach
tar czf peach-data-$(date +%F).tar.gz -C /volume2 peach-data
docker start peach

# 卸载（保留数据）
docker rm -f peach
# 真要连数据一起删再执行：rm -rf /volume2/peach-data
```

> 风险提示：桌面安装包未签名，macOS 版未公证；项目仅 6 名贡献者、100+ 开放 issue。
> 自建部署要定期备份 `/data`，不要把它当唯一副本。
