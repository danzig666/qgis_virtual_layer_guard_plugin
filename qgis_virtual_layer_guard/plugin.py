"""Virtual Layer Guard for QGIS 3.30+ / 4.x.

QGIS silently skips every layer that has a dependency (virtual layers always
have one) when any layer in the project file depends on a layer ID that no
longer exists. The skipped layers keep their Layers panel entry, but the next
save drops their definition from the project file for good.

This plugin
- removes dependencies on missing layers from the project file on every save,
- re-inserts definitions QGIS would drop on save (layer tree entries without
  a layer),
- restores layers QGIS skipped while loading a project,
- warns when removing a layer or changing its data source breaks a virtual
  layer, and when a virtual layer arrives referring to missing layers.

SPDX-License-Identifier: GPL-2.0-or-later
"""

import html
import os
import traceback

from qgis.PyQt.QtCore import QObject, QTimer
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QDialog, QDialogButtonBox, QPushButton, QTextBrowser, QVBoxLayout
from qgis.core import Qgis, QgsMessageLog, QgsProject

from . import guard
from .i18n import PLUGIN_NAME, tr

ICON_PATH = os.path.join(os.path.dirname(__file__), "icon.png")
MAX_NAMES = 6


def _names(names):
    names = sorted(names)
    text = ", ".join(names[:MAX_NAMES])
    return text + (f" (+{len(names) - MAX_NAMES})" if len(names) > MAX_NAMES else "")


