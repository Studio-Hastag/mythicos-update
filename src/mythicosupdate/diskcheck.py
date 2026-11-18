# MythicOS Update Manager - free disk space check
#
# Copyright (C) 2026 Studio Hastag <contact@hastag.fr>
# SPDX-License-Identifier: GPL-3.0-or-later

import os

from mythicosupdate import constants


def _free_bytes(path):
    stat = os.statvfs(path)
    return stat.f_bavail * stat.f_frsize


def missing_space(download_size, install_size, archives_dir=None, system_dir="/usr",
                  margin=None):
    """Return the number of bytes that are missing to download and unpack the
    updates (0 when there is enough room).

    download_size: bytes to fetch into the APT archive cache
    install_size:  net extra bytes needed on the system partition (may be <= 0)
    """
    archives_dir = archives_dir or constants.APT_ARCHIVES_DIR
    margin = constants.DISK_SAFETY_MARGIN if margin is None else margin
    install_size = max(int(install_size), 0)
    download_size = max(int(download_size), 0)
    try:
        same_device = os.stat(archives_dir).st_dev == os.stat(system_dir).st_dev
        if same_device:
            needed = download_size + install_size + margin
            return max(0, needed - _free_bytes(system_dir))
        missing = max(0, download_size + margin // 2 - _free_bytes(archives_dir))
        missing += max(0, install_size + margin // 2 - _free_bytes(system_dir))
        return missing
    except OSError:
        # If we cannot measure, do not block the installation: apt will fail
        # with its own explicit message if the disk really is full.
        return 0
