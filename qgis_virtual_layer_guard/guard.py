"""Project XML inspection, save guard and layer restore.

Everything here works on the QDomDocument QGIS reads or writes, so it does not
depend on the plugin GUI and can be used from a headless PyQGIS script.

SPDX-License-Identifier: GPL-2.0-or-later
"""

import os
import re

from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtXml import QDomDocument
from qgis.core import (
    QgsApplication,
    QgsLayerTreeLayer,
    QgsMapLayerDependency,
    QgsPathResolver,
    QgsProviderRegistry,
    QgsRasterLayer,
    QgsReadWriteContext,
    QgsVectorLayer,
    QgsVirtualLayerDefinition,
)

DEPENDENCY_TAGS = ("layerDependencies", "dataDependencies")
FROM_USER = getattr(QgsMapLayerDependency, "FromUser", None) or QgsMapLayerDependency.Origin.FromUser
CACHE_DIR = os.path.join(QgsApplication.qgisSettingsDirPath(), "virtual_layer_guard")


# ---------------------------------------------------------------- QDom helpers

def _children(element, tag):
    node = element.firstChildElement(tag)
    while not node.isNull():
        yield node
        node = node.nextSiblingElement(tag)


def _descendants(element, tag):
    nodes = element.elementsByTagName(tag)
    return [nodes.at(i).toElement() for i in range(nodes.count())]


def project_layer_elements(doc):
    """{layer id: <maplayer> element} of the <projectlayers> section."""
    root = doc.documentElement().firstChildElement("projectlayers")
    return {e.firstChildElement("id").text(): e for e in _children(root, "maplayer")}


def tree_layer_ids(doc):
    """{layer id: name} for every layer node of the saved layer tree."""
    tree = doc.documentElement().firstChildElement("layer-tree-group")
    return {e.attribute("id"): e.attribute("name") for e in _descendants(tree, "layer-tree-layer")}


def element_name(element):
    return element.firstChildElement("layername").text()


def element_to_string(element):
    doc = QDomDocument()
    doc.appendChild(doc.importNode(element, True))
    return doc.toString()


def set_content(doc, data):
    """QDomDocument.setContent() returning a plain bool (PyQt5 and PyQt6)."""
    result = doc.setContent(data)
    return bool(result[0] if isinstance(result, tuple) else result)


def string_to_element(text, doc=None):
    source = QDomDocument()
    if not set_content(source, text):
        return None
    element = source.documentElement()
    return doc.importNode(element, True).toElement() if doc is not None else element


def dangling_dependencies(element, existing_ids):
    """Dependency child elements of a <maplayer> that point to missing layers."""
    found = []
    for tag in DEPENDENCY_TAGS:
        for deps in _children(element, tag):
            for child in _children(deps, "layer"):
                if child.attribute("id") not in existing_ids:
                    found.append(child)
    return found


def strip_dangling_dependencies(elements, existing_ids):
    removed = 0
    for element in elements:
        for child in dangling_dependencies(element, existing_ids):
            child.parentNode().removeChild(child)
            removed += 1
    return removed


# --------------------------------------------------------------- path rebasing

def rebase_element(element, old_project_file, new_project_file):
    """Rewrite the (possibly relative) datasource for a new project location."""
    if not old_project_file or os.path.normcase(os.path.dirname(old_project_file)) == os.path.normcase(
        os.path.dirname(new_project_file or "")
    ):
        return
    source = element.firstChildElement("datasource")
    provider = element.firstChildElement("provider").text()
    if source.isNull() or not provider:
        return
    registry = QgsProviderRegistry.instance()
    old_ctx = QgsReadWriteContext()
    old_ctx.setPathResolver(QgsPathResolver(old_project_file))
    new_ctx = QgsReadWriteContext()
    new_ctx.setPathResolver(QgsPathResolver(new_project_file))
    absolute = registry.relativeToAbsoluteUri(provider, source.text(), old_ctx)
    relative = registry.absoluteToRelativeUri(provider, absolute, new_ctx)
    text = source.firstChild()
    if text.isText():
        text.setNodeValue(relative)


# ------------------------------------------------------------- virtual layers

def virtual_references(layer, project):
    """Layers a virtual layer reads: [(reference text, layer or None)].

    Explicit layer_ref entries and table names in the query that match a layer
    ID or a layer name of the project are reported.
    """
    definition = QgsVirtualLayerDefinition.fromUrl(QUrl.fromEncoded(layer.source().encode()))
    refs = []
    for source in definition.sourceLayers():
        if source.isReferenced():
            refs.append((source.reference(), project.mapLayer(source.reference())))
    query = definition.query()
    if query:
        tokens = set(re.findall(r'"([^"]+)"|\'([^\']+)\'|([A-Za-z_][\w]*)', query))
        words = {a or b or c for a, b, c in tokens}
        by_name = {}
        for other in project.mapLayers().values():
            by_name.setdefault(other.name(), other)
        for word in words:
            other = project.mapLayer(word) or by_name.get(word)
            if other is not None and other is not layer and all(r[1] is not other for r in refs):
                refs.append((word, other))
    return refs


def unresolved_layer_refs(layer):
    """Layer IDs in the explicit layer_ref entries of a virtual layer."""
    definition = QgsVirtualLayerDefinition.fromUrl(QUrl.fromEncoded(layer.source().encode()))
    return [s.reference() for s in definition.sourceLayers() if s.isReferenced()]


def probe_virtual_layer(layer):
    """None when the virtual layer can be rebuilt from its source, else error."""
    probe = QgsVectorLayer(layer.source(), "virtual_layer_guard_probe", "virtual")
    if probe.isValid():
        return None
    provider = probe.dataProvider()
    message = provider.error().summary() if provider is not None else ""
    return re.sub(r"<[^>]+>", "", message or probe.error().summary()).strip() or "?"


