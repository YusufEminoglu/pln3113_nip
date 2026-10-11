# -*- coding: utf-8 -*-
"""QGIS Plugin entry point for nip_eklenti_01."""
from __future__ import annotations

def classFactory(iface):
    """Instantiate the plugin."""
    from .main_plugin import NipEklentiPlugin
    return NipEklentiPlugin(iface)
