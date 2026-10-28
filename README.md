<img src="icon_256.png" width="96" align="right" alt="icon">

# Virtual Layer Guard (QGIS plugin)

Prevents QGIS from silently dropping virtual (and other dependent) layers from the project file. QGIS 3.30 – 4.x, English and Hungarian UI.

*Megakadályozza, hogy a QGIS csendben kihagyja a projektfájlból a virtuális (és más függő) rétegeket.*

If any layer depends on a layer ID that no longer exists, QGIS skips every layer with a dependency while loading the project, and the next save removes their definitions for good. This plugin cleans such dependencies on save, keeps definitions QGIS would drop, restores skipped layers on load and keeps a copy of every virtual layer definition for recovery.

- Magyar leírás: [qgis_virtual_layer_guard/README_HU.md](qgis_virtual_layer_guard/README_HU.md)

Experimental: back up your projects before use.

## Install

Download `qgis_virtual_layer_guard.zip` from the [latest release](https://github.com/danzig666/qgis_virtual_layer_guard_plugin/releases/latest), then in QGIS: **Plugins → Manage and Install Plugins → Install from ZIP**.

## The underlying QGIS bug

### Symptom

Open a project in which **one** layer has a dependency (`<layerDependencies>` in the project file) on a layer ID that is no longer in the project. This happens easily after deleting or replacing a layer, changing data sources, or moving layers between projects. QGIS then loads only the layers that have **no** dependencies at all. Every layer that has a dependency is skipped silently, with no error message and no entry in the *Handle unavailable layers* dialog. Virtual layers always have dependencies, so all of them disappear. Their names stay in the Layers panel without a layer behind them, and the next save writes the project without their definitions. The SQL, style, joins and labels are then gone from the file.

### Affected versions

- Reproduced with QGIS **3.40.8, 3.44.9 and 4.2.2** on a real project: 0 of 11 virtual layers loaded. With the single dangling dependency entry removed from the file, all 11 loaded.
- The code is unchanged on `master` as of 2026-10-28.
- It was introduced in commit `de30d7ce08` ("Further DOM loop optimizations", 2020-12-10), so it is very likely present since **QGIS 3.18**.

### Cause

`QgsProject` sorts layers with `QgsLayerDefinition::DependencySorter` before loading them (`src/core/project/qgsproject.cpp`). The comment there states the intended behaviour: *"Missing a dependency? We still load all the layers, otherwise the project is completely broken!"*

The sorter in `src/core/qgslayerdefinition.cpp` (`DependencySorter::init`) tries to do that. When a dependency is missing, it restarts from the first `<maplayer>` element and adds every layer to the sorted list. But the first element is stored as a **reference** to the loop variable, not as a copy:

```cpp
const QDomElement &firstElement { layerElem };   // reference, not a copy
...
while ( !layerElem.isNull() ) { ... layerElem = layerElem.nextSiblingElement(); }
...
// missing dependency:
mHasMissingDependency = true;
layerElem = firstElement;        // layerElem is already null here, so this assigns null
while ( !layerElem.isNull() )    // never entered
```

By the time a missing dependency is detected, the first loop has walked `layerElem` to a null element, so `firstElement` is null as well. The "load everything" loop never runs. `mSortedLayerNodes` keeps only the dependency-free layers, and `QgsProject` loads only those.

### Possible fix

Store a copy of the first element. Also clear the partial list before refilling it, otherwise the dependency-free layers would be added twice:

```diff
-  const QDomElement &firstElement { layerElem };
+  const QDomElement firstElement = layerElem;
 ...
         mHasMissingDependency = true;
+        mSortedLayerNodes.clear();
         layerElem = firstElement;
         while ( !layerElem.isNull() )
```

This patch has not been compiled or tested against the QGIS source tree.

### Why it is published here

QGIS does not accept bug reports, pull requests, comments or reviews made with AI, LLM or agent assistance ([QEP 408](https://github.com/qgis/QGIS-Enhancement-Proposals/blob/master/qep-408-ai-tool-policy.md)). This analysis was made with an AI assistant, so it is documented here instead of being reported to the QGIS repository. Until QGIS changes this code, this plugin works around the bug: it removes dangling dependencies on save and restores skipped layers on load.

## License

GNU General Public License v2.0 or later, see [LICENSE](LICENSE).
