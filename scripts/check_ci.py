#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
校验 .github/workflows/*.yml 能被 YAML 解析器正常解析。

为什么要有这一步：workflow 文件写坏时，GitHub 不会报"第几行错了"，
只会产生一个 conclusion=failure 且 jobs 数为 0 的 run —— 看上去像"CI 挂了"，
实际是文件压根没被解析（2026-09-29 首次发布就栽在 --notes 里的一个空行上）。
本地先解析一遍，把这类问题挡在提交之前。

依赖 PyYAML（pip install pyyaml）；没装则跳过并提示（退出 0，不阻断）。

用法：
    python3 scripts/check_ci.py            # 校验全部 workflow
    python3 scripts/check_ci.py ci.yml     # 只校验指定文件

退出码：0 全部通过（或跳过） / 1 解析失败
"""
import glob
import os
import sys

def _skill_root():
    # 优先用环境变量覆盖（别的 agent 把脚本复制到临时目录运行、__file__ 兜底指错时可重定向）
    env = os.environ.get("SYNO_SKILL_ROOT")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


SKILL_ROOT = _skill_root()
WF_DIR = os.path.join(SKILL_ROOT, ".github", "workflows")


def main():
    targets = sys.argv[1:] or sorted(glob.glob(os.path.join(WF_DIR, "*.yml")))
    if not targets:
        print("[WARN] 未找到 .github/workflows/*.yml，跳过")
        return 0

    try:
        import yaml
    except ImportError:
        print("[WARN] 未安装 PyYAML，跳过 workflow 校验（pip install pyyaml 后可启用）")
        return 0

    bad = 0
    for t in targets:
        path = t if os.path.isabs(t) else os.path.join(WF_DIR, t)
        if not os.path.exists(path):
            print(f"[ERROR] 文件不存在: {path}")
            bad += 1
            continue
        try:
            with open(path, encoding="utf-8") as f:
                doc = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(f"[ERROR] YAML 解析失败 {path}: {e}")
            bad += 1
            continue
        if not isinstance(doc, dict) or "jobs" not in doc:
            print(f"[ERROR] 缺少 jobs 段: {path}")
            bad += 1
            continue
        print(f"✓ {os.path.basename(path)} 合法（jobs: {', '.join(doc['jobs'])})")

    if bad:
        print(f"[ERROR] {bad} 个 workflow 文件有问题——推上去 GitHub 只会得到 0 作业的失败 run")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
