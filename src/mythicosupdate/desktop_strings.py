# Strings used only by the generated .desktop and polkit files. This module
# is never imported: it exists so that xgettext extracts them into the .pot.
#
# Copyright (C) 2026 Studio Hastag <contact@hastag.fr>
# SPDX-License-Identifier: GPL-3.0-or-later

from mythicosupdate.i18n import _

DESKTOP_NAME = _("Update Manager")
DESKTOP_COMMENT = _("Show and install available updates")
POLKIT_INSTALL = _("Authentication is required to install updates")
POLKIT_AUTOMATION = _("Authentication is required to change the automatic updates setting")
