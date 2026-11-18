# MythicOS Update Manager
# Copyright (C) 2026 Studio Hastag <contact@hastag.fr>
# SPDX-License-Identifier: GPL-3.0-or-later

DESTDIR ?=
PREFIX ?= /usr
LIBDIR := $(PREFIX)/lib/mythicos-update
BUILD := build

LANGS := $(patsubst po/%.po,%,$(wildcard po/*.po))

all: mo generated

mo:
	for lang in $(LANGS); do \
		install -d $(BUILD)/locale/$$lang/LC_MESSAGES; \
		msgfmt -o $(BUILD)/locale/$$lang/LC_MESSAGES/mythicos-update.mo po/$$lang.po || exit 1; \
	done

generated:
	python3 tools/generate_additional_files.py po $(BUILD)/generated

install: all
	install -d $(DESTDIR)$(PREFIX)/bin $(DESTDIR)$(LIBDIR)/mythicosupdate/ui
	install -m 0755 bin/* $(DESTDIR)$(PREFIX)/bin/
	install -m 0644 src/mythicosupdate/*.py $(DESTDIR)$(LIBDIR)/mythicosupdate/
	install -m 0644 src/mythicosupdate/ui/*.py $(DESTDIR)$(LIBDIR)/mythicosupdate/ui/
	install -m 0755 data/lib/lock-check.sh data/lib/automatic-upgrade.py $(DESTDIR)$(LIBDIR)/
	install -D -m 0644 data/schemas/fr.hastag.MythicOSUpdate.gschema.xml \
		$(DESTDIR)$(PREFIX)/share/glib-2.0/schemas/fr.hastag.MythicOSUpdate.gschema.xml
	for icon in $$(cd data/icons && find scalable -name '*.svg'); do \
		install -D -m 0644 data/icons/$$icon $(DESTDIR)$(PREFIX)/share/icons/hicolor/$$icon; \
	done
	install -D -m 0644 data/systemd/mythicos-update-automation.service \
		$(DESTDIR)$(PREFIX)/lib/systemd/system/mythicos-update-automation.service
	install -D -m 0644 data/systemd/mythicos-update-automation.timer \
		$(DESTDIR)$(PREFIX)/lib/systemd/system/mythicos-update-automation.timer
	install -D -m 0440 data/sudoers/mythicos-update $(DESTDIR)/etc/sudoers.d/mythicos-update
	install -D -m 0644 data/logrotate/mythicos-update $(DESTDIR)/etc/logrotate.d/mythicos-update
	install -D -m 0644 $(BUILD)/generated/applications/fr.hastag.MythicOSUpdate.desktop \
		$(DESTDIR)$(PREFIX)/share/applications/fr.hastag.MythicOSUpdate.desktop
	install -D -m 0644 $(BUILD)/generated/autostart/mythicos-update-tray.desktop \
		$(DESTDIR)/etc/xdg/autostart/mythicos-update-tray.desktop
	install -D -m 0644 $(BUILD)/generated/polkit/fr.hastag.mythicos-update.policy \
		$(DESTDIR)$(PREFIX)/share/polkit-1/actions/fr.hastag.mythicos-update.policy
	cp -r $(BUILD)/locale $(DESTDIR)$(PREFIX)/share/

clean:
	rm -rf $(BUILD)

.PHONY: all mo generated install clean
