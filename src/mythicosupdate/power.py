# MythicOS Update Manager - power state helpers (UPower over D-Bus)
#
# Derived from mintupdate (usr/lib/linuxmint/mintUpdate/util.py)
# Copyright (C) 2007-2015 Clement Lefebvre <root@linuxmint.com>
# Copyright (C) 2026 Studio Hastag <contact@hastag.fr>
# SPDX-License-Identifier: GPL-3.0-or-later

from gi.repository import Gio, GLib


def _get_upower_property(path, iface, name):
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    ret = bus.call_sync("org.freedesktop.UPower", path,
                        "org.freedesktop.DBus.Properties", "Get",
                        GLib.Variant("(ss)", (iface, name)), GLib.VariantType("(v)"),
                        Gio.DBusCallFlags.NONE, 2000, None)
    return ret.unpack()[0]


def on_battery():
    """False if UPower is unavailable (assume AC power)."""
    try:
        return bool(_get_upower_property("/org/freedesktop/UPower",
                                         "org.freedesktop.UPower", "OnBattery"))
    except GLib.Error:
        return False


def battery_percentage():
    path = "/org/freedesktop/UPower/devices/DisplayDevice"
    iface = "org.freedesktop.UPower.Device"
    try:
        if not _get_upower_property(path, iface, "IsPresent"):
            return None
        return _get_upower_property(path, iface, "Percentage")
    except GLib.Error:
        return None
