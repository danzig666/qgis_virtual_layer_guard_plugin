<img src="icon_256.png" width="96" align="right" alt="icon">

# Virtual Layer Guard (QGIS plugin)

Prevents QGIS from silently dropping virtual (and other dependent) layers from the project file. QGIS 3.30 – 4.x, English and Hungarian UI.

*Megakadályozza, hogy a QGIS csendben kihagyja a projektfájlból a virtuális (és más függő) rétegeket.*

If any layer depends on a layer ID that no longer exists, QGIS skips every layer with a dependency while loading the project, and the next save removes their definitions for good. This plugin cleans such dependencies on save, keeps definitions QGIS would drop, restores skipped layers on load and keeps a copy of every virtual layer definition for recovery.

- Magyar leírás: [qgis_virtual_layer_guard/README_HU.md](qgis_virtual_layer_guard/README_HU.md)

Experimental: back up your projects before use.

## License

GNU General Public License v2.0 or later, see [LICENSE](LICENSE).
