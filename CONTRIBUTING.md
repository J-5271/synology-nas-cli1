# 协作规范

## 谁能改

当前是**本地仓库**，无远端。若挂成公开远端（fork / clone 自由），写权限只给被邀请的协作者，改动走 PR。

## 公开仓库红线（最重要）

公开 = 任何人可见、可被抓取、可被 fork 留档，**删除也留痕**。所以：

- 禁止提交真实 IP / 内网网段 / 主机名 / 域名 / 序列号 / MAC
- 禁止提交账号名、uid、密码、sid、云密钥、token
- 禁止提交客户名、项目名、报价、控标参数、方案文档
- 涉及具体环境的，一律占位符：`<NAS_IP>` / `<内网网段>` / `<管理员账号>` / `<密码>` / `<序列号>`
- 提交前跑 `python scripts/pack_skill.py --mode full --no-state`，命中凭据会 exit 4

## 分支策略

- `main` **不接受协作者直接 push**，改动走 PR。
- 改任何东西先开分支：`git switch -c feat/<简短描述>`，PR 经 review 后由仓库所有者合并。
- PR 需 1 个 review 通过才能合并。

> 注：仓库转公开后**分支保护 / rulesets 已在 Free 计划可用**（私有仓库才需 Pro）。
> 是否启用期限内保护，由仓库所有者决定；PR 会跑 GitHub Actions 校验见 `.github/workflows/ci.yml`。

## 提交前必做

```bash
python -m py_compile scripts/*.py                    # 语法检查
python scripts/nas_exec.py --dry-run "cat /etc/VERSION"      # 只打印命令，exit 0
# 守卫只在「非 dry-run」时生效：不加 --yes 必须返回 2，且不连设备
python scripts/nas_exec.py "/usr/syno/sbin/synouser --setpw <账号> <密码>"            # exit 2
python scripts/nas_exec.py "/usr/syno/sbin/synonet --manual eth0 1.2.3.4 255.255.255.0"  # exit 2
python scripts/pack_skill.py --mode full --no-state  # 凭据扫描，命中 exit 4 必须先脱敏
```

> ⚠️ `--dry-run` 只打印将要执行的命令，**永远返回 0，不走守卫**。
> 验证「改配置被拦截」必须去掉 `--dry-run`，靠返回值 2 判定。

`pack_skill.py` 命中真实凭据会中止打包。修法是**把真实值换成占位符**（`<账号>` / `<密码>` / `$ENV`），
不要用 `--allow-secrets`。

## 内容红线

- 禁止真实账号 / 密码 / sid / 云密钥 / token。示例一律占位符。
- 命令必须有实测依据，标注 **DSM 版本 + 机型**。没实测过的不要写。
- 不确定就查官方知识库 https://kb.synology.cn/zh-cn/，不要凭记忆下命令。

## 改完记得

- `CHANGELOG.md` 追加一条「日期 + 新增能力」。
- 改了脚本要同步更新 `SKILL.md` / `README.md` 里的命令清单。

## 生效方式

技能包要在本机生效，需 clone 到：

```
~/.workbuddy/skills/synology-nas-cli/
```

（Windows 即 `C:/Users/<你>/.workbuddy/skills/synology-nas-cli/`）

首次认证：`git credential-manager github login`
