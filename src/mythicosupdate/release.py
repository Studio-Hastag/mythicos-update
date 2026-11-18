# MythicOS Update Manager - new MythicOS release detection
#
# Derived from mintupdate (mintUpdate.py, release upgrade check)
# Copyright (C) 2007-2015 Clement Lefebvre <root@linuxmint.com>
# Copyright (C) 2026 Studio Hastag <contact@hastag.fr>
# SPDX-License-Identifier: GPL-3.0-or-later

import configparser
import os
from dataclasses import dataclass

from mythicosupdate import constants, logutil


@dataclass
class ReleaseCheck:
    available: bool = False
    target_name: str = ""
    codename: str = ""
    # Set when a file could not be read: shown as a discreet indicator.
    problem: str = ""


def parse_info_file(path):
    """Parse a KEY=VALUE file like /etc/mythicos/info."""
    values = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def check_new_release(info_file=None, upgrade_info_dir=None):
    info_file = info_file or constants.INFO_FILE
    upgrade_info_dir = upgrade_info_dir or constants.UPGRADE_INFO_DIR
    result = ReleaseCheck()

    # A missing file means "up to date", as requested.
    if not os.path.exists(info_file):
        return result
    try:
        values = parse_info_file(info_file)
    except (OSError, UnicodeDecodeError) as error:
        logutil.error("Cannot read %s: %s" % (info_file, error))
        result.problem = "%s: %s" % (info_file, error)
        return result

    codename = values.get("CODENAME", "").strip().lower()
    if not codename:
        return result
    result.codename = codename

    rel_info = os.path.join(upgrade_info_dir, codename, "info")
    if not os.path.exists(rel_info):
        return result
    config = configparser.ConfigParser()
    try:
        with open(rel_info, encoding="utf-8") as handle:
            config.read_file(handle)
    except (OSError, UnicodeDecodeError, configparser.Error) as error:
        logutil.error("Cannot read %s: %s" % (rel_info, error))
        result.problem = "%s: %s" % (rel_info, error)
        return result

    result.available = True
    result.target_name = config.get("general", "target_name", fallback="")
    editions = config.get("general", "editions", fallback="")
    edition = values.get("EDITION", "").strip().lower()
    if editions and edition and edition not in [e.strip().lower() for e in editions.split(",")]:
        # Not hidden: the presence of the file is what counts. Logged so that
        # a mismatching EDITION value is noticed by the maintainers.
        logutil.info("Edition %r is not listed in %s (editions=%s)" % (edition, rel_info, editions))
    return result
