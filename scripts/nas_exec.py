#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run a command on a Synology NAS over SSH, escalating to root via `sudo -i`.

Auth is handled in two independent layers — they are easy to conflate:

  1. **SSH login**  — key (recommended) or the account password
  2. **sudo -i**    — only needed when NAS_USER is not root; the same password
                      is fed to sudo over the allocated pty

Why paramiko: the OpenSSH client reads the password from `/dev/tty`, **not stdin**,
so `echo pw | ssh ...` hangs at the `user@host's password:` prompt. Paramiko
supplies the password in-process, which is the only clean way to do password
auth non-interactively. Falls back to the `ssh` binary if paramiko is absent
(key auth only in that mode).

    pip install paramiko

Config (environment):
    NAS_HOST  (required)  NAS IP/hostname          e.g. <NAS_IP>
    NAS_USER  (required)  SSH account              e.g. myadmin / root
    NAS_PORT  default 22                           port from DSM > Terminal
    NAS_KEY   optional, path to private key        e.g. ~/.ssh/nas_rsa
    NAS_PASS  optional, password for SSH login and/or sudo

Only accounts in the DSM **administrators** group can get root via `sudo -i`.

Usage:
    nas_exec.py --health                    # safe read-only probe
    nas_exec.py "cat /etc/VERSION; df -h"
    nas_exec.py --dry-run "synoservice --restart samba"
    nas_exec.py --install-key --yes          # copy ~/.ssh/id_rsa.pub -> NAS
                                             # (changes device config: needs --yes)
"""
import argparse
import base64
import os
import subprocess
import sys
import time

HEALTH_CMD = r"""
echo "===== DSM VERSION ====="; cat /etc/VERSION 2>/dev/null || echo "(no /etc/VERSION)"
echo; echo "===== HOSTNAME / KERNEL ====="; hostname; uname -a
echo; echo "===== UPTIME / LOAD ====="; uptime
echo; echo "===== DISK (volume) ====="; df -h | grep -E '^/dev/mapper|^Filesystem'
echo; echo "===== MEMORY ====="; free -m 2>/dev/null || true
echo; echo "===== SYNO CLI TOOLS ====="
ls /usr/syno/sbin/ 2>/dev/null | grep -E '^(synouser|synogroup|synoshare|synonet|synoservice|synowin)$' \
  || echo "(none found - check DSM version)"
