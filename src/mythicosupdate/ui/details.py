# MythicOS Update Manager - "Details" window
#
# Copyright (C) 2026 Studio Hastag <contact@hastag.fr>
# SPDX-License-Identifier: GPL-3.0-or-later

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from mythicosupdate.i18n import _
from mythicosupdate.session import format_size


def _row(title, subtitle="", suffix=""):
    row = Adw.ActionRow(title=GLibEscape(title), subtitle=GLibEscape(subtitle))
    row.set_subtitle_selectable(True)
    if suffix:
        label = Gtk.Label(label=suffix)
        label.add_css_class("dim-label")
        row.add_suffix(label)
    return row


def GLibEscape(text):
    from gi.repository import GLib
    return GLib.markup_escape_text(text or "")


def _group(page, title):
    group = Adw.PreferencesGroup(title=title)
    page.add(group)
    return group


class DetailsWindow(Adw.Window):
    def __init__(self, parent, result):
        super().__init__(transient_for=parent, modal=True, default_width=520, default_height=560)
        self.set_title(_("Details"))
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        page = Adw.PreferencesPage()
        view.set_content(page)
        self.set_content(view)

        apt = result.apt
        updates = apt.get("updates", [])
        by_type = {"security": [], "kernel": [], "package": []}
        for update in updates:
            by_type.setdefault(update["type"] if update["type"] in by_type else "package", []).append(update)
        for key, title in (("security", _("Security updates")), ("kernel", _("Kernel updates")),
                           ("package", _("Software updates"))):
            if by_type[key]:
                group = _group(page, title)
                for update in by_type[key]:
                    group.add(_row(update["display_name"],
                                   "%s → %s" % (update["old_version"] or "?", update["new_version"]),
                                   format_size(update["size"])))

        if apt.get("new"):
            group = _group(page, _("New packages"))
            for item in apt["new"]:
                group.add(_row(item["name"], item["version"], format_size(item.get("size", 0))))
        if apt.get("removed"):
            group = _group(page, _("Packages to remove"))
            for item in apt["removed"]:
                group.add(_row(item["name"], item["version"]))
        if apt.get("held"):
            group = _group(page, _("Packages kept back"))
            reasons = {"hold": _("Marked as held (apt-mark hold)"),
                       "phased": _("Phased update, rolled out gradually"),
                       "kept-back": _("Kept back by APT")}
            for item in apt["held"]:
                subtitle = "%s → %s · %s" % (item["installed"], item["candidate"],
                                              reasons.get(item["reason"], item["reason"]))
                group.add(_row(item["name"], subtitle))
        if apt.get("broken"):
            group = _group(page, _("Broken packages"))
            group.add(_row(_("APT could not find a consistent set of changes"), apt["broken"]))
        if result.flatpak_updates:
            group = _group(page, _("Flatpak updates"))
            for item in result.flatpak_updates:
                subtitle = item["id"]
                if item.get("new_version"):
                    subtitle = "%s · %s → %s" % (item["id"], item.get("old_version") or "?", item["new_version"])
                group.add(_row(item["display_name"], subtitle, format_size(item.get("size", 0))))
