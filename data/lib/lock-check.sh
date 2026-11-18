#!/bin/sh
# MythicOS Update Manager - is the package manager busy?
# Runs as root through sudo. Prints "process (pid)" for every process holding
# a package manager lock and exits with 3 when at least one does, 0 otherwise.
#
# Derived from mintupdate (dpkg_lock_check.sh)
# Copyright (C) 2007-2015 Clement Lefebvre <root@linuxmint.com>
# Copyright (C) 2026 Studio Hastag <contact@hastag.fr>
# SPDX-License-Identifier: GPL-3.0-or-later

# With the "lists" argument the lock of the package lists (apt update) is
# checked too: used to name the process that blocks a refresh.
locks="/var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/cache/apt/archives/lock"
[ "$1" = "lists" ] && locks="$locks /var/lib/apt/lists/lock"

found=0
for lock in $locks; do
    [ -e "$lock" ] || continue
    for pid in $(/usr/bin/fuser "$lock" 2>/dev/null); do
        [ "$pid" = "$$" ] && continue
        name=$(cat "/proc/$pid/comm" 2>/dev/null || echo "?")
        echo "$name ($pid)"
        found=1
    done
done
[ "$found" -eq 1 ] && exit 3
exit 0
