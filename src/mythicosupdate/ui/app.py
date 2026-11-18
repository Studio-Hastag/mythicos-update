# MythicOS Update Manager - application
#
# Copyright (C) 2026 Studio Hastag <contact@hastag.fr>
# SPDX-License-Identifier: GPL-3.0-or-later

import sys

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib

from mythicosupdate import __version__, constants
from mythicosupdate.i18n import _
from mythicosupdate.ui.window import MainWindow


class Application(Adw.Application):
    def __init__(self):
        super().__init__(application_id=constants.APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        GLib.set_application_name(_("Update Manager"))
        GLib.set_prgname(constants.APP_ID)
        self.window = None

    def do_activate(self):
        if self.window is None:
            self.window = MainWindow(self)
            self.window.present()
            self.window.start_check(True)
        else:
            self.window.present()

    def release_for_restart(self):
        """Drop the D-Bus name so that the re-executed process can take it."""
        self.quit_on_restart = True


def main():
    return Application().run(sys.argv)