""".strip()

DESTRUCTIVE = ("rm ", "mkfs", "reboot", "shutdown", "poweroff", "init ",
               "--del", "--disable", "--stop", "format", "> /dev/")

# Two independent guards, both bypassed with `--yes` — which means "the user has
# been told what this does and agreed". Default stance: read-only, never touch
# device configuration unless the user explicitly asked for that change.
#
# 1. DESTRUCTIVE — things that can destroy data or drop connectivity.
# 2. MUTATING_TOKENS / CLI_TOOLS — things that rewrite persistent config, handled
#    by config_mutations() below.

# Write-shaped constructs: flagged wherever they appear in the command.
MUTATING_TOKENS = (
    "authorized_keys",      # writing ~/.ssh/authorized_keys
    "/usr/syno/etc/",       # DSM keeps its persistent config here
    "tee ", ">> ",
    "chmod ", "chown ", "mv ",
    "--setpw", "--set_gateway", "--set_dns", "--manual",
    "--enable", "--restart",
)

# Official CLI tools. Flagged only when they are *the command being run* — their
# presence in an argument is harmless (e.g. `ls /usr/syno/sbin/ | grep synouser`).
CLI_TOOLS = ("synouser", "synogroup", "synoshare", "synonet", "synowin")

# Flags after which a CLI tool is read-only.
READONLY_FLAGS = ("--help", "-h", "--list", "--get", "--status", "--version")


def needs_sudo(user):
    return user != "root"


def wrap_sudo(cmd):
    """Wrap `cmd` so it runs under `sudo -i` with byte-for-byte fidelity.

    Why not `sudo -i bash -c '<cmd>'`? Verified on a real DS918+ (DSM 7.3): sudo
    puts the payload through an **extra layer of shell parsing**, which silently
    corrupts anything non-trivial — newlines get eaten (`echo AAA` + `echo BBB`
    becomes `echo AAAecho BBB`) and shell variables like `$t` are expanded to
    empty *before* the script ever runs. `command | sudo` breaks too: sudo's stdin
    is then the pipe, so it can never read the password.

    Base64 removes every shell metacharacter from the payload, so the extra parse
    is harmless — while the password still arrives over the pty where sudo expects it.
    """
    blob = base64.b64encode(cmd.encode("utf-8")).decode("ascii")
    return f"sudo -S -p '' -i bash -c 'echo {blob} | base64 -d | bash'"


def _split_stages(cmd):
    """Split on unquoted | ; && and newline. Quote-aware, because a regex argument
    like `'^(synouser|synogroup)$'` contains pipes that are not shell pipes."""
    stages, buf, quote, i = [], [], None, 0
    while i < len(cmd):
        ch = cmd[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            i += 1
        elif ch in "'\"":
            quote = ch
            buf.append(ch)
            i += 1
        elif ch in "|;\n":
            stages.append("".join(buf))
            buf = []
            i += 1
        elif cmd.startswith("&&", i):
            stages.append("".join(buf))
            buf = []
            i += 2
        else:
            buf.append(ch)
            i += 1
    stages.append("".join(buf))
    return stages


def command_names(cmd):
    """Names of the executables actually being run, across pipes and separators."""
    names = set()
    for stage in _split_stages(cmd):
        stage = stage.strip()
        if not stage:
            continue
        names.add(os.path.basename(stage.split()[0].strip("'\"")).lower())
    return names


def config_mutations(cmd):
    """Reasons this command rewrites the NAS's persistent configuration.

    Deliberately narrow: `synouser --help`, `synoservice --list` and even
    `ls /usr/syno/sbin/ | grep synouser` must stay usable, because "discover with
    --help before running anything" is the workflow this skill recommends.
    Anything not obviously read-only gets flagged and needs an explicit --yes
    (i.e. the user was told and agreed).
    """
    low = cmd.lower()
    hits = [tok.strip() for tok in MUTATING_TOKENS if tok in low]
    invoked = command_names(cmd)
    for tool in CLI_TOOLS:
        if tool in invoked and not any(f in low for f in READONLY_FLAGS):
            hits.append(tool)
    return sorted(set(hits))


# ----------------------------------------------------------------- paramiko
def run_paramiko(args, cmd):
    import paramiko
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ckw = dict(hostname=args.host, port=args.port, username=args.user,
               timeout=args.timeout, allow_agent=not args.password,
               look_for_keys=not args.password)
    if args.key:
        ckw.update(key_filename=os.path.expanduser(args.key))
    if args.password:
        ckw["password"] = args.password
    client.connect(**ckw)
    try:
        sudo = needs_sudo(args.user)
        remote = wrap_sudo(cmd) if sudo else cmd
        # sudo needs a pty; plain root commands keep stdout/stderr separate
        stdin, stdout, stderr = client.exec_command(remote, get_pty=sudo,
                                                    timeout=args.timeout)
        if sudo:
            time.sleep(0.4)
            stdin.write(args.password + "\n")
            stdin.flush()
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        rc = stdout.channel.recv_exit_status()
        return rc, out, err
    finally:
        client.close()


# ------------------------------------------------------------ ssh fallback
def run_ssh_binary(args, cmd):
    target = f"{args.user}@{args.host}"
    ssh = ["ssh", "-p", str(args.port), "-o", "StrictHostKeyChecking=accept-new",
           "-o", "ConnectTimeout=10", "-o", "LogLevel=ERROR"]
    if args.key:
        ssh += ["-i", os.path.expanduser(args.key), "-o", "IdentitiesOnly=yes"]
    remote = wrap_sudo(cmd) if needs_sudo(args.user) else cmd
    ssh += ["-tt", target, remote]
    stdin_data = (args.password + "\n").encode() if needs_sudo(args.user) else None
    try:
        p = subprocess.run(ssh, input=stdin_data, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=args.timeout)
    except subprocess.TimeoutExpired:
        print("[ERROR] timed out. If you are stuck at a 'password:' prompt, "
              "the ssh binary cannot read it from stdin — either set NAS_KEY "
              "or install paramiko (pip install paramiko).", file=sys.stderr)
        return 124, "", ""
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def install_key(args):
    pub = os.path.expanduser(args.pubkey)
    if not os.path.exists(pub):
        print(f"[ERROR] public key not found: {pub}\n"
              f"        generate one with: ssh-keygen -t rsa -b 4096", file=sys.stderr)
        return 2
    pubdata = open(pub).read().strip()
    try:
        import paramiko
    except ImportError:
        print("[ERROR] --install-key needs paramiko (pip install paramiko)", file=sys.stderr)
        return 2
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(args.host, port=args.port, username=args.user,
                   password=args.password, timeout=args.timeout)
    sftp = client.open_sftp()
    try:
        try:
            sftp.stat(".ssh")
        except IOError:
            sftp.mkdir(".ssh", mode=0o700)
        path = ".ssh/authorized_keys"
        existing = ""
        try:
            existing = sftp.open(path).read().decode()
        except IOError:
            pass
        if pubdata.split()[1] in existing:
            print("key already present on the NAS, nothing to do")
        else:
            with sftp.open(path, "w") as f:
                f.write((existing.rstrip("\n") + "\n" if existing else "") + pubdata + "\n")
            sftp.chmod(path, 0o600)
            print(f"installed {pub} -> {args.user}@{args.host}:~/.ssh/authorized_keys")
    finally:
        sftp.close()
        client.close()
    return 0


def main():
    env = os.environ
    p = argparse.ArgumentParser(description="Run a command on a Synology NAS as root.")
    p.add_argument("command", nargs="*", help="command to run (use - to read stdin)")
    p.add_argument("--host", default=env.get("NAS_HOST", ""))
    p.add_argument("--user", default=env.get("NAS_USER", "root"))
    p.add_argument("--port", type=int, default=int(env.get("NAS_PORT", 22)))
    p.add_argument("--key", default=env.get("NAS_KEY", ""), help="private key for SSH login")
    p.add_argument("-P", "--password", default=env.get("NAS_PASS", ""),
                   help="password for SSH login and/or sudo")
    p.add_argument("--timeout", type=int, default=30)
    p.add_argument("--health", action="store_true", help="safe read-only probe")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--yes", dest="confirmed", action="store_true",
                   help="skip the destructive-command guard")
    p.add_argument("--install-key", action="store_true",
                   help="copy a public key to the NAS for passwordless login")
    p.add_argument("--pubkey", default="~/.ssh/id_rsa.pub")
    args = p.parse_args()

    if not args.host:
        print("[ERROR] NAS_HOST is required (or pass --host).", file=sys.stderr)
        return 2

    if args.install_key:
        if not args.password:
            print("[ERROR] --install-key needs NAS_PASS this one time.", file=sys.stderr)
            return 2
        if not args.confirmed:
            print("[WARN] --install-key rewrites ~/.ssh/authorized_keys on the NAS, "
                  "i.e. it changes device configuration.\n"
                  "       Default policy is read-only. Only proceed if the user "
                  "explicitly asked for passwordless login; then re-run with --yes.",
                  file=sys.stderr)
            return 2
        return install_key(args)

    if args.health:
        cmd = HEALTH_CMD
    elif args.command == ["-"]:
        cmd = sys.stdin.read().strip()      # safest way to pass multi-line scripts
    elif args.command:
        cmd = " ".join(args.command)
    else:
        print("[ERROR] provide a command, or use --health", file=sys.stderr)
        return 2

    sudo = needs_sudo(args.user)
    if sudo and not args.password:
        print("[ERROR] NAS_USER != root and no password: sudo -i cannot run.\n"
              "        Set NAS_PASS, or use root + NAS_KEY.", file=sys.stderr)
        return 2

    if args.dry_run:
        auth = f"key={args.key}" if args.key else ("password" if args.password else "agent/default keys")
        print("# DRY RUN - nothing executed")
        print(f"# target  : {args.user}@{args.host}:{args.port}")
        print(f"# ssh auth: {auth}")
        print(f"# run as  : root via 'sudo -i'" if sudo else "# run as  : root (direct)")
        print("# command :")
        for line in cmd.splitlines():
            print("    " + line)
        return 0

    # --health is a read-only probe by construction; never gate it.
    if not args.health and not args.confirmed:
        hits = [t for t in DESTRUCTIVE if t in cmd.lower()]
        if hits:
            print(f"[WARN] looks destructive ({', '.join(hits)}).\n"
                  f"       Confirm with the user, then re-run with --yes. "
                  f"Use --dry-run to inspect first.", file=sys.stderr)
            return 2
        muts = config_mutations(cmd)
        if muts:
            print(f"[WARN] this changes NAS configuration ({', '.join(muts)}).\n"
                  f"       Default policy is read-only — only run it if the user "
                  f"explicitly asked for this change, then re-run with --yes.\n"
                  f"       Use --dry-run to inspect the exact command first.",
                  file=sys.stderr)
            return 2

    try:
        rc, out, err = run_paramiko(args, cmd)
    except ImportError:
        if args.password and not args.key:
            print("[WARN] paramiko not installed; falling back to the ssh binary, "
                  "which cannot do password login non-interactively.\n"
                  "       Fix with: pip install paramiko", file=sys.stderr)
        rc, out, err = run_ssh_binary(args, cmd)

    out = out.replace("\r\n", "\n").strip()
    err = err.replace("\r\n", "\n").strip()
    if out:
        print(out)
    if err:
        print(err, file=sys.stderr)
    if rc == 255:
        print("[ERROR] SSH failed. Check NAS_HOST/NAS_PORT, that SSH is enabled in "
              "DSM > Control Panel > Terminal & SNMP, and that the account is in "
              "the administrators group.", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main())
