"""Minimal English/Hungarian message catalogue.

The language follows the QGIS user interface locale: Hungarian when QGIS runs
in Hungarian, English otherwise. A plain dictionary is used instead of Qt
.ts/.qm files so the plugin has no build step.
"""

from qgis.core import QgsApplication, QgsSettings

PLUGIN_NAME = "Virtual Layer Guard"

MESSAGES = {
    "menu_check": {
        "en": "Check project layers",
        "hu": "Projekt rétegeinek ellenőrzése",
    },
    "menu_restore": {
        "en": "Restore lost layers",
        "hu": "Elveszett rétegek visszaállítása",
    },
    "btn_restore": {
        "en": "Restore",
        "hu": "Visszaállítás",
    },
    "btn_details": {
        "en": "Details",
        "hu": "Részletek",
    },
    "dropped_on_load": {
        "en": "QGIS skipped {count} layer(s) of the project file while loading "
              "(usually a dependency on a deleted layer): {names}.",
        "hu": "A QGIS betöltéskor kihagyott {count} réteget a projektfájlból "
              "(általában egy törölt rétegre mutató függőség miatt): {names}.",
    },
    "dropped_restored": {
        "en": " Restored automatically: {ok}. Save the project to keep the fix.",
        "hu": " Automatikusan visszaállítva: {ok}. A javítás megtartásához "
              "mentsd a projektet.",
    },
    "orphans_on_load": {
        "en": "{count} layer(s) appear in the Layers panel without data: {names}.",
        "hu": "{count} réteg csak névként szerepel a Rétegek panelen, "
              "definíció nélkül: {names}.",
    },
    "orphans_cached": {
        "en": " A saved copy exists for {count} of them.",
        "hu": " Ebből {count} réteghez van mentett másolat.",
    },
    "restored": {
        "en": "Restored {ok} layer(s).",
        "hu": "Visszaállítva: {ok} réteg.",
    },
    "restore_failed": {
        "en": " Could not restore: {names}.",
        "hu": " Nem sikerült visszaállítani: {names}.",
    },
    "nothing_to_restore": {
        "en": "There is no lost layer with a saved copy.",
        "hu": "Nincs olyan elveszett réteg, amelyhez mentett másolat lenne.",
    },
    "save_guarded": {
        "en": "Save guard: kept the definition of {count} layer(s) that QGIS "
              "would have dropped from the project file: {names}.",
        "hu": "Mentésvédelem: {count} réteg definícióját megtartottam, amelyet a "
              "QGIS kihagyott volna a projektfájlból: {names}.",
    },
    "deps_cleaned": {
        "en": "Removed {count} dependency entry(s) pointing to layers that no "
              "longer exist (they make QGIS skip layers on load).",
        "hu": "Eltávolítottam {count} olyan függőségi bejegyzést, amely már nem "
              "létező rétegre mutatott (ezek miatt a QGIS betöltéskor kihagy "
              "rétegeket).",
    },
    "removal_breaks": {
        "en": "Removing \"{name}\" breaks these virtual layers: {names}.",
        "hu": "A(z) \"{name}\" eltávolítása elrontja ezeket a virtuális "
              "rétegeket: {names}.",
    },
    "source_breaks": {
        "en": "After the data source change of \"{name}\" these virtual layers "
              "fail: {details}",
        "hu": "A(z) \"{name}\" adatforrásának cseréje után ezek a virtuális "
              "rétegek hibásak: {details}",
    },
    "added_missing_refs": {
        "en": "Virtual layer \"{name}\" refers to layers missing from this "
              "project: {refs}.",
        "hu": "A(z) \"{name}\" virtuális réteg olyan rétegekre hivatkozik, "
              "amelyek nincsenek ebben a projektben: {refs}.",
    },
    "report_title": {
        "en": "Virtual Layer Guard – project check",
        "hu": "Virtual Layer Guard – projektellenőrzés",
    },
    "report_ok": {
        "en": "No problem found.",
        "hu": "Nem találtam hibát.",
    },
    "sec_orphans": {
        "en": "Layers panel entries without a layer",
        "hu": "Rétegfa-bejegyzések réteg nélkül",
    },
    "sec_dropped": {
        "en": "In the project file but not loaded",
        "hu": "A projektfájlban benne van, de nem töltődött be",
    },
    "sec_dangling": {
        "en": "Dependencies on layers that do not exist",
        "hu": "Nem létező rétegre mutató függőségek",
    },
    "sec_invalid": {
        "en": "Invalid virtual layers",
        "hu": "Hibás virtuális rétegek",
    },
    "sec_refs": {
        "en": "Virtual layers referring to missing layers",
        "hu": "Hiányzó rétegre hivatkozó virtuális rétegek",
    },
    "cached_yes": {
        "en": "saved copy available",
        "hu": "van mentett másolat",
    },
    "cached_no": {
        "en": "no saved copy",
        "hu": "nincs mentett másolat",
    },
    "report_hint": {
        "en": "Dangling dependencies are removed automatically on save. Lost "
              "layers can be brought back with \"Restore lost layers\".",
        "hu": "A nem létező rétegre mutató függőségeket mentéskor automatikusan "
              "törlöm. Az elveszett rétegeket az \"Elveszett rétegek "
              "visszaállítása\" menüponttal lehet visszahozni.",
    },
}


def _detect_language():
    locale = ""
    try:
        locale = QgsApplication.locale() or ""
    except Exception:  # very old API or no application instance
        pass
    if not locale:
        settings = QgsSettings()
        if settings.value("locale/overrideFlag", False, type=bool):
            locale = settings.value("locale/userLocale", "", type=str)
    return "hu" if locale.lower().startswith("hu") else "en"


LANGUAGE = _detect_language()


def tr(key, **kwargs):
    entry = MESSAGES[key]
    text = entry.get(LANGUAGE) or entry["en"]
    return text.format(**kwargs) if kwargs else text
