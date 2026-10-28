"""QGIS plugin entry point."""


def classFactory(iface):
    from .plugin import VirtualLayerGuard
    return VirtualLayerGuard(iface)
