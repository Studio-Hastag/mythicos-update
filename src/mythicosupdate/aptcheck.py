# MythicOS Update Manager - APT update computation
#
# Derived from mintupdate (usr/lib/linuxmint/mintUpdate/aptUpdater.py)
#   Copyright (C) 2007-2015 Clement Lefebvre <root@linuxmint.com>
# and from Ubuntu update-manager (UpdateManager/Core/UpdateList.py, MyCache.py:
# phased updates and interrupted-dpkg detection)
#   Copyright (C) 2004-2013 Canonical Ltd and the update-manager authors
# Copyright (C) 2026 Studio Hastag <contact@hastag.fr>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version.
#
# This module has no GTK dependency. It is run in a child process by the
# window and the tray icon (python3 -m mythicosupdate.aptcheck), which print
# one JSON document on stdout; the root helper imports it directly.

import json
import os
import re
import sys

import apt

from mythicosupdate import constants, diskcheck
from mythicosupdate.updates import Update

PHASED_KEY = "Phased-Update-Percentage"


def dpkg_journal_dirty():
    """True if a previous dpkg run was interrupted (from Ubuntu MyCache)."""
    try:
        for name in os.listdir(constants.DPKG_UPDATES_DIR):
            if re.match(r"^[0-9]+$", name):
                return True
    except OSError:
        pass
    return False


def needs_repair():
    """True if dpkg was interrupted (dirty journal) or left packages in a
    half-installed / half-configured state (`dpkg --audit`)."""
    if dpkg_journal_dirty():
        return True
    try:
        import subprocess
        audit = subprocess.run(["dpkg", "--audit"], stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, timeout=60, text=True,
                               env=dict(os.environ, LC_ALL="C.UTF-8"))
        return bool(audit.stdout.strip())
    except Exception:
        return False


def _kernel_version_from_meta(pkg_version):
    for dependency in pkg_version.dependencies:
        if not dependency.target_versions or dependency.rawtype != "Depends":
            return None
        target = dependency.target_versions[0]
        if target.source_name in ("linux", "linux-signed") or target.source_name.startswith("linux-hwe"):
            return target.source_version
        if target.source_name.startswith("linux-meta"):
            return _kernel_version_from_meta(target)
    return None


class _Collector:
    def __init__(self):
        self.updates = {}
        self.priority = False
        self.meta_names = []

    def add(self, package):
        candidate = package.candidate
        source_version = candidate.version
        kernel_update = False

        # Show the version of the actual kernel for kernel meta packages
        if candidate.source_name.startswith("linux-meta"):
            shortname = package.name.split(":")[0]
            if shortname not in self.meta_names:
                self.meta_names.append(shortname)
            real_version = _kernel_version_from_meta(candidate)
            if real_version:
                source_version = real_version

        # Group all kernel packages of one version together
        if (candidate.source_name == "linux"
                or candidate.source_name.startswith(("linux-hwe", "linux-meta", "linux-signed"))
                or any(candidate.source_name.startswith("linux%s" % flavour)
                       for flavour in constants.SUPPORTED_KERNEL_TYPES)):
            kernel_update = True
            source_name = "linux-%s" % source_version
        else:
            source_name = candidate.source_name

        if source_name in constants.PRIORITY_UPDATES:
            if not self.priority and self.updates:
                self.updates.clear()
            self.priority = True
        if source_name in constants.PRIORITY_UPDATES or not self.priority:
            if source_name in self.updates:
                update = self.updates[source_name]
                update.add_package(package)
                if (kernel_update and package.is_installed
                        and "-" not in update.old_version and "-" in package.installed.version):
                    update.old_version = package.installed.version
            else:
                update = Update(package, source_name=source_name)
                self.updates[source_name] = update
            if kernel_update:
                update.type = "kernel"
            update.new_version = source_version


def _held_reason(package):
    try:
        import apt_pkg
        if package._pkg.selected_state == apt_pkg.SELSTATE_HOLD:
            return "hold"
    except Exception:
        pass
    try:
        if PHASED_KEY in package.candidate.record:
            return "phased"
    except Exception:
        pass
    return "kept-back"


def _describe_changes(cache, result):
    for package in cache.get_changes():
        if package.marked_delete:
            version = package.installed.version if package.installed else ""
            result["removed"].append({"name": package.name, "version": version})
        elif package.marked_install and not package.is_installed:
            if package.candidate is not None:
                result["new"].append({"name": package.name, "version": package.candidate.version,
                                      "size": package.candidate.size})
    try:
        result["download_size"] = int(cache.required_download)
        result["install_size"] = int(cache.required_space)
    except Exception:
        pass


def compute(only_packages=None):
    """Compute the APT updates. Returns a JSON-serialisable dict.

    only_packages: if given, only these packages (and the dependencies APT
    adds for them) are marked, as done for the priority self-update.
    """
    result = {"updates": [], "priority": False, "new": [], "removed": [], "held": [],
              "download_size": 0, "install_size": 0, "disk_missing": 0,
              "needs_repair": needs_repair(), "error": None, "broken": ""}
    try:
        cache = apt.Cache()
    except Exception as error:
        result["error"] = str(error).replace("E:", "\n").strip()
        return result

    try:
        if only_packages:
            for name in only_packages:
                cache[name].mark_upgrade()
        else:
            cache.upgrade(True)  # dist-upgrade, as Mint does
    except Exception as error:
        # Broken packages: the resolver could not find a consistent state.
        result["error"] = "broken"
        result["broken"] = str(error).replace("E:", "\n").strip()
        return result

    collector = _Collector()
    for package in cache.get_changes():
        if package.candidate is None:
            continue
        if (package.is_installed and package.candidate.version != package.installed.version
                and (package.marked_upgrade or package.marked_downgrade)):
            collector.add(package)

    if only_packages is None:
        for package in cache:
            if (package.is_installed and package.is_upgradable and package.candidate is not None
                    and not package.marked_upgrade and not package.marked_delete
                    and not package.marked_downgrade):
                result["held"].append({"name": package.name,
                                       "installed": package.installed.version,
                                       "candidate": package.candidate.version,
                                       "reason": _held_reason(package)})

    _describe_changes(cache, result)

    if collector.priority and only_packages is None:
        # Redo the computation for the priority packages only so that the
        # list, sizes and removals describe exactly what will be installed.
        names = []
        for update in collector.updates.values():
            names.extend(update.package_names)
        sub = compute(only_packages=names)
        sub["priority"] = True
        sub["held"] = []
        return sub

    result["priority"] = collector.priority
    result["updates"] = [collector.updates[key].to_dict() for key in sorted(collector.updates)]
    result["disk_missing"] = diskcheck.missing_space(result["download_size"], result["install_size"])
    return result


def packages_not_upgradable(names):
    """Names from `names` that are not installed packages with a newer
    candidate version (used by the root helper to refuse anything else)."""
    cache = apt.Cache()
    bad = []
    for name in names:
        try:
            package = cache[name]
        except KeyError:
            bad.append(name)
            continue
        if not package.is_installed or package.candidate is None or not package.is_upgradable:
            bad.append(name)
    return bad


def disk_missing_for(names):
    """Bytes missing on disk to upgrade exactly these packages, plus the
    sizes: (missing, download, install)."""
    cache = apt.Cache()
    for name in names:
        cache[name].mark_upgrade()
    download = int(cache.required_download)
    install = int(cache.required_space)
    return diskcheck.missing_space(download, install), download, install


def main():
    only = sys.argv[1:] or None
    print(json.dumps(compute(only)))


if __name__ == "__main__":
    main()
