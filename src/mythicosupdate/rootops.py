# MythicOS Update Manager - operations performed as root
#
# Used by mythicos-update-helper (through pkexec) and by the automatic update
# service. Everything the unprivileged side can ask for is validated here.
#
# Copyright (C) 2026 Studio Hastag <contact@hastag.fr>
# SPDX-License-Identifier: GPL-3.0-or-later

import collections
import datetime
import json
import os
import re
import select
import signal
import subprocess
import sys
import time

from mythicosupdate import aptcheck, constants, locks, logutil

PACKAGE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9+.\-]*(:[a-z0-9\-]+)?$")
STATUS_LINE_RE = re.compile(r"^(pmstatus|dlstatus|media-change):")


class OperationError(Exception):
    def __init__(self, code, event, **details):
        super().__init__(event)
        self.code = code
        self.event = event
        self.details = details


# ---------------------------------------------------------------- output

_stdout_alive = True


def out(text):
    """Write a line to stdout; survive the reader going away."""
    global _stdout_alive
    if not _stdout_alive:
        return
    try:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()
    except (BrokenPipeError, OSError, ValueError):
        _stdout_alive = False


def emit(event, **details):
    payload = {"event": event}
    payload.update(details)
    out(constants.PROTOCOL_PREFIX + json.dumps(payload, ensure_ascii=False))


# ------------------------------------------------------------- utilities

def clean_environment():
    env = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
           "DEBIAN_FRONTEND": "noninteractive",
           "APT_LISTCHANGES_FRONTEND": "none",
           "LC_ALL": "C.UTF-8",
           "HOME": "/root"}
    for key in ("http_proxy", "https_proxy", "ftp_proxy", "no_proxy",
                "HTTP_PROXY", "HTTPS_PROXY", "FTP_PROXY", "NO_PROXY"):
        if key in os.environ:
            env[key] = os.environ[key]
    return env


def validate_package_names(names):
    for name in names:
        if not PACKAGE_NAME_RE.match(name):
            raise OperationError(constants.EXIT_BAD_ARGUMENTS, "bad-argument", argument=name)


def requested_by():
    return os.environ.get("PKEXEC_UID", "")


def _group_io(pgid):
    """Total bytes read+written (network included) by every process of the
    process group. Flatpak prints nothing while it downloads a large runtime
    when its output is not a terminal, so "no output" does not mean "stuck"."""
    total = 0
    try:
        entries = os.listdir("/proc")
    except OSError:
        return None
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open("/proc/%s/stat" % entry, encoding="utf-8", errors="replace") as handle:
                fields = handle.read().rsplit(")", 1)[1].split()
            if int(fields[2]) != pgid:  # field 5 of stat: process group id
                continue
            with open("/proc/%s/io" % entry, encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith(("rchar:", "wchar:")):
                        total += int(line.split(":")[1])
        except (OSError, IndexError, ValueError):
            continue
    return total


def run_streamed(cmd, env=None, total_timeout=None, stall_timeout=None, status_pipe=False):
    """Run cmd, copying its output line by line to our stdout.
    Returns (returncode, tail_text, timeout_reason).

    status_pipe: apt-get only. The progress lines (pmstatus/dlstatus) are
    requested on a dedicated pipe. They must NOT go to fd 1: with
    APT::Status-Fd=1 the maintainer scripts of packages lose their standard
    output ("echo: I/O error", "sed: couldn't close stdout") and fail."""
    status_read = status_write = None
    if status_pipe:
        status_read, status_write = os.pipe()
        cmd = list(cmd[:2]) + ["-o", "APT::Status-Fd=%d" % status_write] + list(cmd[2:])
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, env=env or clean_environment(),
                                   start_new_session=True,
                                   pass_fds=(status_write,) if status_pipe else ())
    finally:
        if status_write is not None:
            os.close(status_write)
    main_fd = process.stdout.fileno()
    open_fds = {main_fd}
    if status_read is not None:
        open_fds.add(status_read)
    pending = {fd: b"" for fd in open_fds}
    tail = collections.deque(maxlen=80)
    start = last_output = time.monotonic()
    reason = None
    last_io = None
    next_io_check = start + 5

    def handle(line_bytes):
        text = line_bytes.decode("utf-8", "replace").rstrip()
        if not text:
            return
        out(text)
        if not STATUS_LINE_RE.match(text):
            tail.append(text)

    def feed(fd, chunk):
        pending[fd] += chunk
        while True:
            positions = [pos for pos in (pending[fd].find(b"\n"), pending[fd].find(b"\r")) if pos >= 0]
            if not positions:
                break
            cut = min(positions)
            handle(pending[fd][:cut])
            pending[fd] = pending[fd][cut + 1:]

    try:
        while main_fd in open_fds:
            now = time.monotonic()
            if stall_timeout and now >= next_io_check:
                # Progress without any output (a big download) counts as activity.
                next_io_check = now + 5
                current_io = _group_io(process.pid)
                if current_io is not None and current_io != last_io:
                    last_io = current_io
                    last_output = now
            if total_timeout and now - start > total_timeout:
                reason = "total"
            elif stall_timeout and now - last_output > stall_timeout:
                reason = "stall"
            if reason:
                for sig in (signal.SIGTERM, signal.SIGKILL):
                    try:
                        os.killpg(process.pid, sig)
                    except ProcessLookupError:
                        break
                    time.sleep(3 if sig == signal.SIGTERM else 0)
                break
            ready, _, _ = select.select(list(open_fds), [], [], 1.0)
            if ready:
                for fd in ready:
                    chunk = os.read(fd, 65536)
                    if not chunk:
                        open_fds.discard(fd)
                        continue
                    last_output = time.monotonic()
                    feed(fd, chunk)
            elif process.poll() is not None:
                break
        # Drain what is left on the status pipe once the process is gone.
        if status_read is not None and status_read in open_fds:
            try:
                os.set_blocking(status_read, False)
                while True:
                    chunk = os.read(status_read, 65536)
                    if not chunk:
                        break
                    feed(status_read, chunk)
            except (BlockingIOError, OSError):
                pass
    finally:
        if status_read is not None:
            os.close(status_read)
    for leftover in pending.values():
        if leftover:
            handle(leftover)
    try:
        returncode = process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        returncode = process.wait()
    return returncode, "\n".join(tail), reason


