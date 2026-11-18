# MythicOS Update Manager - package manager lock detection
#
# Derived from mintupdate (dpkg_lock_check.sh and mintUpdate.py:dpkg_locked)
# Copyright (C) 2007-2015 Clement Lefebvre <root@linuxmint.com>
# Copyright (C) 2026 Studio Hastag <contact@hastag.fr>
# SPDX-License-Identifier: GPL-3.0-or-later

import subprocess

from mythicosupdate import constants

LOCKED_EXIT_CODE = 3


def holder_from_apt_message(text):
    """Extract 'name (pid)' from an apt/dpkg 'Could not get lock' message."""
    import re
    match = re.search(r"held by process (\d+) \(([^)]+)\)", text or "")
    if match:
        return "%s (%s)" % (match.group(2), match.group(1))
    if re.search(r"Could not get lock|Unable to acquire the dpkg frontend lock|"
                 r"Unable to lock directory", text or ""):
        return ""
    return None


def check_locked(include_lists=False):
    """Return None if the package manager is free (or if we cannot tell),
    otherwise a string naming the process holding the lock (possibly '')."""
    try:
        result = subprocess.run(["sudo", "-n", constants.LOCK_CHECK] + (["lists"] if include_lists else []),
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                timeout=20, text=True)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != LOCKED_EXIT_CODE:
        return None
    names = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line and line not in names:
            names.append(line)
    return ", ".join(names)
