# MythicOS Update Manager - gettext setup
#
# Copyright (C) 2026 Studio Hastag <contact@hastag.fr>
# SPDX-License-Identifier: GPL-3.0-or-later

import gettext
import locale

from mythicosupdate.constants import GETTEXT_DOMAIN, LOCALE_DIR

try:
    locale.setlocale(locale.LC_ALL, "")
except locale.Error:
    pass

try:
    locale.bindtextdomain(GETTEXT_DOMAIN, LOCALE_DIR)
except AttributeError:
    pass

gettext.bindtextdomain(GETTEXT_DOMAIN, LOCALE_DIR)
gettext.textdomain(GETTEXT_DOMAIN)

_ = gettext.gettext
ngettext = gettext.ngettext
