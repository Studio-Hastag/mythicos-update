# MythicOS Update Manager - update data model
#
# Derived from mintupdate (usr/lib/linuxmint/mintUpdate/Classes.py)
# Copyright (C) 2007-2015 Clement Lefebvre <root@linuxmint.com>
# Copyright (C) 2026 Studio Hastag <contact@hastag.fr>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version.

from mythicosupdate.constants import SOURCE_PACKAGE_NAME_OVERRIDES


class Update:
    """A group of binary packages that are updated together (one source
    package, or one kernel version)."""

    FIELDS = ("package_names", "source_name", "real_source_name", "display_name",
              "main_package_name", "old_version", "new_version", "size", "type",
              "origin", "archive", "short_description")

    def __init__(self, package=None, source_name=None):
        self.package_names = []
        self.source_name = source_name or ""
        self.real_source_name = ""
        self.display_name = ""
        self.main_package_name = ""
        self.old_version = ""
        self.new_version = ""
        self.size = 0
        self.type = "package"
        self.origin = ""
        self.archive = ""
        self.short_description = ""
        if package is not None:
            self._init_from_package(package, source_name)

    def _init_from_package(self, package, source_name):
        self.package_names.append(package.name)
        self.main_package_name = package.name
        self.new_version = package.candidate.version
        self.old_version = package.installed.version if package.installed else ""
        self.size = package.candidate.size
        self.real_source_name = package.candidate.source_name
        self.source_name = source_name or self.real_source_name
        if self.main_package_name in SOURCE_PACKAGE_NAME_OVERRIDES:
            self.display_name = self.main_package_name
        else:
            self.display_name = self.source_name
        self.short_description = package.candidate.raw_description or ""
        self.type = "package"
        for origin in package.candidate.origins:
            self.origin = origin.origin
            self.archive = origin.archive
            if origin.origin == "Ubuntu":
                self.origin = "ubuntu"
            elif origin.origin == "Debian":
                self.origin = "debian"
            if origin.origin == "Ubuntu" and "-security" in origin.archive:
                self.type = "security"
                break
            if origin.origin == "Debian" and "-Security" in origin.label:
                self.type = "security"
                break
        if (package.candidate.section == "kernel"
                or self.main_package_name.startswith("linux-headers")
                or self.real_source_name in ("linux", "linux-kernel", "linux-signed", "linux-meta")):
            self.type = "kernel"

    def add_package(self, package):
        if self.main_package_name in SOURCE_PACKAGE_NAME_OVERRIDES:
            self.display_name = self.source_name
        self.package_names.append(package.name)
        self.size += package.candidate.size
        if not self.main_package_name or package.name == self.source_name:
            self.main_package_name = package.name
            self.short_description = package.candidate.raw_description or ""
            return
        if self.main_package_name != self.source_name:
            # Prefer the "real" package over dev, doc, library... companions
            for suffix in ("-dev", "-dbg", "-common", "-core", "-data", "-doc", ":i386", ":amd64"):
                if self.main_package_name.endswith(suffix) and not package.name.endswith(suffix):
                    self._overwrite_main_package(package)
                    return
            for prefix in ("lib", "gir1.2"):
                if self.main_package_name.startswith(prefix) and not package.name.startswith(prefix):
                    self._overwrite_main_package(package)
                    return
            for keyword in ("-locale-", "-l10n-", "-help-"):
                if keyword in self.main_package_name and keyword not in package.name:
                    self._overwrite_main_package(package)
                    return

    def _overwrite_main_package(self, package):
        self.short_description = package.candidate.raw_description or ""
        self.main_package_name = package.name

    def to_dict(self):
        return {key: getattr(self, key) for key in self.FIELDS}

    @classmethod
    def from_dict(cls, data):
        update = cls()
        for key in cls.FIELDS:
            if key in data:
                setattr(update, key, data[key])
        return update
