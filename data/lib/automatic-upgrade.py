#!/usr/bin/python3
# MythicOS Update Manager - automatic updates (root, started by systemd).
#
# Installs the available APT updates and updates the system Flatpaks. It
# never removes packages: if an update would need a removal, it is skipped
# and left for the user to review in the Update Manager.
#
# Derived from mintupdate (system_automatic_upgrades.py)
# Copyright (C) 2007-2015 Clement Lefebvre <root@linuxmint.com>
# Copyright (C) 2026 Studio Hastag <contact@hastag.fr>
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import sys
import time

sys.path = [p for p in sys.path if p not in ("", ".")]
sys.path.insert(0, "/usr/lib/mythicos-update")

from mythicosupdate import aptcheck, constants, logutil, power, rootops  # noqa: E402

MIN_BATTERY_PERCENTAGE = 75


def main():
    if os.getuid() != 0:
        print("This command needs to be run as root.", file=sys.stderr)
        return constants.EXIT_NOT_ROOT
    if not os.path.exists(constants.AUTOMATION_FLAG):
        return 0

    logutil.info("Automatic update starting (%s)" % time.strftime("%a %d %b %Y %H:%M:%S %Z"))
    if power.on_battery():
        percentage = power.battery_percentage()
        if percentage is None or percentage < MIN_BATTERY_PERCENTAGE:
            logutil.info("On battery power and below %d%%, automatic update aborted"
                         % MIN_BATTERY_PERCENTAGE)
            return 0

    rootops.ignore_termination_signals()
    status = 0
    try:
        rootops.ensure_package_manager_free()
        for warning in rootops.refresh_package_lists():
            logutil.info("Ignored repository failure: %s" % warning)

        # At most two rounds: the first one may only update the manager itself.
        for _round in range(2):
            result = aptcheck.compute()
            if result.get("error"):
                raise rootops.OperationError(constants.EXIT_APT_FAILED, "apt-failed",
                                             detail=result.get("broken") or result["error"])
            names = []
            for update in result["updates"]:
                names.extend(update["package_names"])
            if not names:
                break
            if result["removed"]:
                logutil.info("Skipping the automatic installation: it would remove %s"
                             % ", ".join(item["name"] for item in result["removed"]))
                break
            rootops.apt_upgrade(names, allowed_removals=())
            if not result["priority"]:
                break
        rootops.flatpak_update(source="automatic")
    except rootops.OperationError as error:
        logutil.error("Automatic update failed: %s %s" % (error.event, error.details))
        status = error.code
    except Exception as error:
        logutil.error("Automatic update failed: %r" % (error,))
        status = constants.EXIT_FAILED
    logutil.info("Automatic update finished")
    return status


if __name__ == "__main__":
    sys.exit(main())