class VirtualLayerGuard(QObject):
    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.iface = iface
        self.project = QgsProject.instance()
        self.actions = []
        self.snapshots = {}  # layer id -> guard.Snapshot of definitions not loaded
        self.loading = False
        self.clearing = False
        self._watched_layers = set()
        self._write_reinserted, self._write_removed, self._write_existing = [], 0, None

    # ------------------------------------------------------------------ setup

    def initGui(self):
        icon = QIcon(ICON_PATH)
        check = QAction(icon, tr("menu_check"), self.iface.mainWindow())
        check.triggered.connect(self.show_report)
        restore = QAction(tr("menu_restore"), self.iface.mainWindow())
        restore.triggered.connect(self.restore_lost)
        for action in (check, restore):
            self.iface.addPluginToMenu(PLUGIN_NAME, action)
            self.actions.append(action)

        p = self.project
        p.layerLoaded.connect(self._on_layer_loaded)
        p.readProject.connect(self._on_read)
        p.writeProject.connect(self._on_write)
        p.writeMapLayer.connect(self._on_write_layer)
        p.projectSaved.connect(self._on_saved)
        p.aboutToBeCleared.connect(self._on_about_to_clear)
        p.cleared.connect(self._on_cleared)
        p.layersWillBeRemoved.connect(self._on_layers_will_be_removed)
        p.layersAdded.connect(self._on_layers_added)
        self._watch(p.mapLayers().values())

    def unload(self):
        p = self.project
        for signal, slot in (
            (p.layerLoaded, self._on_layer_loaded),
            (p.readProject, self._on_read),
            (p.writeProject, self._on_write),
            (p.writeMapLayer, self._on_write_layer),
            (p.projectSaved, self._on_saved),
            (p.aboutToBeCleared, self._on_about_to_clear),
            (p.cleared, self._on_cleared),
            (p.layersWillBeRemoved, self._on_layers_will_be_removed),
            (p.layersAdded, self._on_layers_added),
        ):
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        for layer in list(p.mapLayers().values()):
            if layer.id() in self._watched_layers:
                try:
                    layer.dataSourceChanged.disconnect(self._on_source_changed)
                except (TypeError, RuntimeError):
                    pass
        self._watched_layers = set()
        for action in self.actions:
            self.iface.removePluginMenu(PLUGIN_NAME, action)
            action.deleteLater()
        self.actions = []

    # ------------------------------------------------------------- messaging

    def _bar(self, text, level=Qgis.MessageLevel.Warning, button=None, callback=None, duration=0):
        QgsMessageLog.logMessage(text, PLUGIN_NAME, level)
        bar = self.iface.messageBar()
        item = bar.createMessage(PLUGIN_NAME, text)
        if button:
            push = QPushButton(button)
            push.clicked.connect(callback)
            push.clicked.connect(lambda: bar.popWidget(item))
            item.layout().addWidget(push)
        bar.pushWidget(item, level, duration)

    def _safe(self, func, *args):
        try:
            func(*args)
        except Exception:  # never break QGIS project handling
            QgsMessageLog.logMessage(traceback.format_exc(), PLUGIN_NAME, Qgis.MessageLevel.Critical)

    # ----------------------------------------------------------- project I/O

    def _on_layer_loaded(self, index, count):
        self.loading = index < count

    def _on_about_to_clear(self):
        self.clearing = True

    def _on_cleared(self):
        self.clearing = False
        self.snapshots = {}
        self._watched_layers = set()

    def _on_read(self, doc):
        self.loading = False
        self._safe(self._handle_read, doc)

    def _handle_read(self, doc):
        p = self.project
        project_file = p.fileName()
        self._watch(p.mapLayers().values())
        elements = guard.project_layer_elements(doc)
        dropped = {
            layer_id: guard.Snapshot(guard.element_to_string(e), project_file, guard.element_name(e))
            for layer_id, e in elements.items()
            if p.mapLayer(layer_id) is None
        }
        cached = {}
        for layer_id, name in guard.tree_layer_ids(doc).items():
            if layer_id in elements or p.mapLayer(layer_id) is not None:
                continue
            hit = guard.cache_load(layer_id)
            if hit:
                cached[layer_id] = guard.Snapshot(hit[0], hit[1], name)
        self.snapshots = {**cached, **dropped}
        self._store_cache(elements, project_file)
        if dropped:
            QTimer.singleShot(0, lambda: self._safe(self._restore_dropped, dropped))
        orphans = [n.name() for n in p.layerTreeRoot().findLayers() if n.layer() is None and n.layerId() not in dropped]
        if orphans:
            text = tr("orphans_on_load", count=len(orphans), names=_names(orphans))
            if cached:
                text += tr("orphans_cached", count=len(cached))
                self._bar(text, button=tr("btn_restore"), callback=self.restore_lost)
            else:
                self._bar(text, button=tr("btn_details"), callback=self.show_report)

    def _restore_dropped(self, dropped):
        restored, failed = guard.restore_layers(self.project, dropped)
        for layer_id in dropped:
            if self.project.mapLayer(layer_id) is not None:
                self.snapshots.pop(layer_id, None)
        guard.clean_dangling_dependencies(self.project)
        self._watch(self.project.mapLayers().values())
        text = tr("dropped_on_load", count=len(dropped), names=_names(s.name for s in dropped.values()))
        if restored:
            text += tr("dropped_restored", ok=len(restored))
            self.project.setDirty(True)
        if failed:
            text += tr("restore_failed", names=_names(failed))
        self._bar(text, Qgis.MessageLevel.Critical if failed else Qgis.MessageLevel.Warning)

    def _on_write(self, doc):
        self._safe(self._handle_write, doc)

    def _handle_write(self, doc):
        reinserted, _removed = guard.guard_before_write(self.project, doc, self.snapshots)
        for layer_id in list(self.snapshots):
            if self.project.mapLayer(layer_id) is not None:
                del self.snapshots[layer_id]
        self._watch(self.project.mapLayers().values())
        self._write_reinserted = reinserted
        self._write_removed = 0
        self._write_existing = set(self.project.mapLayers())

    def _on_write_layer(self, layer, element, doc):
        # The provider dependencies of a virtual layer (layers read by its
        # query) are written too and cannot be changed on the live layer, so
        # dangling ones are removed from the written XML.
        try:
            existing = self._write_existing or set(self.project.mapLayers())
            self._write_removed += guard.strip_dangling_dependencies([element], existing)
        except Exception:
            QgsMessageLog.logMessage(traceback.format_exc(), PLUGIN_NAME, Qgis.MessageLevel.Critical)

    def _on_saved(self):
        reinserted, removed = self._write_reinserted, self._write_removed
        self._write_reinserted, self._write_removed, self._write_existing = [], 0, None
        messages = []
        if reinserted:
            messages.append(tr("save_guarded", count=len(reinserted), names=_names(reinserted)))
        if removed:
            messages.append(tr("deps_cleaned", count=removed))
        if messages:
            self._bar(" ".join(messages), Qgis.MessageLevel.Warning, duration=20)
        self._safe(self._store_live_cache)

    def _store_live_cache(self):
        for layer in self._virtual_layers():
            if layer.isValid():
                try:
                    guard.cache_store(layer.id(), guard.layer_to_element(layer, self.project), self.project.fileName())
                except OSError:
                    pass

    def _store_cache(self, elements, project_file):
        """Cache the virtual layer definitions of a project read from disk."""
        for layer_id, element in elements.items():
            if element.firstChildElement("provider").text() != "virtual":
                continue
            layer = self.project.mapLayer(layer_id)
            if layer is None or not layer.isValid():
                continue
            try:
                guard.cache_store(layer_id, element, project_file)
            except OSError:
                pass

    # -------------------------------------------------------- layer changes

    def _watch(self, layers):
        for layer in layers:
            if layer.id() in self._watched_layers:
                continue
            layer.dataSourceChanged.connect(self._on_source_changed)
            self._watched_layers.add(layer.id())

    def _virtual_layers(self, exclude=()):
        return [
            layer for layer in self.project.mapLayers().values()
            if layer.providerType() == "virtual" and layer.id() not in exclude
        ]

    def _on_layers_added(self, layers):
        self._watch(layers)
        if self.loading:
            return
        self._safe(self._check_added, layers)

    def _check_added(self, layers):
        for layer in layers:
            if layer.providerType() != "virtual":
                continue
            missing = [ref for ref in guard.unresolved_layer_refs(layer) if self.project.mapLayer(ref) is None]
            if missing or not layer.isValid():
                self._bar(tr("added_missing_refs", name=layer.name(), refs=_names(missing) or "?"))

    def _on_layers_will_be_removed(self, layer_ids):
        if self.clearing or self.loading:
            return
        self._safe(self._handle_removal, list(layer_ids))

    def _handle_removal(self, layer_ids):
        removed = set(layer_ids)
        for layer_id in layer_ids:
            target = self.project.mapLayer(layer_id)
            if target is None:
                continue
            broken = [
                v.name() for v in self._virtual_layers(exclude=removed)
                if any(other is target for _ref, other in guard.virtual_references(v, self.project))
            ]
            if broken:
                self._bar(tr("removal_breaks", name=target.name(), names=_names(broken)))
        guard.clean_dangling_dependencies(self.project, removed)

    def _on_source_changed(self):
        layer = self.sender()
        if layer is None or self.loading:
            return
        QTimer.singleShot(0, lambda: self._safe(self._check_source_change, layer))

    def _check_source_change(self, layer):
        if self.project.mapLayer(layer.id()) is None:
            return
        problems = []
        for v in self._virtual_layers(exclude={layer.id()}):
            if not any(other is layer for _ref, other in guard.virtual_references(v, self.project)):
                continue
            error = guard.probe_virtual_layer(v)
            if error:
                problems.append(f"{v.name()} ({error})")
            else:
                v.reload()
        if problems:
            self._bar(tr("source_breaks", name=layer.name(), details="; ".join(problems)), Qgis.MessageLevel.Critical)

    # ------------------------------------------------------- menu commands

    def _lost_snapshots(self):
        lost = {}
        for node in self.project.layerTreeRoot().findLayers():
            if node.layer() is not None:
                continue
            snap = self.snapshots.get(node.layerId())
            if snap is None:
                hit = guard.cache_load(node.layerId())
                snap = guard.Snapshot(hit[0], hit[1], node.name()) if hit else None
            if snap is not None:
                lost[node.layerId()] = snap
        return lost

    def restore_lost(self):
        try:
            lost = self._lost_snapshots()
            if not lost:
                self._bar(tr("nothing_to_restore"), Qgis.MessageLevel.Info, duration=8)
                return
            restored, failed = guard.restore_layers(self.project, lost)
            for layer_id in lost:
                if self.project.mapLayer(layer_id) is not None:
                    self.snapshots.pop(layer_id, None)
            self._watch(self.project.mapLayers().values())
            if restored:
                self.project.setDirty(True)
            text = tr("restored", ok=len(restored))
            if failed:
                text += tr("restore_failed", names=_names(failed))
            self._bar(text, Qgis.MessageLevel.Warning if failed else Qgis.MessageLevel.Success, duration=0 if failed else 10)
        except Exception:
            QgsMessageLog.logMessage(traceback.format_exc(), PLUGIN_NAME, Qgis.MessageLevel.Critical)

    def collect_report(self):
        """[(section title, [lines])] describing the current project."""
        p = self.project
        sections = []
        lost = self._lost_snapshots()
        orphans = [
            f"{n.name()} – {tr('cached_yes') if n.layerId() in lost else tr('cached_no')}"
            for n in p.layerTreeRoot().findLayers() if n.layer() is None
        ]
        sections.append((tr("sec_orphans"), orphans))
        dangling = []
        for layer in p.mapLayers().values():
            for dep in layer.dependencies():
                if p.mapLayer(dep.layerId()) is None:
                    dangling.append(f"{layer.name()} → {dep.layerId()}")
        sections.append((tr("sec_dangling"), dangling))
        invalid, refs = [], []
        for v in self._virtual_layers():
            error = None if v.isValid() else (guard.probe_virtual_layer(v) or "?")
            if error:
                invalid.append(f"{v.name()}: {error}")
            missing = [r for r in guard.unresolved_layer_refs(v) if p.mapLayer(r) is None]
            if missing:
                refs.append(f"{v.name()} → {', '.join(missing)}")
        sections.append((tr("sec_invalid"), invalid))
        sections.append((tr("sec_refs"), refs))
        return sections

    def show_report(self):
        try:
            sections = [s for s in self.collect_report() if s[1]]
        except Exception:
            QgsMessageLog.logMessage(traceback.format_exc(), PLUGIN_NAME, Qgis.MessageLevel.Critical)
            return
        parts = []
        for title, lines in sections:
            items = "".join(f"<li>{html.escape(line)}</li>" for line in lines)
            parts.append(f"<h3>{html.escape(title)} ({len(lines)})</h3><ul>{items}</ul>")
        body = "".join(parts) + f"<p><i>{html.escape(tr('report_hint'))}</i></p>" if parts else f"<p>{tr('report_ok')}</p>"

        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle(tr("report_title"))
        dialog.resize(720, 480)
        layout = QVBoxLayout(dialog)
        browser = QTextBrowser(dialog)
        browser.setHtml(body)
        layout.addWidget(browser)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dialog)
        if any(title == tr("sec_orphans") for title, _ in sections) and self._lost_snapshots():
            restore = buttons.addButton(tr("menu_restore"), QDialogButtonBox.ButtonRole.ActionRole)
            restore.clicked.connect(lambda: (self.restore_lost(), dialog.accept()))
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()
