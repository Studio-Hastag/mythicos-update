# MythicOS Update Manager - logging
#
# Every message goes to journald (through syslog, identifier
# "mythicos-update") and to a log file: /var/log/mythicos-update.log when
# running as root, ~/.local/state/mythicos-update/update.log otherwise.
#
# Copyright (C) 2026 Studio Hastag <contact@hastag.fr>
# SPDX-License-Identifier: GPL-3.0-or-later

import datetime
import os
import sys
import syslog
import threading

from mythicosupdate import constants

_lock = threading.Lock()
_opened = False
_callbacks = []

MAX_USER_LOG_BYTES = 512 * 1024


def _open_syslog():
    global _opened
    if not _opened:
        syslog.openlog("mythicos-update", syslog.LOG_PID, syslog.LOG_DAEMON)
        _opened = True


def log_file_path():
    if os.getuid() == 0:
        return constants.ROOT_LOG_FILE
    return os.path.join(constants.user_state_dir(), "update.log")


def add_callback(callback):
    _callbacks.append(callback)


def _write(level, text):
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = "%s [%s] %s" % (stamp, "ERROR" if level == syslog.LOG_ERR else "INFO", text)
    with _lock:
        try:
            _open_syslog()
            syslog.syslog(level, text)
        except Exception:
            pass
        try:
            path = log_file_path()
            if os.getuid() != 0 and os.path.exists(path) and os.path.getsize(path) > MAX_USER_LOG_BYTES:
                os.replace(path, path + ".1")
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except Exception:
            # Logging must never break an update; the message is still on stderr.
            pass
        print(line, file=sys.stderr, flush=True)
        for callback in list(_callbacks):
            try:
                callback(line)
            except Exception:
                pass


def info(text):
    _write(syslog.LOG_INFO, text)


def error(text):
    _write(syslog.LOG_ERR, text)


def read_user_log(max_bytes=200 * 1024):
    try:
        with open(log_file_path(), "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes))
            return handle.read().decode("utf-8", "replace")
    except OSError:
        return ""
