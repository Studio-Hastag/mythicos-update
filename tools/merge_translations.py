#!/usr/bin/env python3
"""Developer tool: build po/<lang>.po from po/mythicos-update.pot.

For every language:
  * strings whose msgid also exists in Linux Mint's mintupdate.pot reuse the
    translation (and the header credits) of the Mint .po file;
  * the other strings come from translations/<lang>.json (translated by
    Claude), when that file exists;
  * anything else stays empty and falls back to English.

Usage: merge_translations.py MINTUPDATE_DIR   (the unpacked mintupdate-master)

Copyright (C) 2026 Studio Hastag <contact@hastag.fr>
SPDX-License-Identifier: GPL-3.0-or-later
"""
import glob
import json
import os
import sys

import polib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTE = ("Strings shared with mintupdate keep the translations of the Linux Mint translators (credits above); "
        "the other strings were translated by Claude (Anthropic) for Studio Hastag.")


def main(mint_dir):
    pot = polib.pofile(os.path.join(ROOT, "po", "mythicos-update.pot"))
    mint_files = {os.path.basename(p)[len("mintupdate-"):-3]: p
                  for p in glob.glob(os.path.join(mint_dir, "po", "mintupdate-*.po"))}
    json_files = {os.path.basename(p)[:-5]: p for p in glob.glob(os.path.join(ROOT, "translations", "*.json"))
                  if not p.endswith("new_strings.json")}
    written = 0
    for lang in sorted(set(mint_files) | set(json_files)):
        mint = {}
        header = None
        if lang in mint_files:
            mpo = polib.pofile(mint_files[lang])
            header = mpo
            for entry in mpo:
                if entry.msgstr and "fuzzy" not in entry.flags and not entry.obsolete:
                    mint[entry.msgid] = entry.msgstr
        own = {}
        if lang in json_files:
            with open(json_files[lang], encoding="utf-8") as handle:
                own = json.load(handle)

        po = polib.POFile()
        po.metadata = {
            "Project-Id-Version": "mythicos-update",
            "Report-Msgid-Bugs-To": "contact@hastag.fr",
            "POT-Creation-Date": pot.metadata.get("POT-Creation-Date", ""),
            "PO-Revision-Date": "2026-11-15 12:00+0000",
            "Last-Translator": (header.metadata.get("Last-Translator", "") if header else "Claude (Anthropic)"),
            "Language-Team": (header.metadata.get("Language-Team", "") if header else lang),
            "Language": lang,
            "MIME-Version": "1.0",
            "Content-Type": "text/plain; charset=UTF-8",
            "Content-Transfer-Encoding": "8bit",
        }
        if header and header.metadata.get("Plural-Forms"):
            po.metadata["Plural-Forms"] = header.metadata["Plural-Forms"]
        po.header = ((header.header.strip() + "\n\n") if header else "") + NOTE
        translated = 0
        for entry in pot:
            msgstr = mint.get(entry.msgid) or own.get(entry.msgid, "")
            new = polib.POEntry(msgid=entry.msgid, msgstr=msgstr, occurrences=entry.occurrences,
                                comment=entry.comment)
            if msgstr:
                translated += 1
            po.append(new)
        if translated:
            po.save(os.path.join(ROOT, "po", "%s.po" % lang))
            written += 1
    print("wrote %d .po files" % written)


if __name__ == "__main__":
    main(sys.argv[1])
