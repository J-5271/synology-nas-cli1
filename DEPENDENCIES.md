# 依赖与外部文件清单

仓库规则：**小于 1 MB 的依赖/支撑文件直接放 `assets/` 入库；大于 1 MB 的只在这里记录地址**
（仓库保持轻量，CI 与 clone 都快）。

## 一、Python 依赖

| 包 | 用途 | 安装 | 体积 |
|---|---|---|---|
| paramiko | SSH 密码登录（nas_exec.py） | `pip install -r requirements.txt` | 约 1.2 MB |

> 用 SSH key 登录时不装也能跑；脚本会自动回退到系统 `ssh` 二进制。
> 其余全部用 Python 标准库（argparse / json / urllib / hashlib / hmac / ssl / re）。

## 二、入库文件（< 1 MB）

| 路径 | 大小 | 说明 |
|---|---|---|
| `requirements.txt` | ~200 B | Python 依赖清单 |
| `scripts/*.py` | < 20 KB/个 | 执行器、打包器、上传器 |
| `references/*.md` | < 10 KB/个 | 命令 / API / 错误码 / 排障 |

## 三、外部文件（≥ 1 MB，只记地址，不入库）

| 名称 | 来源 | 获取方式 |
|---|---|---|
| paramiko 离线 wheel | PyPI | `pip download paramiko -d <离线目录>`，或 https://pypi.org/project/paramiko/#files |
| 群晖官方 DSM 管理员手册 / CLI 指南 | Synology 下载中心 | https://www.synology.com/zh-cn/support/download → 选机型 → 文档 |
| DSM 7.x CLI 命令参考（第三方整理） | 官方知识库 | https://kb.synology.cn/zh-cn/ |
| 本技能包的 ima 知识库副本 | ima「公用nas操作技能」 | kb_id `7510180233248137`；本地由 `pack_skill.py` 生成到 `build/`（被 .gitignore 忽略） |

> 不要把客户方案、报价单、控标参数往这里塞——本仓库是公开的。
