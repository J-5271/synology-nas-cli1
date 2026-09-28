#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
打印「使用须知」：免责声明 + 两个收集表入口 + 版本与更新入口。

与 SKILL.md 顶部「首次加载必弹」区块一致（脚本在区块末尾额外多打一行当前版本号，
版本号来自仓库根的 VERSION 文件）。安装技能后/每次启用时跑一次即可：

    python3 scripts/first_run.py

纯打印，不连设备、不读凭据、无任何副作用，退出码恒为 0。
修改文案时，SKILL.md 顶部区块与本文件需同步。
"""
import os
import sys

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

UPDATE_ENTRIES = (
    ("GitHub 更新地址（能访问优先）",
     "https://github.com/J-5271/synology-nas-cli1/releases"),
    ("腾讯文档版本记录（访问不了 GitHub 走这里）",
     "https://docs.qq.com/aio/DQ05IdUxxR3ZtUndG"),
)

DISCLAIMER_URLS = (
    ("使用报告 / 更新收集（实测记录、命令输出、改进建议）",
     "https://docs.qq.com/form/page/DQ2RsRGRjc3JnRHFi"),
    ("未解决问题 / 售前方案咨询（卡住了、要方案、要报价思路）",
     "https://docs.qq.com/form/page/DQ1dTRXdjTUZ6SFR4"),
)

NOTICE = """\
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Synology NAS 管理技能包 · 使用须知
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【免责声明】
本技能包为个人收集整理的学习与运维笔记，素材来自 Synology 官方文档、
官方知识库及个人设备实测，仅供个人学习与技术交流使用。
· 禁止商用开发：不得用于商业开发、商业交付、付费服务或二次分发获利。
· 无担保：机型 / DSM 版本差异大，不保证适用于你的设备。
· 风险自负：因参考或使用本包造成的任何数据丢失、设备损坏或服务中断，
  整理者不承担任何责任。执行写操作前请先备份。

【反馈与求助 · 两个收集表】"""

MIDDLE = """\

【版本与更新】"""

TAIL = """\
提交前请先脱敏：不要填真实 IP、序列号、账号、密码、sid。
本包不做任何自动遥测，无出站上报。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""


def skill_version():
    try:
        with open(os.path.join(SKILL_ROOT, "VERSION"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "未知"


def main():
    print(NOTICE)
    for i, (label, url) in enumerate(DISCLAIMER_URLS, 1):
        print(f"{i}) {label}")
        print(f"   {url}")
    print(MIDDLE)
    for i, (label, url) in enumerate(UPDATE_ENTRIES, 1):
        print(f"{i}) {label}")
        print(f"   {url}")
    print(f"   检查更新：python3 scripts/check_update.py")
    print()
    print(TAIL)
    print(f"（当前版本 v{skill_version()}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
