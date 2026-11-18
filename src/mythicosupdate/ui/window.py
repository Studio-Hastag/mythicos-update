# MythicOS Update Manager - main window (GTK 4 + libadwaita)
#
# Flow derived from mintupdate (mintUpdate.py) and Ubuntu update-manager.
# Copyright (C) 2007-2015 Clement Lefebvre <root@linuxmint.com>
# Copyright (C) 2026 Studio Hastag <contact@hastag.fr>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This window never imports XApp (it does not exist for GTK 4): the tray icon
# lives in its own process and follows the window through mythicosupdate.state.

import json
import os
import shutil
import sys
import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

from mythicosupdate import checker, constants, locks, logutil, release, session, state
from mythicosupdate.i18n import _
from mythicosupdate.ui.details import DetailsWindow
from mythicosupdate.ui.history_window import HistoryWindow
from mythicosupdate.ui.preferences import PreferencesDialog


class MainWindow(Adw.ApplicationWindow):

    def __init__(self, application):
        super().__init__(application=application, default_width=480, default_height=540)
        self.set_title(_("Update Manager"))
        self.result = None
        self.release_check = None
        self.installing = False
        self.busy_cookie = 0
        self.install_error = None
        self.install_priority = False
        self.process = None
        self.last_message = ""

        self.toasts = Adw.ToastOverlay()
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        view.add_top_bar(header)
        self.banner = Adw.Banner()
        view.add_top_bar(self.banner)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        view.set_content(self.stack)
        self.toasts.set_child(view)
        self.set_content(self.toasts)

        self._build_menu(header)
        self._build_pages()
        self.connect("close-request", self._on_close_request)

    # ------------------------------------------------------------ building

    def _build_menu(self, header):
        menu = Gio.Menu()
        menu.append(_("Refresh"), "win.refresh")
        menu.append(_("History of Updates"), "win.history")
        menu.append(_("Preferences"), "win.preferences")
        menu.append(_("About"), "win.about")
        button = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
        header.pack_end(button)
        for name, callback in (("refresh", lambda *_a: self.start_check(True)),
                               ("history", lambda *_a: HistoryWindow(self).present()),
                               ("preferences", lambda *_a: PreferencesDialog(self).present(self)),
                               ("about", lambda *_a: self._show_about())):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

    def _button(self, label, callback, suggested=False, tooltip=None):
        button = Gtk.Button(label=label)
        if suggested:
            button.add_css_class("suggested-action")
        button.add_css_class("pill")
        button.connect("clicked", callback)
        if tooltip:
            button.set_tooltip_text(tooltip)
        return button

    def _buttons_box(self, *buttons):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
                      halign=Gtk.Align.CENTER, homogeneous=False)
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=False,
                           max_children_per_line=4, halign=Gtk.Align.CENTER, column_spacing=8, row_spacing=8)
        for button in buttons:
            flow.append(button)
        return flow

    def _page(self, name, icon, title, description, *buttons, extra=None):
        status = Adw.StatusPage(icon_name=icon, title=title, description=description)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        if extra is not None:
            box.append(extra)
        if buttons:
            box.append(self._buttons_box(*buttons))
        status.set_child(box)
        self.stack.add_named(status, name)
        return status

    def _build_pages(self):
        # checking
        spinner = Gtk.Spinner(spinning=True, width_request=32, height_request=32)
        self.checking_page = self._page("checking", "mythicos-update-checking-symbolic",
                                        _("Checking for updates"), "", extra=spinner)

        # updates available
        self.summary_label = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
        self.summary_label.add_css_class("dim-label")
        self.install_button = self._button(_("Install"), self.on_install, suggested=True)
        self.settings_button = self._button(_("Settings"), self.on_settings)
        self.details_button = self._button(_("Details"), self.on_details)
        self.updates_page = self._page(
            "updates", "mythicos-update-updates-available-symbolic", _("Updates are available"),
            _("Updates are available. Do you want to install them?"),
            self.install_button, self._button(_("Later"), lambda *_a: self.close()),
            self.settings_button, self.details_button, extra=self.summary_label)

        # installing
        self.progress_bar = Gtk.ProgressBar(show_text=False)
        self.progress_label = Gtk.Label(label="", wrap=True)
        self.progress_label.add_css_class("dim-label")
        self.terminal_view = Gtk.TextView(editable=False, monospace=True, cursor_visible=False,
                                          wrap_mode=Gtk.WrapMode.WORD_CHAR)
        scroll = Gtk.ScrolledWindow(min_content_height=160, vexpand=True)
        scroll.set_child(self.terminal_view)
        expander = Gtk.Expander(label=_("Terminal"))
        expander.set_child(scroll)
        progress_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for widget in (self.progress_bar, self.progress_label, expander):
            progress_box.append(widget)
        self.progress_page = self._page("progress", "mythicos-update-installing-symbolic",
                                        _("Installing updates"), "", extra=progress_box)
        self.terminal_expander = expander

        # reboot
        self.reboot_page = self._page(
            "reboot", "system-reboot-symbolic", _("Restart required"),
            _("A restart is needed to finish applying the updates."),
            self._button(_("Restart"), lambda *_a: session.restart_computer(), suggested=True),
            self._button(_("Later"), lambda *_a: self.start_check(False)))

        # up to date
        self.uptodate_settings = self._button(_("Settings"), self.on_settings)
        self.problem_label = Gtk.Label(wrap=True, visible=False)
        self.problem_label.add_css_class("dim-label")
        self.uptodate_page = self._page(
            "uptodate", "mythicos-update-up-to-date-symbolic", _("Your system is up to date"), "",
            self.uptodate_settings, self._button(_("Close"), lambda *_a: self.close()),
            extra=self.problem_label)

        # new MythicOS version
        self.newversion_settings = self._button(_("Settings"), self.on_settings)
        self.newversion_page = self._page(
            "newversion", "mythicos-update-updates-available-symbolic", _("A new version of MythicOS is available"),
            _("Your software is up to date, but a new version of MythicOS is available. "
              "Do you want to install it?"),
            self._button(_("Later"), lambda *_a: self.close()),
            self._button(_("Upgrade"), self.on_upgrade, suggested=True), self.newversion_settings)

        # error
        self.error_text = Gtk.Label(wrap=True, selectable=True, xalign=0)
        self.error_text.add_css_class("monospace")
        error_scroll = Gtk.ScrolledWindow(min_content_height=90, max_content_height=160,
                                          propagate_natural_height=True)
        error_scroll.set_child(self.error_text)
        self.error_expander = Gtk.Expander(label=_("Details"))
        self.error_expander.set_child(error_scroll)
        self.retry_button = self._button(_("Retry"), lambda *_a: self.start_check(True), suggested=True)
        self.error_page = self._page("error", "mythicos-update-error-symbolic", "", "",
                                     self.retry_button, self._button(_("Close"), lambda *_a: self.close()),
                                     extra=self.error_expander)

        # interrupted installation
        self.repair_page = self._page(
            "repair", "mythicos-update-warning-symbolic", _("A previous installation was interrupted"),
            _("The package system must be repaired before anything new is installed."),
            self._button(_("Repair"), self.on_repair, suggested=True),
            self._button(_("Close"), lambda *_a: self.close()))

    # --------------------------------------------------------------- misc

    def toast(self, text):
        self.toasts.add_toast(Adw.Toast(title=text))

    def _show_about(self):
        from mythicosupdate import __version__
        about = Adw.AboutDialog(application_name=_("Update Manager"), application_icon=constants.APP_ID,
                                version=__version__, developer_name="Studio Hastag",
                                website="https://hastag.fr", license_type=Gtk.License.GPL_3_0,
                                copyright="© 2026 Studio Hastag\n© 2007-2015 Clement Lefebvre (mintupdate)\n"
                                          "© Canonical Ltd (update-manager)")
        about.present(self)

    def _on_close_request(self, _window):
        if self.installing:
            self.toast(_("Please wait until the installation has finished."))
            return True
        return False

    def _set_state(self, name, count=0, message=""):
        state.write(name, count=count, message=message)

    def show_error(self, title, description, detail="", retry=True):
        self.error_page.set_title(title)
        self.error_page.set_description(description)
        self.error_text.set_text(detail or "")
        self.error_expander.set_visible(bool(detail))
        self.retry_button.set_visible(retry)
        self.stack.set_visible_child_name("error")
        self._set_state(state.ERROR, message=title)
        logutil.error("%s - %s %s" % (title, description, (detail or "")[:300]))

    # ---------------------------------------------------------- checking

    def start_check(self, refresh=True):
        if self.installing:
            return
        self.banner.set_revealed(False)
        self.stack.set_visible_child_name("checking")
        self._set_state(state.CHECKING)
        threading.Thread(target=self._check_thread, args=(refresh,), daemon=True).start()

    def _check_thread(self, refresh):
        result = checker.check(refresh=refresh)
        GLib.idle_add(self._on_check_done, result)

    def _on_check_done(self, result):
        self.result = result
        apt = result.apt

        if result.refresh_error:
            if result.refresh_kind == "locked":
                holder = result.lock_holder
                self.show_error(_("Cannot Proceed"),
                                _("Another process is currently using the package management system. "
                                  "Please wait for it to finish and then try again.")
                                + ((" (%s)" % holder) if holder else ""), result.refresh_error)
            else:
                self.show_error(_("Could not refresh the list of updates"),
                                _("Check your Internet connection and try again."), result.refresh_error)
            return False
        if result.apt_error:
            self.show_error(_("Could not refresh the list of updates"), "", result.apt_error)
            return False
        if apt.get("error") == "broken":
            self.show_error(_("Broken packages"),
                            _("APT could not find a consistent set of changes. Nothing was installed."),
                            apt.get("broken", ""))
            return False
        if apt.get("needs_repair"):
            self._set_state(state.ERROR, message=_("A previous installation was interrupted"))
            self.stack.set_visible_child_name("repair")
            return False

        if result.count > 0:
            self._show_updates(result)
            return False

        if result.flatpak_error:
            self.show_error(_("Could not check for Flatpak updates"), "", result.flatpak_error)
            return False

        self._show_release_page()
        return False

    def _show_updates(self, result):
        apt = result.apt
        lines = []
        if result.priority:
            self.updates_page.set_description(
                _("A new version of the Update Manager is available")
                + "\n" + _("It will be installed first, then the other updates."))
        else:
            self.updates_page.set_description(_("Updates are available. Do you want to install them?"))
        lines.append(_("Updates to install: %d") % result.count)
        size = apt.get("download_size", 0) + sum(i.get("size", 0) for i in result.flatpak_updates)
        if size:
            lines.append(_("Download size: %s") % session.format_size(size))
        if apt.get("removed"):
            lines.append(_("Packages to remove: %d") % len(apt["removed"]))
        if apt.get("held"):
            lines.append(_("Packages kept back: %d") % len(apt["held"]))
        self.summary_label.set_text("\n".join(lines))
        self.settings_button.set_sensitive(session.sources_available())
        self.settings_button.set_tooltip_text(None if session.sources_available()
                                              else _("Software Sources is not installed."))
        if result.flatpak_error:
            self.banner.set_title(_("Error checking for flatpak updates: %s") % result.flatpak_error)
            self.banner.set_revealed(True)
        self.stack.set_visible_child_name("updates")
        self._set_state(state.UPDATES, count=result.count)

    def _show_release_page(self):
        self.release_check = release.check_new_release()
        info = self.release_check
        if info.available:
            description = _("Your software is up to date, but a new version of MythicOS is available. "
                            "Do you want to install it?")
            if info.target_name:
                description += "\n" + info.target_name
            self.newversion_page.set_description(description)
            self.newversion_settings.set_sensitive(session.sources_available())
            self.stack.set_visible_child_name("newversion")
        else:
            self.problem_label.set_visible(bool(info.problem))
            if info.problem:
                self.problem_label.set_text(_("Could not read %s") % info.problem)
            self.uptodate_settings.set_sensitive(session.sources_available())
            self.uptodate_settings.set_tooltip_text(None if session.sources_available()
                                                    else _("Software Sources is not installed."))
            self.stack.set_visible_child_name("uptodate")
        self._set_state(state.UP_TO_DATE)

    # ------------------------------------------------------------ buttons

    def on_details(self, _button):
        if self.result is not None:
            DetailsWindow(self, self.result).present()

    def on_settings(self, _button):
        if not session.sources_available():
            return
        try:
            process = Gio.Subprocess.new(["pkexec", constants.SOURCES_COMMAND], Gio.SubprocessFlags.NONE)
        except GLib.Error as error:
            logutil.error("Cannot start %s: %s" % (constants.SOURCES_COMMAND, error.message))
            self.toast(_("Could not start Software Sources."))
            return
        process.wait_async(None, lambda p, res: self._sources_closed(p, res))

    def _sources_closed(self, process, res):
        try:
            process.wait_finish(res)
        except GLib.Error:
            pass
        self.start_check(True)

    def on_upgrade(self, _button):
        if not session.upgrade_available():
            self.toast(_("The program %s is not installed.") % constants.UPGRADE_COMMAND)
            return
        try:
            Gio.Subprocess.new([constants.UPGRADE_COMMAND], Gio.SubprocessFlags.NONE)
        except GLib.Error as error:
            logutil.error("Cannot start %s: %s" % (constants.UPGRADE_COMMAND, error.message))
            self.toast(_("Could not start the upgrade."))
            return
        self.close()

    # ------------------------------------------------------------ install

    def on_install(self, _button):
        result = self.result
        if result is None:
            return
        self.install_button.set_sensitive(False)
        threading.Thread(target=self._preflight_thread, args=(result,), daemon=True).start()

    def _preflight_thread(self, result):
        holder = locks.check_locked()
        GLib.idle_add(self._preflight_done, result, holder)

    def _preflight_done(self, result, holder):
        self.install_button.set_sensitive(True)
        if holder is not None:
            self._alert(_("Cannot Proceed"),
                        _("Another process is currently using the package management system. "
                          "Please wait for it to finish and then try again.")
                        + ((" (%s)" % holder) if holder else ""))
            return False
        missing = result.apt.get("disk_missing", 0)
        if missing > 0:
            self._alert(_("Not enough free disk space"),
                        _("%s more free space is needed to install the updates.")
                        % session.format_size(missing))
            return False
        self._start_install(result)
        return False

    def _alert(self, heading, body):
        dialog = Adw.AlertDialog(heading=heading, body=body)
        dialog.add_response("ok", _("OK"))
        dialog.present(self)

    def _helper_command(self, result, repair_only=False):
        cmd = ["pkexec", constants.HELPER]
        if repair_only:
            return cmd + ["--repair-only"]
        names = []
        for update in result.apt_updates:
            names.extend(update["package_names"])
        if names:
            cmd += ["--apt"] + names
            removed = [item["name"] for item in result.apt.get("removed", [])]
            if removed:
                cmd += ["--allow-remove"] + removed
        if result.flatpak_updates:
            cmd.append("--flatpak")
        return cmd

    def _start_install(self, result, repair_only=False):
        self.installing = True
        self.install_error = None
        self.install_priority = result.priority and not repair_only
        self.terminal_view.get_buffer().set_text("")
        self.progress_bar.set_fraction(0)
        self.progress_label.set_text(_("Authentication is required to install updates"))
        self.stack.set_visible_child_name("progress")
        self._set_state(state.INSTALLING)
        app = self.get_application()
        self.busy_cookie = app.inhibit(self, Gtk.ApplicationInhibitFlags.LOGOUT
                                       | Gtk.ApplicationInhibitFlags.SUSPEND, _("Installing updates"))
        self._pulse_id = GLib.timeout_add(250, self._pulse)
        self._determinate = False
        self.tail = []
        cmd = self._helper_command(result, repair_only)
        logutil.info("Starting: %s" % " ".join(cmd))
        try:
            self.process = Gio.Subprocess.new(cmd, Gio.SubprocessFlags.STDOUT_PIPE
                                              | Gio.SubprocessFlags.STDERR_MERGE)
        except GLib.Error as error:
            self._install_finished(constants.EXIT_FAILED, error.message)
            return
        self.stream = Gio.DataInputStream.new(self.process.get_stdout_pipe())
        self.stream.read_line_async(GLib.PRIORITY_DEFAULT, None, self._on_line)
        self.process.wait_async(None, self._on_exit)

    def _pulse(self):
        if not self.installing:
            return False
        if not self._determinate:
            self.progress_bar.pulse()
        return True

    def _on_line(self, stream, res):
        try:
            line, _length = stream.read_line_finish_utf8(res)
        except GLib.Error:
            return
        if line is None:
            return
        self._handle_line(line)
        stream.read_line_async(GLib.PRIORITY_DEFAULT, None, self._on_line)

    def _handle_line(self, line):
        if line.startswith(constants.PROTOCOL_PREFIX):
            try:
                event = json.loads(line[len(constants.PROTOCOL_PREFIX):])
            except ValueError:
                return
            kind = event.get("event")
            if kind == "stage":
                labels = {"repair": _("Repairing the package system"),
                          "apt": _("Installing updates"),
                          "flatpak": _("Flatpak updates")}
                self._determinate = False
                self.progress_label.set_text(labels.get(event.get("name"), ""))
            elif kind == "error":
                self.install_error = event
            return
        if line.startswith(("dlstatus:", "pmstatus:")):
            parts = line.split(":", 3)
            try:
                percent = float(parts[2]) / 100.0
            except (IndexError, ValueError):
                return
            self._determinate = True
            base = 0.0 if parts[0] == "dlstatus" else 0.5
            self.progress_bar.set_fraction(min(1.0, base + percent / 2.0))
            if len(parts) > 3:
                self.progress_label.set_text(parts[3])
            return
        buffer = self.terminal_view.get_buffer()
        buffer.insert(buffer.get_end_iter(), line + "\n")
        mark = buffer.create_mark(None, buffer.get_end_iter(), False)
        self.terminal_view.scroll_mark_onscreen(mark)
        self.tail.append(line)
        self.tail = self.tail[-30:]

    def _on_exit(self, process, res):
        try:
            process.wait_finish(res)
        except GLib.Error:
            pass
        code = process.get_exit_status() if process.get_if_exited() else constants.EXIT_FAILED
        # Let the last lines of output be read first.
        GLib.timeout_add(300, self._install_finished, code, "")

    def _install_finished(self, code, message):
        self.installing = False
        self.process = None
        if self.busy_cookie:
            self.get_application().uninhibit(self.busy_cookie)
            self.busy_cookie = 0
        logutil.info("The installation helper exited with code %d" % code)
        event = self.install_error or {}
        detail = event.get("detail") or message or "\n".join(self.tail)

        if code == constants.EXIT_OK:
            self._after_install()
        elif code == constants.EXIT_PKEXEC_DISMISSED:
            # Cancelled by the user: back to the list, without any error.
            self.start_check(False)
        elif code == constants.EXIT_PKEXEC_DENIED:
            self.show_error(_("Authentication failed"),
                            _("You are not allowed to install updates, or the password was refused."),
                            "", retry=False)
        elif code == constants.EXIT_LOCKED:
            holder = event.get("holder", "")
            self.show_error(_("Cannot Proceed"),
                            _("Another process is currently using the package management system. "
                              "Please wait for it to finish and then try again.")
                            + ((" (%s)" % holder) if holder else ""), "")
        elif code == constants.EXIT_DISK_FULL:
            self.show_error(_("Not enough free disk space"),
                            _("%s more free space is needed to install the updates.")
                            % session.format_size(event.get("missing", 0)), "")
        elif code == constants.EXIT_UNEXPECTED_REMOVAL:
            self.show_error(_("The list of updates has changed"),
                            _("The changes APT would make differ from what was shown. Nothing was installed."),
                            ", ".join(event.get("packages", [])))
        elif code == constants.EXIT_REPAIR_FAILED:
            self.show_error(_("Could not repair the package system"),
                            _("Run 'apt update' in a terminal window to address this"), detail)
        elif code == constants.EXIT_FLATPAK_FAILED:
            # The APT step already succeeded: say so separately.
            self.show_error(_("Could not update the Flatpaks"),
                            _("The system updates were installed, but the Flatpak updates failed."),
                            detail)
        else:
            self.show_error(_("Could not install the updates"), "", detail)
        return False

    def _after_install(self):
        if self.install_priority:
            logutil.info("The Update Manager was updated, restarting it")
            self._restart_application()
            return
        if session.reboot_required():
            self._set_state(state.UP_TO_DATE)
            self.stack.set_visible_child_name("reboot")
            return
        self.start_check(False)

    def _restart_application(self):
        self.get_application().release_for_restart()
        try:
            os.execv("/usr/bin/mythicos-update", ["/usr/bin/mythicos-update"])
        except OSError as error:
            logutil.error("Cannot restart: %s" % error)
            self.start_check(True)

    def on_repair(self, _button):
        locked = locks.check_locked()
        if locked is not None:
            self._alert(_("Cannot Proceed"),
                        _("Another process is currently using the package management system. "
                          "Please wait for it to finish and then try again.")
                        + ((" (%s)" % locked) if locked else ""))
            return
        self._start_install(self.result, repair_only=True)