def layer_to_element(layer, project):
    """<maplayer> element of a live layer, as QGIS writes it into a project."""
    doc = QDomDocument("qgis")
    element = doc.createElement("maplayer")
    ctx = QgsReadWriteContext()
    ctx.setPathResolver(project.pathResolver())
    layer.writeLayerXml(element, doc, ctx)
    doc.appendChild(element)
    return element


# ---------------------------------------------------------------- disk cache

def _cache_file(layer_id):
    safe = re.sub(r"[^\w.-]", "_", layer_id)
    return os.path.join(CACHE_DIR, safe + ".xml")


def cache_store(layer_id, element, project_file):
    os.makedirs(CACHE_DIR, exist_ok=True)
    doc = QDomDocument()
    wrapper = doc.createElement("virtual-layer-guard")
    wrapper.setAttribute("project", project_file or "")
    wrapper.appendChild(doc.importNode(element, True))
    doc.appendChild(wrapper)
    with open(_cache_file(layer_id), "w", encoding="utf-8") as handle:
        handle.write(doc.toString())


def cache_load(layer_id):
    """(maplayer element string, project file it was saved with) or None."""
    path = _cache_file(layer_id)
    if not os.path.exists(path):
        return None
    doc = QDomDocument()
    with open(path, "rb") as handle:
        if not set_content(doc, handle.read()):
            return None
    wrapper = doc.documentElement()
    layer = wrapper.firstChildElement("maplayer")
    if layer.isNull() or layer.firstChildElement("id").text() != layer_id:
        return None
    return element_to_string(layer), wrapper.attribute("project")


# --------------------------------------------------------------------- guard

class Snapshot:
    """A <maplayer> definition kept as text with the project file it came from."""

    def __init__(self, xml, project_file, name):
        self.xml = xml
        self.project_file = project_file
        self.name = name


def guard_before_write(project, doc, snapshots):
    """Fix the live project from QgsProject.writeProject.

    The signal is emitted after the layer tree is written into ``doc`` but
    before the layers are, so layers added and dependencies changed here end
    up in the file. Layer tree entries without a layer get their saved
    definition back (as an invalid layer if it cannot be loaded, so the
    definition is still written), then dependencies on missing layers are
    removed. Returns (names of restored layers, number of removed dependencies).
    """
    lost = {
        layer_id: snapshots[layer_id]
        for layer_id in tree_layer_ids(doc)
        if project.mapLayer(layer_id) is None and layer_id in snapshots
    }
    restored, failed = restore_layers(project, lost, keep_invalid=True) if lost else ([], [])
    return restored + failed, clean_dangling_dependencies(project)


def clean_dangling_dependencies(project, removed_ids=()):
    """Drop dependencies on layers that are not (or soon no longer) in the project."""
    removed_ids = set(removed_ids)
    existing = set(project.mapLayers()) - removed_ids
    changed = 0
    for layer in project.mapLayers().values():
        if layer.id() in removed_ids:
            continue
        deps = layer.dependencies()
        keep = {d for d in deps if d.layerId() in existing}
        if len(keep) != len(deps):
            # dependencies() also lists provider (virtual query) dependencies;
            # setDependencies() only stores the user-defined part.
            layer.setDependencies({d for d in keep if d.origin() == FROM_USER})
            changed += len(deps) - len(keep)
    return changed


def restore_layers(project, snapshots, keep_invalid=False):
    """Load saved definitions into the live project.

    Virtual layers that read other restored layers are retried after them.
    Layer tree nodes that already exist are re-attached, others are created on
    top. With ``keep_invalid`` definitions that cannot be loaded are added as
    invalid layers, which QGIS writes back unchanged on save.
    Returns (restored names, failed names).
    """
    ctx = QgsReadWriteContext()
    ctx.setPathResolver(project.pathResolver())
    ctx.setProjectTranslator(project)
    pending = []
    for layer_id, snap in snapshots.items():
        element = string_to_element(snap.xml)
        if element is None:
            continue
        rebase_element(element, snap.project_file, project.fileName())
        pending.append((layer_id, snap.name, element))

    restored, loaded = [], []
    for _round in range(len(pending) + 1):
        existing = set(project.mapLayers()) | {p[0] for p in pending}
        left = []
        for layer_id, name, element in pending:
            strip_dangling_dependencies([element], existing)
            kind = element.attribute("type")
            layer = QgsRasterLayer() if kind == "raster" else QgsVectorLayer()
            if layer.readLayerXml(element, ctx) and layer.isValid():
                project.addMapLayer(layer, False)
                restored.append(name)
                loaded.append(layer)
            else:
                left.append((layer_id, name, element))
        if len(left) == len(pending):
            break
        pending = left
        if not pending:
            break

    if keep_invalid:
        for _layer_id, _name, element in pending:
            layer = QgsRasterLayer() if element.attribute("type") == "raster" else QgsVectorLayer()
            layer.readLayerXml(element, ctx)
            layer.setOriginalXmlProperties(element_to_string(element))
            project.addMapLayer(layer, False)
            loaded.append(layer)

    for layer in loaded:
        if hasattr(layer, "resolveReferences"):
            layer.resolveReferences(project)
    root = project.layerTreeRoot()
    root.resolveReferences(project)
    attached = {node.layerId() for node in root.findLayers() if node.layer() is not None}
    for layer in loaded:
        if layer.id() not in attached:
            root.insertChildNode(0, QgsLayerTreeLayer(layer))
        layer.triggerRepaint()
    return restored, [p[1] for p in pending]
