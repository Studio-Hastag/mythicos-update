# MythicOS Update Manager - GSettings access
#
# Copyright (C) 2026 Studio Hastag <contact@hastag.fr>
# SPDX-License-Identifier: GPL-3.0-or-later

from gi.repository import Gio

from mythicosupdate.constants import APP_ID

DEFAULTS = {"first-refresh-minutes": 1, "refresh-interval-minutes": 120}


class Settings:
    """Thin wrapper that keeps working with defaults when the schema is not
    installed (for instance when running from a source checkout)."""

    def __init__(self):
        self._settings = None
        source = Gio.SettingsSchemaSource.get_default()
        if source is not None and source.lookup(APP_ID, True) is not None:
            self._settings = Gio.Settings.new(APP_ID)

    def get_int(self, key):
        if self._settings is None:
            return DEFAULTS[key]
        return self._settings.get_int(key)

    def set_int(self, key, value):
        if self._settings is not None:
            self._settings.set_int(key, int(value))

    def connect_changed(self, callback):
        if self._settings is not None:
            self._settings.connect("changed", lambda _s, key: callback(key))
