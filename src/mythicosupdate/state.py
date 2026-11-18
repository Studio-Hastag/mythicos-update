# MythicOS Update Manager - state shared between the window and the tray icon
#
# The window and the tray icon are separate processes. The window writes its
# current state to a small JSON file in $XDG_RUNTIME_DIR, which the tray icon
# watches to update its icon.
#
# Copyright (C) 2026 Studio Hastag <contact@hastag.fr>
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import os
import time

from mythicosupdate import constants

CHECKING = "checking"
UP_TO_DATE = "up-to-date"
UPDATES = "updates-available"
INSTALLING = "installing"
ERROR = "error"
ALL = (CHECKING, UP_TO_DATE, UPDATES, INSTALLING, ERROR)

FILE_NAME = "state.json"


def state_path():
    return os.path.join(constants.runtime_dir(), FILE_NAME)


def write(state, count=0, message="", source="window"):
    if state not in ALL:
        raise ValueError(state)
    payload = {"state": state, "count": int(count), "message": message,
               "source": source, "time": int(time.time()), "pid": os.getpid()}
    path = state_path()
    tmp = "%s.%d.tmp" % (path, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        os.replace(tmp, path)
    except OSError:
        pass


def read():
    try:
        with open(state_path(), encoding="utf-8") as handle:
            data = json.load(handle)
        if data.get("state") in ALL:
            return data
    except (OSError, ValueError):
        pass
    return None
