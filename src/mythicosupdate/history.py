# MythicOS Update Manager - update history
#
# Combines /var/log/apt/history.log* (what APT really did) with the run
# summaries written by the root helper (Flatpak and automatic runs).
#
# Copyright (C) 2026 Studio Hastag <contact@hastag.fr>
# SPDX-License-Identifier: GPL-3.0-or-later

import glob
import gzip
import json
import re
from dataclasses import dataclass, field

from mythicosupdate import constants

_PACKAGE_RE = re.compile(r"(\S+) \(([^,)]*)(?:, ([^)]*))?\)")


@dataclass
class HistoryEntry:
    date: str                      # "YYYY-MM-DD HH:MM:SS"
    source: str                    # apt / flatpak / automatic
    result: str                    # ok / failed
    items: list = field(default_factory=list)   # (name, old, new, action)


def _open(path):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return open(path, encoding="utf-8", errors="replace")


def parse_apt_history_text(text):
    entries = []
    for block in text.split("\n\n"):
        start = None
        items = []
        for line in block.splitlines():
            if line.startswith("Start-Date:"):
                start = line.split(":", 1)[1].strip()
                continue
            for key, action in (("Upgrade", "upgrade"), ("Install", "install"), ("Remove", "remove"),
                                ("Purge", "remove"), ("Downgrade", "downgrade")):
                if line.startswith(key + ":"):
                    for name, old, new in _PACKAGE_RE.findall(line.split(":", 1)[1]):
                        if action == "install":
                            items.append((name, "", old.split(",")[0], action))
                        elif action == "remove":
                            items.append((name, old, "", action))
                        else:
                            items.append((name, old, new, action))
        if start and items:
            date = start.replace("  ", " ")
            # "2026-11-12  10:00:00" -> "2026-11-12 10:00:00"
            entries.append(HistoryEntry(date=date, source="apt", result="ok", items=items))
    return entries


def read_apt_history(limit_files=6):
    entries = []
    paths = sorted(glob.glob(constants.APT_HISTORY_LOG + "*"))
    for path in paths[:limit_files]:
        try:
            with _open(path) as handle:
                entries.extend(parse_apt_history_text(handle.read()))
        except OSError:
            continue
    return entries


def read_helper_history():
    entries = []
    try:
        with open(constants.ROOT_HISTORY_FILE, encoding="utf-8") as handle:
            for line in handle:
                try:
                    data = json.loads(line)
                except ValueError:
                    continue
                if data.get("source") not in ("flatpak", "automatic", "apt-failed"):
                    continue
                items = [(i.get("name", ""), i.get("old", ""), i.get("new", ""), i.get("action", "upgrade"))
                         for i in data.get("items", [])]
                entries.append(HistoryEntry(date=data.get("date", ""), source=data["source"],
                                            result=data.get("result", "ok"), items=items))
    except OSError:
        pass
    return entries


def load(limit=300):
    entries = read_apt_history() + read_helper_history()
    entries.sort(key=lambda entry: entry.date, reverse=True)
    return entries[:limit]
