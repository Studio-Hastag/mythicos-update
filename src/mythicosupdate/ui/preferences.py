# MythicOS Update Manager - preferences dialog
#
# Copyright (C) 2026 Studio Hastag <contact@hastag.fr>
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib

from mythicosupdate import constants, logutil
from mythicosupdate.i18n import _
from mythicosupdate.settings import Settings


class PreferencesDialog(Adw.PreferencesDialog):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.settings = Settings()
        self._busy = False
        self.set_title(_("Preferences"))

        page = Adw.PreferencesPage()
        self.add(page)

        automation = Adw.PreferencesGroup(title=_("Automation"))
        page.add(automation)
        self.auto_row = Adw.SwitchRow(title=_("Apply updates automatically"),
                                      subtitle=_("Performed as root on a daily basis"))
        self.auto_row.set_active(os.path.exists(constants.AUTOMATION_FLAG))
        self.auto_row.connect("notify::active", self._on_auto_toggled)
        automation.add(self.auto_row)

        refresh = Adw.PreferencesGroup(title=_("Auto-refresh"))
        page.add(refresh)
        self.first_row = self._spin(_("First, refresh the list of updates after:"),
                                    "first-refresh-minutes", 1, 1440)
        self.every_row = self._spin(_("Then, refresh the list of updates every:"),
                                    "refresh-interval-minutes", 10, 10080)
        refresh.add(self.first_row)
        refresh.add(self.every_row)

    def _spin(self, title, key, low, high):
        row = Adw.SpinRow.new_with_range(low, high, 1)
        row.set_title(title)
        row.set_subtitle(_("minutes"))
        row.set_value(self.settings.get_int(key))
        row.connect("notify::value", lambda r, _p: self.settings.set_int(key, r.get_value()))
        return row

    def _on_auto_toggled(self, row, _param):
        if self._busy:
            return
        enable = row.get_active()
        if enable == os.path.exists(constants.AUTOMATION_FLAG):
            return
        self._busy = True
        self.auto_row.set_sensitive(False)
        threading.Thread(target=self._run_automation, args=(enable,), daemon=True).start()

    def _run_automation(self, enable):
        import subprocess
        try:
            code = subprocess.run(["pkexec", constants.AUTOMATION_TOOL,
                                   "enable" if enable else "disable"]).returncode
        except OSError as error:
            logutil.error("Cannot run pkexec: %s" % error)
            code = 1
        GLib.idle_add(self._automation_done, enable, code)

    def _automation_done(self, enable, code):
        self._busy = False
        actual = os.path.exists(constants.AUTOMATION_FLAG)
        if code != 0 and code not in (126,):
            logutil.error("Changing automatic updates failed with code %d" % code)
            self.window.toast(_("Could not change the automatic updates setting."))
        self.auto_row.set_sensitive(True)
        if self.auto_row.get_active() != actual:
            self._busy = True
            self.auto_row.set_active(actual)
            self._busy = False
        return False
