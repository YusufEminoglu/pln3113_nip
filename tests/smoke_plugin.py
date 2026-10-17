# -*- coding: utf-8 -*-
"""Lifecycle smoke test for tire_nip."""
from __future__ import annotations

import configparser
import os
import re
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
if str(PLUGIN_DIR.parent) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR.parent))

from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.PyQt.QtWidgets import QMainWindow, QToolBar
from qgis.core import QgsApplication
from qgis.gui import QgsMapCanvas

PACKAGE = "pln3113_nip"


def _ok(name: str, condition: bool, detail: str = "") -> bool:
    tag = "PASS" if condition else "FAIL"
    print(f"  [{tag}] {name}" + (f" - {detail}" if detail else ""))
    return bool(condition)


class _MessageBar:
    def pushMessage(self, *args, **kwargs):
        return None

    pushInfo = pushWarning = pushCritical = pushSuccess = pushMessage


class _Iface(QObject):
    """The slice of QgisInterface a plugin touches during load and unload."""

    currentLayerChanged = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self._window = QMainWindow()
        self._canvas = QgsMapCanvas(self._window)
        self._window.setCentralWidget(self._canvas)
        self._message_bar = _MessageBar()
        self.menu_entries = []
        self.toolbar_icons = []
        self.docks = []

    def mainWindow(self):
        return self._window

    def mapCanvas(self):
        return self._canvas

    def messageBar(self):
        return self._message_bar

    def activeLayer(self):
        return None

    def layerTreeView(self):
        return None

    def addToolBar(self, toolbar):
        if isinstance(toolbar, str):
            bar = QToolBar(toolbar, self._window)
            self._window.addToolBar(bar)
            return bar
        self._window.addToolBar(toolbar)
        return toolbar

    def removeToolBar(self, toolbar):
        self._window.removeToolBar(toolbar)

    def addToolBarIcon(self, action):
        self.toolbar_icons.append(action)

    def removeToolBarIcon(self, action):
        if action in self.toolbar_icons:
            self.toolbar_icons.remove(action)

    def addPluginToMenu(self, menu, action):
        self.menu_entries.append((menu, action))

    def removePluginMenu(self, menu, action):
        self.menu_entries = [e for e in self.menu_entries if e[1] is not action]

    addPluginToVectorMenu = addPluginToMenu
    removePluginVectorMenu = removePluginMenu
    addPluginToRasterMenu = addPluginToMenu
    removePluginRasterMenu = removePluginMenu

    def addDockWidget(self, area, dock):
        self.docks.append(dock)
        self._window.addDockWidget(area, dock)

    def removeDockWidget(self, dock):
        if dock in self.docks:
            self.docks.remove(dock)
        self._window.removeDockWidget(dock)


def read_metadata():
    raw = (PLUGIN_DIR / "metadata.txt").read_text(encoding="utf-8-sig", errors="replace")
    if not re.search(r"^\s*\[general\]", raw, re.M):
        raw = "[general]\n" + raw
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(raw)
    return {k.lower(): v for k, v in parser["general"].items()}


def test_metadata():
    meta = read_metadata()
    required = ("name", "version", "qgisminimumversion", "description", "author", "email")
    missing = [f for f in required if not meta.get(f, "").strip()]
    semver = re.match(r"^\d+\.\d+\.\d+", meta.get("version", ""))
    return _ok(
        "metadata has the required fields and a semver version",
        not missing and bool(semver),
        f"missing={missing}" if missing else f"version={meta.get('version')}",
    )


def test_no_percent_in_metadata():
    raw = (PLUGIN_DIR / "metadata.txt").read_text(encoding="utf-8-sig", errors="replace")
    return _ok("metadata has no literal % (breaks Hub upload)", "%" not in raw)


def test_icon_exists():
    icon = read_metadata().get("icon", "").strip()
    if not icon:
        return _ok("declared icon exists", True, "no icon declared")
    return _ok("declared icon exists", (PLUGIN_DIR / icon).exists(), icon)


def test_class_factory():
    module = __import__(PACKAGE)
    return _ok("package imports and exposes classFactory",
               hasattr(module, "classFactory"), PACKAGE)


