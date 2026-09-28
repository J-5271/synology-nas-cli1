# 协作规范

## 谁能改

仓库私有，只有被邀请的协作者有写权限。包内含实测设备档案、内网 IP 段、SSH 运维细节，
**不要转发、不要 fork 成公开仓库**。

## 分支策略

- `main` **不接受协作者直接 push**，改动走 PR。
- 改任何东西先开分支：`git switch -c feat/<简短描述>`，PR 经 review 后由仓库所有者合并。
- PR 需 1 个 review 通过才能合并。

> 注：GitHub Free 计划的**私有仓库不支持分支保护 / rulesets**（API 返回
> "Upgrade to GitHub Pro or make this repository public"）。仓库必须保持私有，
> 所以上面这条目前靠约定执行，不靠平台强制。真要强制需升级 GitHub Pro。

## 提交前必做

```bash
python -m py_compile scripts/*.py                    # 语法检查
python scripts/nas_exec.py --dry-run "cat /etc/VERSION"      # 只读应放行
python scripts/nas_exec.py --dry-run "/usr/syno/sbin/synouser --setpw <账号> <密码>"  # 改配置应拦截
python scripts/pack_skill.py --mode full --no-state  # 凭据扫描，命中 exit 4 必须先脱敏
```

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
