# MythicOS Update Manager - desktop session helpers
#
# Reboot handling derived from mintupdate (mintUpdate.py:_on_infobar_reboot)
# Copyright (C) 2007-2015 Clement Lefebvre <root@linuxmint.com>
# Copyright (C) 2026 Studio Hastag <contact@hastag.fr>
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import shutil
import subprocess

from mythicosupdate import constants


def reboot_required():
    return any(os.path.exists(path) for path in constants.REBOOT_REQUIRED_FILES)


def restart_computer():
    session = os.environ.get("XDG_CURRENT_DESKTOP", "")
    if session in ("Cinnamon", "X-Cinnamon") and shutil.which("cinnamon-session-quit"):
        cmd = ["cinnamon-session-quit", "--reboot"]
    elif session == "MATE":
        cmd = ["dbus-send", "--dest=org.gnome.SessionManager", "--type=method_call",
               "/org/gnome/SessionManager", "org.gnome.SessionManager.RequestReboot"]
    elif session == "XFCE" and shutil.which("xfce4-session-logout"):
        cmd = ["xfce4-session-logout", "--reboot"]
    else:
        cmd = ["systemctl", "reboot"]
    subprocess.Popen(cmd)


def sources_available():
    return shutil.which(constants.SOURCES_COMMAND) is not None


def upgrade_available():
    return shutil.which(constants.UPGRADE_COMMAND) is not None


def format_size(size):
    size = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1000 or unit == "GB":
            return ("%d %s" % (size, unit)) if unit == "B" else ("%.1f %s" % (size, unit))
        size /= 1000.0