def test_lifecycle(iface):
    module = __import__(PACKAGE)
    plugin = module.classFactory(iface)
    if plugin is None:
        return _ok("initGui / unload cycle", False, "classFactory returned None")

    toolbars_before = {tb.objectName() for tb in iface.mainWindow().findChildren(QToolBar)}
    plugin.initGui()
    app = QgsApplication.instance()
    app.processEvents()

    icon_valid = (
        plugin.action is not None
        and not plugin.action.icon().pixmap(16, 16).isNull()
    )

    plugin.unload()
    app.sendPostedEvents()
    app.processEvents()

    toolbars_after = {tb.objectName() for tb in iface.mainWindow().findChildren(QToolBar)}
    leaked = toolbars_after - toolbars_before
    return _ok(
        "initGui / unload leaves no toolbar, menu entry or dock behind (and icon is valid)",
        icon_valid and not leaked and not iface.menu_entries and not iface.toolbar_icons
        and not iface.docks,
        f"toolbars={sorted(leaked)} menu={len(iface.menu_entries)} "
        f"icons={len(iface.toolbar_icons)} docks={len(iface.docks)} icon_valid={icon_valid}",
    )


def test_dop_calculation_engine():
    from qgis.core import QgsFeature, QgsGeometry, QgsFields, QgsField, QgsRectangle
    from pln3113_nip.core.nip_calculator import NipCalculatorEngine

    fields = QgsFields()
    fields.append(QgsField("fonk"))

    # 1. Konut poligonu (100x100 = 10,000 m2)
    f1 = QgsFeature(fields)
    f1.setGeometry(QgsGeometry.fromRect(QgsRectangle(0.0, 0.0, 100.0, 100.0)))
    f1.setAttribute("fonk", "Gelişme Konut Alanı (Orta)")

    # 2. Tarım poligonu (100x100 = 10,000 m2)
    f2 = QgsFeature(fields)
    f2.setGeometry(QgsGeometry.fromRect(QgsRectangle(200.0, 0.0, 300.0, 100.0)))
    f2.setAttribute("fonk", "Tarım Alanı")

    features = [f1, f2]

    # Varsayılan hesap: Konut -> DOP İçi (Özel), Tarım -> DOP Dışı (10,000 m2)
    items_def, summary_def = NipCalculatorEngine.calculate(
        features, fields, "fonk", projeksiyon_nufus=50000
    )
    dop_def = summary_def["dop_ozet"]
    ok_default = (
        dop_def["dop_disi_alan_m2"] == 10000.0
        and dop_def["toplam_ozel_tahsis_m2"] == 10000.0
    )

    # Özel DOP Kuralı ile hesap: Tarım -> DOP İçi yap, Konut -> nDOP (DOP Dışı) yap
    rules = {
        "dop": {
            "GELISME KONUT ALANI (ORTA)": {"include": False, "dop_durumu": "DOP DIŞI", "dop_turu": "DOP DIŞI (HARİÇ)"},
            "TARIM ALANI": {"include": True, "dop_durumu": "DOP İÇİ", "dop_turu": "DOP İÇİ - ÖZEL (TAHSİS)"}
        }
    }
    items_custom, summary_custom = NipCalculatorEngine.calculate(
        features, fields, "fonk", projeksiyon_nufus=50000, rules_config=rules
    )
    dop_custom = summary_custom["dop_ozet"]
    ok_custom = (
        items_custom[0]["dop_durumu"] == "DOP DIŞI"
        and items_custom[1]["dop_durumu"] == "DOP İÇİ"
        and dop_custom["dop_disi_alan_m2"] == 10000.0  # Konut harice ayrıldı
        and dop_custom["toplam_ozel_tahsis_m2"] == 10000.0  # Tarım özel tahsise girdi
    )

    return _ok("dop calculation engine applies default and user rules correctly", ok_default and ok_custom)


