# Virtual Layer Guard – bug demo

Two QGIS projects that differ by **one** `<layerDependencies>` entry.

| File | Content | Result without the plugin |
|---|---|---|
| `control_works.qgs` | `cities`, `rivers`, 3 virtual layers on `cities` | all 5 layers load |
| `bug_demo.qgs` | same, but `rivers` depends on a layer ID that no longer exists (`deleted_layer_…`) | only `cities` loads, all 3 virtual layers (and `rivers`) are silently skipped |

Keep the four files together (paths are relative).

## Demo steps

1. Disable Virtual Layer Guard, then open `control_works.qgs`: everything renders.
2. Open `bug_demo.qgs`: the virtual layers still appear in the Layers panel but show nothing, and no error appears. `rivers` is gone too, even though it is a normal GeoJSON layer.
3. Optional, to show data loss: **save** `bug_demo.qgs` and reopen it. The virtual layer definitions (SQL, style) are gone from the file.
   Use a copy of the file for this step.
4. Enable the plugin and open a fresh copy of `bug_demo.qgs`: the skipped layers are restored. Saving removes the dangling dependency.

## Where the bug is

```diff
-      <layerDependencies/>
+      <layerDependencies>
+        <layer id="deleted_layer_00000000_0000_0000_0000_000000000000"/>
+      </layerDependencies>
```

Verified headless with QGIS 3.44.9: control 5/5 layers loaded, bug_demo 1/5.
