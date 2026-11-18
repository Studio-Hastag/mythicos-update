# MythicOS Update Manager - tray icon (separate process)
#
# XApp.StatusIcon only exists for GTK 3, so the tray icon lives in its own
# small process; the GTK 4 window never imports XApp. It checks for updates
# 1 minute after login (configurable), then every 2 hours, and follows the
# state of the window through mythicosupdate.state.
#
# Derived from mintupdate (mintUpdate.py: status icon and menu)
# Copyright (C) 2007-2015 Clement Lefebvre <root@linuxmint.com>
# Copyright (C) 2026 Studio Hastag <contact@hastag.fr>
# SPDX-License-Identifier: GPL-3.0-or-later

import subprocess
import sys
import threading

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("XApp", "1.0")
from gi.repository import Gio, GLib, Gtk, XApp

from mythicosupdate import checker, logutil, state
from mythicosupdate.i18n import _
from mythicosupdate.settings import Settings

ICONS = {state.CHECKING: "mythicos-update-checking-symbolic",
         state.UP_TO_DATE: "mythicos-update-up-to-date-symbolic",
         state.UPDATES: "mythicos-update-updates-available-symbolic",
         state.INSTALLING: "mythicos-update-installing-symbolic",
         state.ERROR: "mythicos-update-error-symbolic"}


class Tray:
    def __init__(self):
        self.settings = Settings()
        self.checking = False
        self.timer_id = 0
        self.current = None

        self.icon = XApp.StatusIcon()
        menu = Gtk.Menu()
        for label, callback in ((_("Update Manager"), self.open_window),
                                (_("Refresh"), lambda *_a: self.check()),
                                (_("Quit"), lambda *_a: Gtk.main_quit())):
            item = Gtk.MenuItem(label=label)
            item.connect("activate", callback)
            menu.append(item)
        menu.show_all()
        self.icon.set_secondary_menu(menu)
        self.icon.connect("activate", lambda *_a: self.open_window())
        self.set_state(state.CHECKING, 0, "")
        self.icon.set_visible(True)

        # Follow the window
        self.monitor = Gio.File.new_for_path(state.state_path()).get_parent().monitor_directory(
            Gio.FileMonitorFlags.NONE, None)
        self.monitor.connect("changed", self.on_state_file_changed)
        self.settings.connect_changed(lambda key: self.schedule(first=False))
        self.schedule(first=True)

    def open_window(self, *_args):
        subprocess.Popen(["/usr/bin/mythicos-update"])

    def set_state(self, name, count, message):
        self.current = name
        tooltips = {state.CHECKING: _("Checking for updates"),
                    state.UP_TO_DATE: _("Your system is up to date"),
                    state.UPDATES: _("Updates are available") + (": %d" % count if count else ""),
                    state.INSTALLING: _("Installing updates"),
                    state.ERROR: message or _("Could not refresh the list of updates")}
        self.icon.set_icon_name(ICONS[name])
        self.icon.set_tooltip_text(tooltips[name])

    def on_state_file_changed(self, _monitor, _file, _other, _event):
        data = state.read()
        if data and data.get("source") == "window":
            self.set_state(data["state"], data.get("count", 0), data.get("message", ""))
        return False

    def schedule(self, first):
        if self.timer_id:
            GLib.source_remove(self.timer_id)
        if first:
            delay = self.settings.get_int("first-refresh-minutes") * 60
        else:
            delay = self.settings.get_int("refresh-interval-minutes") * 60
        self.timer_id = GLib.timeout_add_seconds(max(delay, 30), self.on_timer)

    def on_timer(self):
        self.timer_id = 0
        self.check()
        self.schedule(first=False)
        return False

    def check(self):
        data = state.read()
        if self.checking or (data and data["state"] == state.INSTALLING
                             and data.get("source") == "window"):
            return
        self.checking = True
        self.set_state(state.CHECKING, 0, "")
        threading.Thread(target=self._check_thread, daemon=True).start()

    def _check_thread(self):
        result = checker.check(refresh=True)
        GLib.idle_add(self._check_done, result)

    def _check_done(self, result):
        self.checking = False
        if result.refresh_kind == "locked":
            # Another tool is using APT (typical right after the login): not
            # an error. Try again in two minutes, keeping the current icon.
            logutil.info("The package manager is busy, trying again in 2 minutes")
            GLib.timeout_add_seconds(120, lambda: self.check() or False)
            return False
        if result.has_error and result.count == 0:
            message = (result.refresh_error or result.apt_error or result.flatpak_error).strip()
            self.set_state(state.ERROR, 0, message.splitlines()[0] if message else "")
        elif result.count > 0:
            self.set_state(state.UPDATES, result.count, "")
        else:
            self.set_state(state.UP_TO_DATE, 0, "")
        state.write(self.current, count=result.count, source="tray")
        return False


def main():
    try:
        import xapp.os
        if xapp.os.is_live_session() or xapp.os.is_guest_session():
            return 0
    except Exception as error:
        logutil.info("Could not detect a live or guest session: %s" % error)
    Tray()
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
