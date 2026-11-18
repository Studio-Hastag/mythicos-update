#!/usr/bin/python3
"""Generate the translated .desktop and polkit files from the .po files.

Replaces mintcommon.additionalfiles (mint-common) so that mythicos-update
does not depend on Mint packages. Standard library only.

Usage: generate_additional_files.py PO_DIR OUTPUT_DIR

Copyright (C) 2026 Studio Hastag <contact@hastag.fr>
SPDX-License-Identifier: GPL-3.0-or-later
"""
import ast
import glob
import os
import sys
from xml.sax.saxutils import escape

APP_ID = "fr.hastag.MythicOSUpdate"
NAME = "Update Manager"
COMMENT = "Show and install available updates"
MSG_INSTALL = "Authentication is required to install updates"
MSG_AUTOMATION = "Authentication is required to change the automatic updates setting"


def parse_po(path):
    """Minimal .po reader: returns {msgid: msgstr} for translated, non-fuzzy entries."""
    entries = {}
    msgid = msgstr = None
    current = None
    fuzzy = False
    pending_fuzzy = False

    def flush():
        nonlocal msgid, msgstr, fuzzy
        if msgid and msgstr and not fuzzy:
            entries[msgid] = msgstr
        msgid = msgstr = None
        fuzzy = False

    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if line.startswith("#,") and "fuzzy" in line:
                pending_fuzzy = True
            elif line.startswith("msgctxt") or line.startswith("msgid_plural"):
                current = None
            elif line.startswith("msgid "):
                flush()
                fuzzy = pending_fuzzy
                pending_fuzzy = False
                msgid = ast.literal_eval(line[6:])
                current = "id"
            elif line.startswith("msgstr "):
                msgstr = ast.literal_eval(line[7:])
                current = "str"
            elif line.startswith('"'):
                text = ast.literal_eval(line)
                if current == "id":
                    msgid += text
                elif current == "str":
                    msgstr += text
            elif not line:
                current = None
    flush()
    return entries


def desktop(translations, name_key, comment_key, extra):
    lines = ["[Desktop Entry]", "Type=Application", "Name=%s" % NAME]
    for lang in sorted(translations):
        if name_key in translations[lang]:
            lines.append("Name[%s]=%s" % (lang, translations[lang][name_key]))
    lines.append("Comment=%s" % COMMENT)
    for lang in sorted(translations):
        if comment_key in translations[lang]:
            lines.append("Comment[%s]=%s" % (lang, translations[lang][comment_key]))
    lines.extend(extra)
    return "\n".join(lines) + "\n"


def polkit_message(translations, msgid, source):
    lines = ["    <description>%s</description>" % escape(source)]
    for lang in sorted(translations):
        if msgid in translations[lang]:
            lines.append('    <description xml:lang="%s">%s</description>'
                         % (lang, escape(translations[lang][msgid])))
    lines.append("    <message>%s</message>" % escape(source))
    for lang in sorted(translations):
        if msgid in translations[lang]:
            lines.append('    <message xml:lang="%s">%s</message>'
                         % (lang, escape(translations[lang][msgid])))
    return "\n".join(lines)


def main(po_dir, out_dir):
    translations = {}
    for path in sorted(glob.glob(os.path.join(po_dir, "*.po"))):
        translations[os.path.basename(path)[:-3]] = parse_po(path)

    os.makedirs(os.path.join(out_dir, "applications"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "autostart"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "polkit"), exist_ok=True)

    with open(os.path.join(out_dir, "applications", APP_ID + ".desktop"), "w", encoding="utf-8") as out:
        out.write(desktop(translations, NAME, COMMENT, [
            "Exec=mythicos-update", "Icon=" + APP_ID, "Terminal=false",
            "Categories=System;Settings;", "StartupNotify=true",
            "Keywords=update;upgrade;apt;flatpak;packages;"]))
    with open(os.path.join(out_dir, "autostart", "mythicos-update-tray.desktop"), "w", encoding="utf-8") as out:
        out.write(desktop(translations, NAME, COMMENT, [
            "Exec=mythicos-update-tray", "Icon=" + APP_ID, "Terminal=false", "NoDisplay=true",
            "X-GNOME-Autostart-enabled=true", "X-GNOME-Autostart-Phase=Applications"]))

    policy = ['<?xml version="1.0" encoding="UTF-8"?>',
              '<!DOCTYPE policyconfig PUBLIC',
              ' "-//freedesktop//DTD PolicyKit Policy Configuration 1.0//EN"',
              ' "http://www.freedesktop.org/standards/PolicyKit/1/policyconfig.dtd">',
              '<policyconfig>', '',
              '  <vendor>Studio Hastag</vendor>',
              '  <vendor_url>https://hastag.fr/</vendor_url>', '']
    for action, path, msgid in (("fr.hastag.mythicos-update.install", "/usr/bin/mythicos-update-helper", MSG_INSTALL),
                                ("fr.hastag.mythicos-update.automation", "/usr/bin/mythicos-update-automation",
                                 MSG_AUTOMATION)):
        policy += ['  <action id="%s">' % action,
                   '    <icon_name>%s</icon_name>' % APP_ID,
                   polkit_message(translations, msgid, msgid),
                   '    <defaults>',
                   '      <allow_any>no</allow_any>',
                   '      <allow_inactive>no</allow_inactive>',
                   '      <allow_active>auth_admin_keep</allow_active>',
                   '    </defaults>',
                   '    <annotate key="org.freedesktop.policykit.exec.path">%s</annotate>' % path,
                   '    <annotate key="org.freedesktop.policykit.exec.allow_gui">false</annotate>',
                   '  </action>', '']
    policy.append("</policyconfig>")
    with open(os.path.join(out_dir, "polkit", "fr.hastag.mythicos-update.policy"), "w", encoding="utf-8") as out:
        out.write("\n".join(policy) + "\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
