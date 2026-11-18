# MythicOS Update Manager - shared constants
#
# Copyright (C) 2026 Studio Hastag <contact@hastag.fr>
# SPDX-License-Identifier: GPL-3.0-or-later

import os

APP_ID = "fr.hastag.MythicOSUpdate"
GETTEXT_DOMAIN = "mythicos-update"
LOCALE_DIR = "/usr/share/locale"

LIBDIR = "/usr/lib/mythicos-update"
HELPER = "/usr/bin/mythicos-update-helper"
REFRESH_CACHE = "/usr/bin/mythicos-refresh-cache"
LOCK_CHECK = LIBDIR + "/lock-check.sh"
AUTOMATION_TOOL = "/usr/bin/mythicos-update-automation"

# These updates take priority over every other update: when one of them is
# available nothing else is offered, so that the manager itself is never
# outdated while it updates the rest of the system.
PRIORITY_UPDATES = ["mythicos-update", "mythicos-upgrade-info"]

# Kernel flavours recognised when grouping kernel packages (from Linux Mint).
SUPPORTED_KERNEL_TYPES = ["-generic", "-lowlatency", "-aws", "-azure", "-gcp",
                          "-kvm", "-oem", "-oracle"]
SOURCE_PACKAGE_NAME_OVERRIDES = ["linux-libc-dev"]

# MythicOS release information
INFO_FILE = "/etc/mythicos/info"
UPGRADE_INFO_DIR = "/usr/share/mythicos-upgrade-info"
UPGRADE_COMMAND = "mythicos-upgrade"
SOURCES_COMMAND = "mythicos-sources"

REBOOT_REQUIRED_FILES = ["/run/reboot-required", "/var/run/reboot-required"]

# Logs and persistent data (written by root)
ROOT_LOG_FILE = "/var/log/mythicos-update.log"
ROOT_HISTORY_FILE = "/var/log/mythicos-update-history.jsonl"
APT_HISTORY_LOG = "/var/log/apt/history.log"
AUTOMATION_FLAG = "/var/lib/mythicos-update/automatic-upgrades-enabled"

DPKG_UPDATES_DIR = "/var/lib/dpkg/updates"
APT_ARCHIVES_DIR = "/var/cache/apt/archives"

# Exit codes of mythicos-update-helper / mythicos-refresh-cache.
# pkexec itself uses 126 (dialog dismissed) and 127 (not authorized).
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_NOT_ROOT = 2
EXIT_LOCKED = 10
EXIT_DISK_FULL = 11
EXIT_APT_FAILED = 12
EXIT_FLATPAK_FAILED = 13
EXIT_BAD_ARGUMENTS = 14
EXIT_REPAIR_FAILED = 15
EXIT_UNEXPECTED_REMOVAL = 16
EXIT_PKEXEC_DISMISSED = 126
EXIT_PKEXEC_DENIED = 127

# Prefix of machine-readable lines the helper prints on stdout.
PROTOCOL_PREFIX = "@@MYTHICOS "

# Timings
FLATPAK_FETCH_TIMEOUT = 90          # seconds
FLATPAK_STALL_TIMEOUT = 10 * 60     # no output and no disk/network activity for this long: give up
FLATPAK_TOTAL_TIMEOUT = 2 * 60 * 60
APT_TOTAL_TIMEOUT = 4 * 60 * 60
REFRESH_TIMEOUT = 240
DISK_SAFETY_MARGIN = 100 * 1024 * 1024


def runtime_dir():
    """Per-user runtime directory shared by the window and the tray icon."""
    base = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    path = os.path.join(base, "mythicos-update")
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def user_state_dir():
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    path = os.path.join(base, "mythicos-update")
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path