def test_boundary_filter_and_clipping():
    from qgis.core import QgsFeature, QgsGeometry, QgsFields, QgsField, QgsRectangle
    from pln3113_nip.core.nip_calculator import NipCalculatorEngine

    fields = QgsFields()
    fields.append(QgsField("fonk"))

    # Sinir: (0, 0) - (100, 100) -> 10,000 m2
    sinir_geom = QgsGeometry.fromRect(QgsRectangle(0.0, 0.0, 100.0, 100.0))

    # 1. Tamamen icinde: (10, 10) - (40, 40) -> 900 m2
    f_in = QgsFeature(fields)
    f_in.setGeometry(QgsGeometry.fromRect(QgsRectangle(10.0, 10.0, 40.0, 40.0)))
    f_in.setAttribute("fonk", "Gelişme Konut Alanı (Orta)")

    # 2. Siniri kesen ada: (70, 0) - (110, 50) -> Toplam 2,000 m2, icte kalan (70..100 x 0..50) = 1,500 m2
    f_cross = QgsFeature(fields)
    f_cross.setGeometry(QgsGeometry.fromRect(QgsRectangle(70.0, 0.0, 110.0, 50.0)))
    f_cross.setAttribute("fonk", "Ticaret Alanı")

    # 3. Tamamen disarida kalan ada: (200, 200) - (250, 250) -> 2,500 m2
    f_out = QgsFeature(fields)
    f_out.setGeometry(QgsGeometry.fromRect(QgsRectangle(200.0, 200.0, 250.0, 250.0)))
    f_out.setAttribute("fonk", "Park ve Yeşil Alan")

    feats = [f_in, f_cross, f_out]

    # Test 1: CLIP modu
    items_clip, sum_clip = NipCalculatorEngine.calculate(
        feats, fields, "fonk", projeksiyon_nufus=50000,
        sinir_geom=sinir_geom, sinir_modu="clip"
    )
    s_clip = sum_clip["sinir_filtre_ozet"]
    ok_clip = (
        s_clip["aktif"] is True
        and s_clip["toplam_girdi_ada"] == 3
        and s_clip["tamamen_icinde"] == 1
        and s_clip["kesisen_islenen"] == 1
        and s_clip["sinir_disi_elenen"] == 1
        and len(items_clip) == 2
        and round(items_clip[0]["alan_m2"], 1) == 900.0
        and round(items_clip[1]["alan_m2"], 1) == 1500.0  # Kesilen parca (2000 -> 1500)
    )

    # Test 2: WITHIN modu (siniri tasan elenir)
    items_within, sum_within = NipCalculatorEngine.calculate(
        feats, fields, "fonk", projeksiyon_nufus=50000,
        sinir_geom=sinir_geom, sinir_modu="within"
    )
    s_within = sum_within["sinir_filtre_ozet"]
    ok_within = (
        s_within["tamamen_icinde"] == 1
        and s_within["kesisen_islenen"] == 0
        and s_within["sinir_disi_elenen"] == 2
        and len(items_within) == 1
        and round(items_within[0]["alan_m2"], 1) == 900.0
    )

    # Test 3: INTERSECT modu (kesisen butun olarak kalir)
    items_inter, sum_inter = NipCalculatorEngine.calculate(
        feats, fields, "fonk", projeksiyon_nufus=50000,
        sinir_geom=sinir_geom, sinir_modu="intersect"
    )
    s_inter = sum_inter["sinir_filtre_ozet"]
    ok_inter = (
        s_inter["tamamen_icinde"] == 1
        and s_inter["kesisen_islenen"] == 1
        and s_inter["sinir_disi_elenen"] == 1
        and len(items_inter) == 2
        and round(items_inter[1]["alan_m2"], 1) == 2000.0  # Butunsel korundu
    )

    # Test 4: CENTROID modu
    # f_cross (70..110 x 0..50) centroid x=90, y=25 (sinir icinde) -> dahil edilmeli
    items_cent, sum_cent = NipCalculatorEngine.calculate(
        feats, fields, "fonk", projeksiyon_nufus=50000,
        sinir_geom=sinir_geom, sinir_modu="centroid"
    )
    s_cent = sum_cent["sinir_filtre_ozet"]
    ok_cent = (
        s_cent["tamamen_icinde"] == 1
        and s_cent["kesisen_islenen"] == 1
        and s_cent["sinir_disi_elenen"] == 1
        and len(items_cent) == 2
    )

    return _ok(
        "boundary filter and clipping (clip, within, intersect, centroid, disjoint exclusion)",
        ok_clip and ok_within and ok_inter and ok_cent
    )


def run_all(iface):
    print("=" * 60)
    print(" pln3113_nip - lifecycle smoke")
    print("=" * 60)
    results = [
        test_metadata(),
        test_no_percent_in_metadata(),
        test_icon_exists(),
        test_class_factory(),
        test_lifecycle(iface),
        test_dop_calculation_engine(),
        test_boundary_filter_and_clipping(),
    ]
    passed = sum(1 for r in results if r)
    print("-" * 60)
    print(f"  {passed}/{len(results)} passed")
    return passed == len(results)


def main():
    app = QgsApplication.instance()
    owns_app = app is None
    profile = None
    if owns_app:
        profile = tempfile.TemporaryDirectory(prefix="pln3113_nip-smoke-")
        app = QgsApplication([], True, profile.name, "external")
        app.initQgis()
    iface = _Iface()
    try:
        return run_all(iface)
    finally:
        iface.mainWindow().close()
        if owns_app:
            app.exitQgis()
            profile.cleanup()


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
else:
    main()
