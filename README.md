# mythicos-update

Gestionnaire de mise à jour de MythicOS (GTK 4 + libadwaita, APT + Flatpak).
Licence GPL-3+. Code réutilisé de mintupdate (Mint) et update-manager (Ubuntu) : voir `debian/copyright`.

## Architecture

- `bin/mythicos-update` : fenêtre GTK 4 (`src/mythicosupdate/ui/`), sans aucun import XApp.
- `bin/mythicos-update-tray` : icône de barre de tâches, processus séparé (GTK 3 + XApp). Elle suit la fenêtre via `$XDG_RUNTIME_DIR/mythicos-update/state.json`.
- Moteur sans GTK (`aptcheck.py`, `flatpak_worker.py`, `checker.py`, `release.py`…) exécuté en processus enfants avec délai maximal.
- Trois points d'entrée root : `mythicos-refresh-cache` (sudoers, sans mot de passe), `mythicos-update-helper` (pkexec, installation APT + Flatpak), `mythicos-update-automation` (pkexec, active/désactive le timer). Service automatique : `automatic-upgrade.py`.
- Le helper n'accepte que des noms de paquets déjà installés et mettables à jour, refuse toute suppression non annoncée (`--allow-remove`), vérifie l'espace disque et ne transmet aucune option à apt-get/flatpak.
- Le helper parle à la fenêtre par des lignes `@@MYTHICOS {json}` sur stdout ; les codes de sortie sont dans `constants.py`.

## Construire

    dpkg-buildpackage -us -uc -b      # dépend de debhelper, dh-python, gettext

## Traductions

`po/mythicos-update.pot` (xgettext sur `src/`), puis `tools/merge_translations.py <mintupdate-master>` reconstruit `po/*.po`
(traductions Mint pour les textes identiques, `translations/<lang>.json` pour les nouveaux textes).
Les `.desktop` et la politique polkit sont générés à la compilation par `tools/generate_additional_files.py`.
