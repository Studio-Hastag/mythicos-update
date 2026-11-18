# MythicOS Update Manager - update history window
#
# Copyright (C) 2026 Studio Hastag <contact@hastag.fr>
# SPDX-License-Identifier: GPL-3.0-or-later

import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from mythicosupdate import history, logutil
from mythicosupdate.i18n import _


class HistoryWindow(Adw.Window):
    def __init__(self, parent):
        super().__init__(transient_for=parent, modal=False, default_width=560, default_height=600)
        self.set_title(_("History of Updates"))
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        self.stack = Gtk.Stack()
        view.set_content(self.stack)
        self.set_content(view)
        spinner = Gtk.Spinner(spinning=True, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER, width_request=32, height_request=32)
        self.stack.add_named(spinner, "loading")
        self.page = Adw.PreferencesPage()
        self.stack.add_named(self.page, "list")
        self.empty = Adw.StatusPage(icon_name="document-open-recent-symbolic",
                                    title=_("No updates have been installed yet"))
        self.stack.add_named(self.empty, "empty")
        self.stack.set_visible_child_name("loading")
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        entries = history.load()
        GLib.idle_add(self._show, entries)

    MAX_ENTRIES = 150
    MAX_ITEMS = 200

    def _show(self, entries):
        try:
            self._fill(entries[:self.MAX_ENTRIES])
        except Exception as error:  # never take the window down
            logutil.error("Cannot display the history: %r" % (error,))
            self.empty.set_title(_("Could not read the history of updates"))
            self.empty.set_description(str(error))
            self.stack.set_visible_child_name("empty")
        return False

    def _fill(self, entries):
        if not entries:
            self.stack.set_visible_child_name("empty")
            return
        sources = {"apt": _("Software updates"), "flatpak": _("Flatpak updates"),
                   "automatic": _("Automatic updates"), "apt-failed": _("Software updates")}
        group = Adw.PreferencesGroup()
        self.page.add(group)
        for entry in entries:
            row = Adw.ExpanderRow(title=GLib.markup_escape_text(entry.date),
                                  subtitle=GLib.markup_escape_text(
                                      "%s · %d" % (sources.get(entry.source, entry.source), len(entry.items))))
            if entry.result != "ok":
                badge = Gtk.Label(label=_("Failed"))
                badge.add_css_class("error")
                row.add_suffix(badge)
            # The package rows are only created when the entry is expanded:
            # a full-system upgrade can contain hundreds of packages.
            row.connect("notify::expanded", self._on_expanded, entry)
            group.add(row)
        self.stack.set_visible_child_name("list")

    def _on_expanded(self, row, _param, entry):
        if not row.get_expanded() or getattr(row, "_filled", False):
            return
        row._filled = True
        for name, old, new, action in entry.items[:self.MAX_ITEMS]:
            if action == "install":
                detail = new
            elif action == "remove":
                detail = old
            else:
                detail = "%s → %s" % (old, new)
            row.add_row(Adw.ActionRow(title=GLib.markup_escape_text(name),
                                      subtitle=GLib.markup_escape_text(detail)))
        extra = len(entry.items) - self.MAX_ITEMS
        if extra > 0:
            row.add_row(Adw.ActionRow(title=GLib.markup_escape_text("… %d" % extra)))
