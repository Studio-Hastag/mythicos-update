# MythicOS Update Manager - Flatpak update lister (child process)
#
# Run as: python3 -m mythicosupdate.flatpak_worker
# Prints one JSON document on stdout:
#   {"status": "ok", "updates": [...]}     updates available (may be empty)
#   {"status": "unavailable"}              Flatpak is not installed
#   {"status": "error", "message": "..."}
#
# Runs without root and without GTK, in its own process so that the caller
# can enforce a timeout. Only the system-wide installation is considered,
# because that is the one the root helper updates.
#
# Copyright (C) 2026 Studio Hastag <contact@hastag.fr>
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import shutil
import sys


def list_updates():
    if shutil.which("flatpak") is None:
        return {"status": "unavailable"}
    try:
        import gi
        gi.require_version("Flatpak", "1.0")
        from gi.repository import Flatpak, GLib
    except (ImportError, ValueError):
        return {"status": "unavailable"}

    try:
        installation = Flatpak.Installation.new_system(None)
        refs = installation.list_installed_refs_for_update(None)
    except GLib.Error as error:
        return {"status": "error", "message": error.message}

    updates = []
    for ref in refs:
        kind = "app" if ref.get_kind() == Flatpak.RefKind.APP else "runtime"
        name = ref.get_name()
        entry = {"ref": ref.format_ref(), "id": name, "kind": kind,
                 "branch": ref.get_branch(), "origin": ref.get_origin(),
                 "display_name": name, "old_version": (ref.get_commit() or "")[:10],
                 "new_version": "", "size": 0}
        try:
            ref.load_appdata(None)
            display = ref.get_appdata_name()
            if display and kind == "app":
                entry["display_name"] = display
            version = ref.get_appdata_version()
            if version:
                entry["old_version"] = version
        except Exception:
            pass
        try:
            remote_ref = installation.fetch_remote_ref_sync(
                ref.get_origin(), ref.get_kind(), name, ref.get_arch(), ref.get_branch(), None)
            entry["new_version"] = (remote_ref.get_commit() or "")[:10]
            entry["size"] = int(remote_ref.get_download_size())
        except Exception:
            pass
        updates.append(entry)
    updates.sort(key=lambda item: (item["kind"] != "app", item["display_name"].lower()))
    return {"status": "ok", "updates": updates}


def main():
    try:
        print(json.dumps(list_updates()))
    except Exception as error:  # report, never crash silently
        print(json.dumps({"status": "error", "message": str(error)}))
        sys.exit(0)


if __name__ == "__main__":
    main()
