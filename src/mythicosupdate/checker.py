# MythicOS Update Manager - update checks for the window and the tray icon
#
# Runs the APT and Flatpak computations in child processes (with timeouts),
# after refreshing the package lists without a password.
#
# Copyright (C) 2026 Studio Hastag <contact@hastag.fr>
# SPDX-License-Identifier: GPL-3.0-or-later

import contextlib
import fcntl
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field

from mythicosupdate import constants, logutil


@dataclass
class CheckResult:
    refresh_error: str = ""           # apt update failed (message)
    refresh_kind: str = ""            # "network", "locked", "other", ""
    lock_holder: str = ""
    apt: dict = field(default_factory=dict)
    apt_error: str = ""
    flatpak: list = field(default_factory=list)
    flatpak_status: str = "ok"        # ok / unavailable / error
    flatpak_error: str = ""

    @property
    def priority(self):
        return bool(self.apt.get("priority"))

    @property
    def apt_updates(self):
        return self.apt.get("updates", [])

    @property
    def flatpak_updates(self):
        return [] if self.priority else self.flatpak

    @property
    def count(self):
        return len(self.apt_updates) + len(self.flatpak_updates)

    @property
    def has_error(self):
        return bool(self.refresh_error or self.apt_error or self.flatpak_error)


def _child_env():
    env = dict(os.environ)
    path = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = constants.LIBDIR + (os.pathsep + path if path else "")
    return env


LOCK_RETRIES = 12          # a busy package manager is retried for about a minute
LOCK_RETRY_DELAY = 5       # seconds


@contextlib.contextmanager
def _one_refresh_at_a_time(timeout=240):
    """The tray icon and the window both refresh the package lists: make them
    take turns instead of fighting over the APT lock."""
    handle = open(os.path.join(constants.runtime_dir(), "refresh.lock"), "a")
    deadline = time.monotonic() + timeout
    locked = False
    try:
        while not locked:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError:
                if time.monotonic() > deadline:
                    break
                time.sleep(0.5)
        yield
    finally:
        if locked:
            fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


def refresh_package_lists():
    """Refresh the package lists. Right after the login (or while another
    tool is installing something) APT is often busy: wait and try again
    instead of reporting an error straight away.
    Returns (error_message, kind); error_message is "" on success."""
    with _one_refresh_at_a_time():
        for attempt in range(LOCK_RETRIES + 1):
            message, kind = _refresh_once()
            if kind != "locked" or attempt == LOCK_RETRIES:
                return message, kind
            time.sleep(LOCK_RETRY_DELAY)
    return "", ""


def _refresh_once():
    """One attempt, through the sudoers rule (no password)."""
    try:
        result = subprocess.run(["sudo", "-n", constants.REFRESH_CACHE],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=constants.REFRESH_TIMEOUT, text=True)
    except subprocess.TimeoutExpired:
        return "Timed out while refreshing the package lists.", "network"
    except OSError as error:
        return str(error), "other"
    if result.returncode == 0:
        for line in (result.stderr or "").splitlines():
            if "ignored failure" in line:
                logutil.info(line.strip())
        return "", ""
    message = (result.stderr or result.stdout or "").strip()
    if result.returncode == constants.EXIT_LOCKED:
        return message, "locked"
    if result.returncode == constants.EXIT_FAILED and "sudo" in message and "password" in message:
        return ("The permission to refresh the package lists is missing "
                "(sudoers rule of mythicos-update): %s" % message), "other"
    return message or "mythicos-refresh-cache exited with code %d" % result.returncode, "network"


def run_apt_check():
    """Returns (dict, error). The dict is the aptcheck JSON."""
    try:
        completed = subprocess.run([sys.executable or "/usr/bin/python3", "-m", "mythicosupdate.aptcheck"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   timeout=120, text=True, env=_child_env())
        if completed.returncode != 0:
            return {}, (completed.stderr.strip() or "aptcheck exited with code %d" % completed.returncode)
        return json.loads(completed.stdout), ""
    except subprocess.TimeoutExpired:
        return {}, "Timed out while computing the list of updates."
    except (OSError, ValueError) as error:
        return {}, str(error)


def run_flatpak_check():
    """Returns (status, updates, error)."""
    try:
        completed = subprocess.run([sys.executable or "/usr/bin/python3", "-m", "mythicosupdate.flatpak_worker"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   timeout=constants.FLATPAK_FETCH_TIMEOUT, text=True, env=_child_env())
        data = json.loads(completed.stdout or "{}")
    except subprocess.TimeoutExpired:
        return "error", [], "Timed out while checking for Flatpak updates."
    except (OSError, ValueError) as error:
        return "error", [], str(error)
    status = data.get("status", "error")
    if status == "ok":
        return "ok", data.get("updates", []), ""
    if status == "unavailable":
        return "unavailable", [], ""
    return "error", [], data.get("message", "unknown error")


def check(refresh=True):
    """Full check. Never reports 'nothing to do' after an error: the caller
    must look at has_error before concluding that the system is up to date."""
    result = CheckResult()
    if refresh:
        result.refresh_error, result.refresh_kind = refresh_package_lists()
        if result.refresh_error:
            logutil.error("Refreshing the package lists failed (%s): %s"
                          % (result.refresh_kind, result.refresh_error))
            if result.refresh_kind == "locked":
                from mythicosupdate import locks
                result.lock_holder = (locks.check_locked(include_lists=True)
                                      or locks.holder_from_apt_message(result.refresh_error) or "")
            return result

    result.apt, result.apt_error = run_apt_check()
    if not result.apt_error and result.apt.get("error") and result.apt["error"] != "broken":
        result.apt_error = result.apt["error"]
    if result.apt_error:
        logutil.error("Computing APT updates failed: %s" % result.apt_error)

    result.flatpak_status, result.flatpak, result.flatpak_error = run_flatpak_check()
    if result.flatpak_error:
        logutil.error("Checking Flatpak updates failed: %s" % result.flatpak_error)
    return result