def record_history(source, result, items):
    entry = {"date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             "source": source, "result": result, "requested_by": requested_by(),
             "items": [{"name": n, "old": o, "new": nw, "action": a} for n, o, nw, a in items]}
    try:
        fd = os.open(constants.ROOT_HISTORY_FILE, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as error:
        logutil.error("Cannot write the history: %s" % error)


# ---------------------------------------------------------------- locks

def ensure_package_manager_free():
    holder = locks_holder()
    if holder is not None:
        raise OperationError(constants.EXIT_LOCKED, "locked", holder=holder)


def locks_holder():
    """None if free, else a description of the process holding the lock."""
    names = []
    for path in ("/var/lib/dpkg/lock-frontend", "/var/lib/dpkg/lock",
                 "/var/cache/apt/archives/lock"):
        if not os.path.exists(path):
            continue
        try:
            result = subprocess.run(["fuser", path], stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, text=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            continue
        for pid in result.stdout.split():
            if not pid.isdigit() or int(pid) == os.getpid():
                continue
            try:
                with open("/proc/%s/comm" % pid, encoding="utf-8") as handle:
                    label = "%s (%s)" % (handle.read().strip(), pid)
            except OSError:
                label = pid
            if label not in names:
                names.append(label)
    return ", ".join(names) if names else None


# ------------------------------------------------------------------ APT

APT_OPTIONS = ["-o", "Dpkg::Options::=--force-confdef",
               "-o", "Dpkg::Options::=--force-confold",
               "-o", "Dpkg::Use-Pty=0"]


def repair_dpkg():
    emit("stage", name="repair")
    logutil.info("Repairing an interrupted installation")
    for cmd in (["dpkg", "--configure", "-a", "--force-confdef", "--force-confold"],
                ["apt-get", "install", "-f", "-y", "--no-install-recommends"] + APT_OPTIONS):
        code, tail, _ = run_streamed(cmd, status_pipe=cmd[0] == "apt-get")
        if code != 0:
            logutil.error("%s failed (%d): %s" % (" ".join(cmd[:2]), code, tail[-400:]))
            raise OperationError(constants.EXIT_REPAIR_FAILED, "repair-failed", detail=tail[-600:])


def check_apt_request(names, allowed_removals):
    """Refuse anything that is not a plain upgrade of installed packages,
    and refuse removals the user was not shown."""
    validate_package_names(names)
    refused = aptcheck.packages_not_upgradable(names)
    if refused:
        raise OperationError(constants.EXIT_BAD_ARGUMENTS, "not-upgradable", packages=refused)

    import apt
    cache = apt.Cache()
    for name in names:
        cache[name].mark_upgrade()
    removed = sorted(pkg.name for pkg in cache.get_changes() if pkg.marked_delete)
    unexpected = [name for name in removed if name not in allowed_removals]
    if unexpected:
        raise OperationError(constants.EXIT_UNEXPECTED_REMOVAL, "unexpected-removal", packages=unexpected)

    from mythicosupdate import diskcheck
    download = int(cache.required_download)
    install = int(cache.required_space)
    missing = diskcheck.missing_space(download, install)
    if missing > 0:
        raise OperationError(constants.EXIT_DISK_FULL, "disk-full", missing=missing)
    return removed


def apt_upgrade(names, allowed_removals=(), repair=True):
    """Install the given upgrades. Raises OperationError."""
    ensure_package_manager_free()
    if repair and aptcheck.needs_repair():
        repair_dpkg()
    check_apt_request(names, set(allowed_removals))

    emit("stage", name="apt", count=len(names))
    logutil.info("Installing %d packages (requested by uid %s): %s"
                 % (len(names), requested_by() or "?", " ".join(names)))
    cmd = (["apt-get", "install", "-y", "--no-install-recommends"] + APT_OPTIONS + ["--"] + list(names))
    code, tail, _ = run_streamed(cmd, total_timeout=None, status_pipe=True)
    if code == 0:
        logutil.info("APT installation finished successfully")
        return
    logutil.error("apt-get install failed with code %d: %s" % (code, tail[-600:]))
    record_history("apt-failed", "failed", [(n, "", "", "upgrade") for n in names])
    holder = locks.holder_from_apt_message(tail)
    if holder is not None:
        raise OperationError(constants.EXIT_LOCKED, "locked", holder=holder)
    raise OperationError(constants.EXIT_APT_FAILED, "apt-failed", detail=tail[-800:])


# ------------------------------------------------------ package lists

def refresh_package_lists():
    """Refresh the APT lists, like `apt update`.

    A repository that fails (a third-party PPA answering 503, an architecture
    it does not provide...) must not make the whole refresh fail: the other
    lists are still fresh and usable. The refresh only fails when nothing at
    all could be fetched (typically: no network), or when APT cannot start.
    Returns the list of per-repository failures (warnings)."""
    import apt
    import apt.cache
    from apt.progress.base import AcquireProgress

    class Recorder(AcquireProgress):
        def __init__(self):
            super().__init__()
            self.fetched = 0
            self.failed = []

        def done(self, item):
            self.fetched += 1

        def ims_hit(self, item):
            self.fetched += 1

        def fail(self, item):
            detail = getattr(item.owner, "error_text", "") or getattr(item.owner, "status", "")
            entry = "%s: %s" % (item.description, detail or "failed")
            if entry not in self.failed:  # APT reports the same item several times
                self.failed.append(entry)

    import warnings
    recorder = Recorder()
    try:
        with warnings.catch_warnings():
            # python-apt turns every "W:" line into a Python warning: we
            # report the failures ourselves, in a readable form.
            warnings.simplefilter("ignore")
            ok = apt.Cache().update(fetch_progress=recorder, raise_on_error=False)
    except apt.cache.LockFailedException as error:
        raise OperationError(constants.EXIT_LOCKED, "locked", detail=str(error) or "lock")
    except Exception as error:
        raise OperationError(constants.EXIT_FAILED, "refresh-failed", detail=str(error) or repr(error))

    if recorder.failed and recorder.fetched == 0:
        raise OperationError(constants.EXIT_FAILED, "refresh-failed", detail="\n".join(recorder.failed))
    if not ok and not recorder.failed:
        raise OperationError(constants.EXIT_FAILED, "refresh-failed",
                             detail="APT reported an error without naming a repository")
    return recorder.failed


# -------------------------------------------------------------- Flatpak

def _flatpak_snapshot():
    try:
        result = subprocess.run(["flatpak", "list", "--system", "--columns=ref,commit"],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                timeout=60, env=clean_environment())
    except (OSError, subprocess.TimeoutExpired):
        return {}
    snapshot = {}
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].strip():
            snapshot[parts[0].strip()] = parts[1].strip()[:10]
    return snapshot


def flatpak_update(source="flatpak"):
    """Update the system-wide Flatpaks. Raises OperationError."""
    import shutil
    if shutil.which("flatpak") is None:
        return
    emit("stage", name="flatpak")
    logutil.info("Updating system Flatpaks")
    before = _flatpak_snapshot()
    cmd = ["flatpak", "update", "--system", "--noninteractive", "-y"]
    code, tail, reason = run_streamed(cmd, total_timeout=constants.FLATPAK_TOTAL_TIMEOUT,
                                      stall_timeout=constants.FLATPAK_STALL_TIMEOUT)
    after = _flatpak_snapshot()
    items = []
    for ref, commit in after.items():
        if ref not in before:
            items.append((ref, "", commit, "install"))
        elif before[ref] != commit:
            items.append((ref, before[ref], commit, "upgrade"))
    if code == 0:
        if items:
            record_history(source, "ok", items)
        logutil.info("Flatpak update finished successfully")
        return
    message = "timed out (no progress)" if reason else tail[-600:]
    logutil.error("flatpak update failed (%s): %s" % (code, message))
    record_history(source, "failed", items)
    raise OperationError(constants.EXIT_FLATPAK_FAILED, "flatpak-failed",
                         detail=message, timeout=bool(reason))


def ignore_termination_signals():
    """Once packages are being installed, never die half-way because the
    window was closed or the terminal went away."""
    for sig in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM, signal.SIGPIPE):
        try:
            signal.signal(sig, signal.SIG_IGN)
        except (ValueError, OSError):
            pass
