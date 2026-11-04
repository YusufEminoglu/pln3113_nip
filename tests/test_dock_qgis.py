# -*- coding: utf-8 -*-
"""The real PLN3113 NİP dock and plugin, offscreen, in a 1366x728 window.

Run under a QGIS Python from the directory that contains the plugin folder,
with QGIS_CUSTOM_CONFIG_PATH set to a throwaway directory (TRAPS 4.6):

    python-qgis-ltr.bat -m pln3113_nip.tests.test_dock_qgis   # QGIS 3.44
    python-qgis.bat     -m pln3113_nip.tests.test_dock_qgis   # QGIS 4.2

No request leaves this computer: a QGIS request preprocessor refuses every
non-local host and browser opens are only recorded.

Covers item 4 (N5, N8), the dock side of N10/N11/N12 and contract C2 of
docs/DEVELOPMENT_SET_v1.2.md. Every check fails on 1.1.6 for the reason in
its docstring.

Where contract C1 (core/projection.py ``project_trend``) or the new
Processing algorithms are missing from the code under test, the suite uses
stand-ins and says so on an [INFO] line; the dock side is then still tested.
"""
from __future__ import annotations

import contextlib
import faulthandler
import importlib
import os
import re
import sys
import tempfile
import threading
import time
import traceback
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SYSTEM_FONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
if os.path.isdir(_SYSTEM_FONTS):
    # Offscreen Qt has no fonts of its own (TRAPS 4.3); with the system's the
    # text is drawn and measured as on screen.
    os.environ.setdefault("QT_QPA_FONTDIR", _SYSTEM_FONTS)
if not os.environ.get("QGIS_CUSTOM_CONFIG_PATH"):
    os.environ["QGIS_CUSTOM_CONFIG_PATH"] = tempfile.mkdtemp(prefix="nip-dock-profile-")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
PACKAGE = PLUGIN_DIR.name
if str(PLUGIN_DIR.parent) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR.parent))

from qgis.core import QgsApplication  # noqa: E402

THEMES = ("default", "Night Mapping", "Blend of Gray")
AA = 4.5
MAX_DOCK_WIDTH = 340
METHODS = ("aritmetik", "geometrik", "iller_bankasi", "regresyon", "polinom", "lojistik")
NEW_ALGS = ("nufus_projeksiyonu", "kohort_projeksiyonu", "mahalle_dagitimi", "kirilganlik_endeksi")
LINKED_ALGS = ("nufus_projeksiyonu", "kohort_projeksiyonu", "mahalle_dagitimi", "kirilganlik_endeksi")
STANDINS = []


class CheckFailed(AssertionError):
    pass


def check(condition, message):
    if not condition:
        raise CheckFailed(message)


def fail_if(problems):
    if problems:
        raise CheckFailed("; ".join(problems[:8]) + (f" (+{len(problems) - 8} more)" if len(problems) > 8 else ""))


def pump(seconds=0.05):
    app = QgsApplication.instance()
    end = time.monotonic() + seconds
    while True:
        app.processEvents()
        if time.monotonic() >= end:
            return
        time.sleep(0.005)


# ---------------------------------------------------------------------------
# Offline guard
# ---------------------------------------------------------------------------
class Offline:
    CLOSED = "http://127.0.0.1:9"

    def __init__(self):
        self._lock = threading.Lock()
        self.refused, self.opened = [], []

    def _guard(self, request):
        from qgis.PyQt.QtCore import QUrl

        url = request.url()
        host = str(url.host()).lower()
        if str(url.scheme()).lower() not in ("http", "https", "ftp", "ws", "wss") \
                or host in ("127.0.0.1", "localhost", "::1"):
            return
        with self._lock:
            self.refused.append(str(url.toString()))
        request.setUrl(QUrl(f"{self.CLOSED}/refused-by-the-offline-guard"))

    def _record(self, target, *_a, **_k):
        with self._lock:
            self.opened.append(target.toString() if hasattr(target, "toString") else str(target))
        return True

    def install(self):
        import webbrowser

        from qgis.core import QgsNetworkAccessManager
        from qgis.PyQt.QtGui import QDesktopServices

        webbrowser.open = webbrowser.open_new = webbrowser.open_new_tab = self._record
        QDesktopServices.openUrl = staticmethod(self._record)
        QgsNetworkAccessManager.setRequestPreprocessor(self._guard)


OFFLINE = Offline()


# ---------------------------------------------------------------------------
# A QGIS-shaped window
# ---------------------------------------------------------------------------
class MessageBar:
    def __init__(self):
        self.notes = []

    def pushMessage(self, *args, **_kw):  # noqa: N802 - QGIS naming
        self.notes.append(tuple(str(a) for a in args))

    pushInfo = pushWarning = pushCritical = pushSuccess = pushMessage


class Iface:
    def __init__(self, window, canvas):
        self._window, self._canvas, self._bar = window, canvas, MessageBar()
        self.menu_entries, self.toolbar_icons, self.docks = [], [], []

    def mainWindow(self):  # noqa: N802
        return self._window

    def mapCanvas(self):  # noqa: N802
        return self._canvas

    def messageBar(self):  # noqa: N802
        return self._bar

    def activeLayer(self):  # noqa: N802
        return None

    def layerTreeView(self):  # noqa: N802
        return None

    def addToolBarIcon(self, action):  # noqa: N802
        self.toolbar_icons.append(action)

    def removeToolBarIcon(self, action):  # noqa: N802
        if action in self.toolbar_icons:
            self.toolbar_icons.remove(action)

    def addPluginToMenu(self, menu, action):  # noqa: N802
        self.menu_entries.append((menu, action))

    def removePluginMenu(self, menu, action):  # noqa: N802
        self.menu_entries = [e for e in self.menu_entries if e[1] is not action]

    def addDockWidget(self, area, dock):  # noqa: N802
        self._window.addDockWidget(area, dock)
        self.docks.append(dock)

    def removeDockWidget(self, dock):  # noqa: N802
        self._window.removeDockWidget(dock)
        if dock in self.docks:
            self.docks.remove(dock)


class BoxRecorder:
    """Every QMessageBox is recorded and answered, never shown."""

    def __init__(self):
        self.shown = []

    def install(self):
        from qgis.PyQt.QtWidgets import QMessageBox

        recorder = self

        def static(kind):
            def show(_parent, _title, text, *_args, **_kwargs):
                recorder.shown.append((kind, str(text)))
                return QMessageBox.StandardButton.Ok
            return staticmethod(show)

        def exec_(box, *_a, **_k):
            recorder.shown.append(("box", box.text()))
            return 0

        QMessageBox.exec = exec_
        QMessageBox.exec_ = exec_
        for kind in ("critical", "warning", "information", "question"):
            setattr(QMessageBox, kind, static(kind))


class Rig:
    """A 1366x728 main window with a menu bar, two tool bars and a status bar
    (the chrome QGIS puts around a dock), the plugin loaded and its dock open."""

    def __init__(self):
        from qgis.gui import QgsMapCanvas
        from qgis.PyQt.QtWidgets import QMainWindow, QToolBar

        self.window = QMainWindow()
        self.window.resize(1366, 728)
        self.canvas = QgsMapCanvas(self.window)
        self.window.setCentralWidget(self.canvas)
        self.window.menuBar().addMenu("Proje")
        for name in ("Dosya", "Harita"):
            bar = QToolBar(name, self.window)
            bar.setFixedHeight(34)
            bar.addAction(name)
            self.window.addToolBar(bar)
        self.window.statusBar().showMessage("Hazır")
        self.window.show()
        self.iface = Iface(self.window, self.canvas)
        self.boxes = BoxRecorder()
        self.boxes.install()
        module = importlib.import_module(PACKAGE)
        self.plugin = module.classFactory(self.iface)
        self.plugin.initGui()
        self.plugin.open_dock()
        self.dock = self.plugin.dock
        pump(0.3)

    def close(self):
        with contextlib.suppress(Exception):
            self.plugin.unload()
        self.window.close()
        self.window.deleteLater()
        pump(0.1)


def pages(dock):
    count = dock.main_stack.count()
    for index in range(count):
        dock.set_page(index)
        pump(0.05)
        yield index, dock.nav_list.item(index).text()


# ---------------------------------------------------------------------------
# Pixel contrast
# ---------------------------------------------------------------------------
def _lum(rgb):
    ch = [v / 255.0 for v in rgb]
    ch = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in ch]
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]


def _ratio(a, b):
    high, low = sorted((_lum(a), _lum(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def measured_contrast(image, rect=None):
    """Background = the most frequent colour; text = the pixel colour with the
    highest contrast against it (the stem colour of the glyphs)."""
    x0, y0 = (rect.x(), rect.y()) if rect is not None else (0, 0)
    w, h = (rect.width(), rect.height()) if rect is not None else (image.width(), image.height())
    counts = {}
    for y in range(max(0, y0), min(image.height(), y0 + h)):
        for x in range(max(0, x0), min(image.width(), x0 + w)):
            c = image.pixelColor(x, y)
            key = (c.red(), c.green(), c.blue())
            counts[key] = counts.get(key, 0) + 1
    if len(counts) < 2:
        return None
    bg = max(counts, key=counts.get)
    fg = max(counts, key=lambda k: _ratio(k, bg))
    return _ratio(fg, bg)


def _texts_on_screen(dock):
    """(label, widget, rect-or-None) for every visible, enabled text the dock draws."""
    from qgis.PyQt.QtCore import QRect
    from qgis.PyQt.QtWidgets import QAbstractButton, QGroupBox, QLabel, QTabBar

    out = []
    for w in dock.findChildren(QLabel) + dock.findChildren(QAbstractButton):
        if not w.isVisible() or not w.isEnabled() or w.width() < 8 or w.height() < 8:
            continue
        if not str(w.text()).strip():
            continue
        if not w.visibleRegion().boundingRect().height() >= 8:
            continue
        out.append((f"{type(w).__name__} {re.sub(r'<[^>]+>', '', w.text())[:40]!r}", w, None))
    for box in dock.findChildren(QGroupBox):
        if box.isVisible() and box.title().strip():
            fm = box.fontMetrics()
            width = (fm.horizontalAdvance(box.title()) if hasattr(fm, "horizontalAdvance") else fm.width(box.title()))
            out.append((f"QGroupBox title {box.title()[:40]!r}", box,
                        QRect(4, 0, min(box.width() - 4, width + 40), fm.height() + 6)))
    for bar in dock.findChildren(QTabBar):
        if bar.isVisible():
            for i in range(bar.count()):
                r = bar.tabRect(i)
                if r.isValid() and r.width() > 8:
                    out.append((f"tab {bar.tabText(i)[:30]!r}", bar, r))
    return out


def grab_in_dock(dock, widget, rect=None):
    """The pixels of ``rect`` (widget coordinates) as the dock draws them, parents'
    backgrounds included (a widget's own grab leaves transparent parts black).
    The page scroll area is scrolled so the rect is on screen first."""
    from qgis.PyQt.QtCore import QRect
    from qgis.PyQt.QtWidgets import QScrollArea

    rect = QRect(rect) if rect is not None else widget.rect()
    scroll = next((s for s in dock.findChildren(QScrollArea) if s.widget() is dock.main_stack), None)
    if scroll is not None and scroll.widget().isAncestorOf(widget):
        centre = widget.mapTo(scroll.widget(), rect.center())
        scroll.ensureVisible(centre.x(), centre.y(), 10, rect.height() // 2 + 4)
        pump(0.01)
        viewport = scroll.viewport()
        top_left = widget.mapTo(viewport, rect.topLeft())
        visible = QRect(top_left, rect.size()).intersected(viewport.rect())
        if visible.height() < min(rect.height(), 10):
            return None
        rect = QRect(widget.mapFrom(viewport, visible.topLeft()), visible.size())
    return dock.grab(QRect(widget.mapTo(dock, rect.topLeft()), rect.size())).toImage()


def nav_contrasts(dock):
    """Navigation rail texts: the selected item and an unselected one."""
    rail = dock.nav_list
    out = []
    for row in range(rail.count()):
        r = rail.visualItemRect(rail.item(row))
        if r.isValid() and r.bottom() <= rail.viewport().height():
            top_left = rail.viewport().mapTo(dock, r.topLeft())
            from qgis.PyQt.QtCore import QRect
            image = dock.grab(QRect(top_left, r.size())).toImage()
            ratio = measured_contrast(image)
            if ratio is not None:
                state = "selected" if row == rail.currentRow() else "item"
                out.append((ratio, "navigation", f"{state} {rail.item(row).text()!r}"))
    return out


def lowest_contrasts(dock):
    from qgis.PyQt.QtWidgets import QTabWidget

    results = {}
    for ratio, page, name in nav_contrasts(dock):
        results[(page, name)] = ratio
    for _index, page_name in pages(dock):
        page = dock.main_stack.currentWidget()
        tab_widgets = [t for t in page.findChildren(QTabWidget)] or [None]
        for tabs in tab_widgets:
            indices = range(tabs.count()) if tabs is not None else [None]
            for ti in indices:
                if tabs is not None:
                    tabs.setCurrentIndex(ti)
                    pump(0.02)
                for name, widget, rect in _texts_on_screen(dock):
                    key = (page_name, name)
                    if key in results:
                        continue
                    image = grab_in_dock(dock, widget, rect)
                    ratio = measured_contrast(image) if image is not None else None
                    if ratio is not None:
                        results[key] = ratio
    return sorted((ratio, page, name) for (page, name), ratio in results.items())


def check_contrast_three_themes(_rig_factory):
    """N5: every text in the dock is ≥ 4.5:1 under default, Night Mapping and Blend of Gray.

    1.1.6 coloured text inline (#64748b on its card 4.14:1 in default) and read
    the palette's window text, which Blend of Gray sets near-black on a dark
    window: 1.02-2.5:1 in the dark themes.
    """
    problems, summary = [], []
    for theme in THEMES:
        QgsApplication.setUITheme(theme)
        pump(0.1)
        rig = _rig_factory()
        try:
            measured = lowest_contrasts(rig.dock)
        finally:
            rig.close()
        low = [m for m in measured if m[0] < AA]
        summary.append(f"{theme}: {len(measured)} texts, lowest {measured[0][0]:.2f}" if measured else f"{theme}: none")
        for ratio, page, name in low[:6]:
            problems.append(f"{theme} / {page}: {name} {ratio:.2f}:1")
        if len(measured) < 60:
            problems.append(f"{theme}: only {len(measured)} texts measured")
    QgsApplication.setUITheme("default")
    pump(0.1)
    source = (PLUGIN_DIR / "dock.py").read_text(encoding="utf-8")
    inline = [f"line {n}: {line.strip()[:70]}" for n, line in enumerate(source.splitlines(), 1)
              if re.search(r"#[0-9a-fA-F]{6}\b", line)
              and not re.search(r"createSimple|['\"](outline_)?color['\"]\s*:", line)]
    if inline:
        problems.append(f"{len(inline)} inline UI colours in dock.py, e.g. {inline[:3]}")
    fail_if(problems)
    return "; ".join(summary)


# ---------------------------------------------------------------------------
# Width
# ---------------------------------------------------------------------------
def check_width_1366x728(rig_factory):
    """N8: the dock fits ~340 px and no page needs a horizontal scrollbar at 1366x728.

    1.1.6 pages asked for 516-672 px: half a 1366 screen, or a horizontal
    scrollbar on every page of a narrower dock.
    """
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtWidgets import QScrollArea

    rig = rig_factory()
    problems = []
    try:
        dock = rig.dock
        hint = dock.minimumSizeHint().width()
        if hint > MAX_DOCK_WIDTH or dock.minimumWidth() > MAX_DOCK_WIDTH:
            problems.append(f"dock minimum width {max(hint, dock.minimumWidth())} px > {MAX_DOCK_WIDTH}")
        rig.window.resizeDocks([dock], [MAX_DOCK_WIDTH], Qt.Orientation.Horizontal)
        pump(0.3)
        scroll = next((s for s in dock.findChildren(QScrollArea) if s.widget() is dock.main_stack), None)
        check(scroll is not None, "no scroll area around the page stack")
        widest = []
        for _index, name in pages(dock):
            pump(0.05)
            need = max(dock.main_stack.currentWidget().minimumSizeHint().width(),
                       dock.main_stack.minimumSizeHint().width())
            have = scroll.viewport().width()
            widest.append((need, name))
            if scroll.horizontalScrollBar().isVisible() or need > have:
                problems.append(f"page {name!r} needs {need} px in a {have} px viewport")
        rail = dock.nav_list
        last = rail.visualItemRect(rail.item(rail.count() - 1))
        reachable = last.bottom() <= rail.viewport().height() or \
            rail.verticalScrollBarPolicy() != Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        if not reachable:
            problems.append(f"the last navigation item ends at y={last.bottom()} of {rail.viewport().height()} "
                            "and the rail cannot scroll")
        detail = (f"dock {dock.width()} px (minimum {hint}); widest page {max(widest)[1]!r} "
                  f"{max(widest)[0]} px in {scroll.viewport().width()} px")
    finally:
        rig.close()
    fail_if(problems)
    return detail


# ---------------------------------------------------------------------------
# Projection (C1 stand-in when missing)
# ---------------------------------------------------------------------------
def _standin_project_trend(years, populations, method, target_year):
    """Arithmetic line through the first and last point; flags itself."""
    y0, y1 = years[0], years[-1]
    p0, p1 = populations[0], populations[-1]
    rate = (p1 - p0) / float(y1 - y0)
    series = [(y, p0 + rate * (y - y0)) for y in range(y0, target_year + 1)]
    return {"value": p0 + rate * (target_year - y0), "series": series, "r2": 0.987,
            "backtest_pct": 1.25, "warnings": ["Yer tutucu uyarı (test)"]}


def projection_module():
    try:
        module = importlib.import_module(f"{PACKAGE}.core.projection")
        if callable(getattr(module, "project_trend", None)):
            return module, True
    except ImportError:
        pass
    module = types.ModuleType(f"{PACKAGE}.core.projection")
    module.project_trend = _standin_project_trend
    module.METHODS = METHODS
    sys.modules[module.__name__] = module
    STANDINS.append("C1 core/projection.project_trend")
    return module, False


def _fill_table(table, rows):
    from qgis.PyQt.QtWidgets import QTableWidgetItem

    table.setRowCount(len(rows))
    for r, (year, pop) in enumerate(rows):
        table.setItem(r, 0, QTableWidgetItem(str(year)))
        table.setItem(r, 1, QTableWidgetItem(str(pop)))


def _digits(text):
    return re.sub(r"[^\d]", "", text)


def _group(value):
    return f"{int(round(value)):,}".replace(",", ".")


def check_projection_fills_target(rig_factory):
    """N11 + C2: the dock projects population with C1 and fills the target spinbox.

    1.1.6 had only a manual target spinbox (max 500 000) and no projection at all.
    """
    from qgis.PyQt.QtWidgets import QGroupBox

    module, real = projection_module()
    rig = rig_factory()
    problems = []
    try:
        dock = rig.dock
        boxes = [b for b in dock.findChildren(QGroupBox) if "Nüfus Projeksiyonu" in b.title()]
        check(boxes, "no “Nüfus Projeksiyonu” section in the dock")
        for name in ("tbl_proj_input", "cmb_proj_method", "spn_proj_target_year", "btn_proj_run",
                     "lbl_proj_result", "btn_proj_apply", "spn_proj_nufus"):
            check(hasattr(dock, name), f"the dock has no {name}")
        methods = [dock.cmb_proj_method.itemData(i) for i in range(dock.cmb_proj_method.count())]
        missing = [m for m in METHODS if m not in methods]
        if missing:
            problems.append(f"methods missing from the choice: {missing}")
        rows = [(1990, 77314), (2000, 79500), (2015, 82102), (2025, 87571)]
        years, pops = [r[0] for r in rows], [r[1] for r in rows]
        for method in ("aritmetik", "geometrik"):
            _fill_table(dock.tbl_proj_input, rows)
            dock.cmb_proj_method.setCurrentIndex(dock.cmb_proj_method.findData(method))
            dock.spn_proj_target_year.setValue(2045)
            dock.btn_proj_run.click()
            pump(0.1)
            expected = module.project_trend(years, pops, method, 2045)
            text = dock.lbl_proj_result.text()
            plain = re.sub(r"<[^>]+>", " ", text)
            if _group(expected["value"]) not in plain:
                problems.append(f"{method}: {_group(expected['value'])} not in the result {plain[:120]!r}")
            if "R²" not in plain:
                problems.append(f"{method}: no R² in the result")
            if expected.get("r2") is not None and f"{expected['r2']:.3f}".replace(".", ",") not in plain \
                    and f"{expected['r2']:.3f}" not in plain:
                problems.append(f"{method}: R² {expected['r2']:.3f} not shown")
            if expected.get("backtest_pct") is not None and "sınama" not in plain.lower():
                problems.append(f"{method}: no backtest line")
            for warning in expected.get("warnings") or []:
                if str(warning)[:40] not in plain:
                    problems.append(f"{method}: warning {str(warning)[:40]!r} not shown")
            dock.spn_proj_nufus.setValue(1000)
            dock.btn_proj_apply.click()
            pump(0.05)
            if dock.spn_proj_nufus.value() != int(round(expected["value"])):
                problems.append(f"{method}: target spinbox {dock.spn_proj_nufus.value()} "
                                f"≠ projection {int(round(expected['value']))}")
        # A city larger than the old 500 000 ceiling is carried over, not clamped.
        saved = module.project_trend
        module.project_trend = lambda *a, **k: {"value": 1234567.0, "series": [], "r2": 0.99,
                                                "backtest_pct": 0.5, "warnings": []}
        try:
            dock.btn_proj_run.click()
            pump(0.05)
            dock.btn_proj_apply.click()
            pump(0.05)
        finally:
            module.project_trend = saved
        if dock.spn_proj_nufus.value() != 1234567:
            problems.append(f"a 1 234 567 projection became {dock.spn_proj_nufus.value()} in the spinbox")
        # Bad input is a message in the dock, not a box or an exception.
        rig.boxes.shown.clear()
        _fill_table(dock.tbl_proj_input, [(2020, 1000)])
        dock.btn_proj_run.click()
        pump(0.05)
        if rig.boxes.shown or not dock.lbl_proj_result.text().strip():
            problems.append("a single row did not give a message in the dock")
        source = (PLUGIN_DIR / "dock.py").read_text(encoding="utf-8")
        if "project_trend" not in source:
            problems.append("dock.py does not call project_trend (C2)")
        # a power operator (not **kwargs), exponentials, logarithms or curve fitting
        formulas = [m.group(0) for m in re.finditer(
            r"[\w)\]]\s*\*\*\s*[\w(]|math\.(exp|log)|polyfit|np\.linalg|curve_fit", source)]
        if formulas:
            problems.append(f"dock.py computes formulas itself (C2): {sorted(set(formulas))}")
    finally:
        rig.close()
    fail_if(problems)
    return f"{'real C1' if real else 'C1 stand-in'}: 2 methods projected and carried to the spinbox"


class _StandinAlg:
    pass


def standin_algorithms():
    """Register empty algorithms for the new ids when the code under test lacks them."""
    registry = QgsApplication.processingRegistry()
    have = {a.id().split(":")[-1] for a in registry.algorithms()}
    missing = [n for n in NEW_ALGS if n not in have]
    if not missing:
        return
    from qgis.core import QgsProcessingAlgorithm, QgsProcessingProvider

    def make(alg_name):
        class Alg(QgsProcessingAlgorithm):
            def name(self):
                return alg_name

            def displayName(self):  # noqa: N802
                return alg_name

            def createInstance(self):  # noqa: N802
                return Alg()

            def initAlgorithm(self, config=None):  # noqa: N802
                pass

            def processAlgorithm(self, parameters, context, feedback):  # noqa: N802
                return {}
        return Alg

    class Provider(QgsProcessingProvider):
        def loadAlgorithms(self):  # noqa: N802
            for alg_name in missing:
                self.addAlgorithm(make(alg_name)())

        def id(self):
            return "pln3113_nip"

        def name(self):
            return "stand-in"

    provider = Provider()
    registry.addProvider(provider)
    _StandinAlg.provider = provider
    STANDINS.append(f"algorithms {missing}")


def check_algorithm_links_open_dialogs(rig_factory):
    """N11: the projection, cohort, allocation and vulnerability tools open their Processing dialogs.

    1.1.6 had none of these tools and nothing in the dock pointing at them.
    """
    import processing

    rig = rig_factory()
    standin_algorithms()
    opened = []
    saved = getattr(processing, "execAlgorithmDialog", None)
    processing.execAlgorithmDialog = lambda alg_id, *a, **k: opened.append(alg_id) or {}
    problems = []
    try:
        dock = rig.dock
        for name in LINKED_ALGS:
            button = getattr(dock, f"btn_open_{name}", None)
            if button is None:
                problems.append(f"no button for {name}")
                continue
            before = len(opened)
            button.click()
            pump(0.05)
            if len(opened) != before + 1 or not str(opened[-1]).endswith(f":{name}"):
                problems.append(f"{name}: dialog calls {opened[before:]}")
            elif QgsApplication.processingRegistry().algorithmById(opened[-1]) is None:
                problems.append(f"{name}: {opened[-1]} is not a registered algorithm id")
    finally:
        if saved is not None:
            processing.execAlgorithmDialog = saved
        rig.close()
    fail_if(problems)
    return f"opened {opened}"


# ---------------------------------------------------------------------------
# Names (N10) and the network note
# ---------------------------------------------------------------------------
def _all_texts(dock):
    from qgis.PyQt.QtWidgets import (QAbstractButton, QComboBox, QGroupBox, QLabel, QLineEdit,
                                     QTableWidget, QTabWidget, QTextEdit)

    texts = [dock.windowTitle()]
    for w in dock.findChildren(QLabel) + dock.findChildren(QAbstractButton):
        texts += [w.text(), w.toolTip()]
    for w in dock.findChildren(QGroupBox):
        texts += [w.title(), w.toolTip()]
    for w in dock.findChildren(QComboBox):
        texts += [w.itemText(i) for i in range(w.count())]
    for w in dock.findChildren(QLineEdit) + dock.findChildren(QTextEdit):
        texts.append(w.placeholderText())
    for w in dock.findChildren(QTabWidget):
        texts += [w.tabText(i) for i in range(w.count())]
    for w in dock.findChildren(QTableWidget):
        for c in range(w.columnCount()):
            item = w.horizontalHeaderItem(c)
            texts.append(item.text() if item else "")
        for r in range(w.rowCount()):
            for c in range(w.columnCount()):
                item = w.item(r, c)
                texts.append(item.text() if item else "")
    for i in range(dock.nav_list.count()):
        texts += [dock.nav_list.item(i).text(), dock.nav_list.item(i).toolTip()]
    return [t for t in texts if t]


def check_names_and_network_note(rig_factory):
    """N10: the dock, menu and toolbar carry the PLN3113 name; Tire appears only as an example.
    The dashboard export says it loads plotly, Leaflet and OSM tiles from the internet.

    1.1.6 titled the dock "Tire NİP Analiz Stüdyosu", the menu "&Tire NİP
    Stüdyosu", a "Tire Tarihsel Nüfus" panel, and said nothing about the
    report's public hosts.
    """
    rig = rig_factory()
    problems = []
    try:
        dock = rig.dock
        names = [("dock title", dock.windowTitle()), ("action", rig.plugin.action.text()),
                 ("action tooltip", rig.plugin.action.toolTip())]
        names += [("menu", menu) for menu, _a in rig.iface.menu_entries]
        names += [("menu action", a.text()) for _m, a in rig.iface.menu_entries]
        for what, text in names:
            if "tire" in text.casefold():
                problems.append(f"{what} names Tire: {text!r}")
        for what in ("dock title", "action"):
            text = dict(names)[what]
            if "PLN3113" not in text:
                problems.append(f"{what} lacks the PLN3113 name: {text!r}")
        for text in _all_texts(dock):
            plain = re.sub(r"<[^>]+>", " ", text)
            if re.search(r"\btire\b|tire_", plain.casefold()) and "örnek" not in plain.casefold():
                problems.append(f"Tire outside an example: {plain.strip()[:80]!r}")
        notes = [t for t in _all_texts(dock) if "plotly" in t.casefold() and "leaflet" in t.casefold()
                 and ("openstreetmap" in t.casefold() or "osm" in t.casefold()) and "internet" in t.casefold()]
        if not notes:
            problems.append("no line near the export says the report loads plotly/Leaflet/OSM from the internet")
    finally:
        rig.close()
    fail_if(problems)
    return f"names {[t for _w, t in names[:2]]}; note {notes[0][:70]!r}"


# ---------------------------------------------------------------------------
# The dock's NİP run: estimated DOP and a boundary in another CRS (N2, N6, N12)
# ---------------------------------------------------------------------------
def _blocks_layer():
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsRectangle, QgsVectorLayer

    # The field comes from the URI: QgsField(name, QVariant.String) fails on QGIS 4 (TRAPS 3.2b).
    layer = QgsVectorLayer("MultiPolygon?crs=EPSG:5253&field=fonk:string(80)", "test_adalar", "memory")
    x0, y0 = 503000.0, 4218000.0   # inside TM27 (EPSG:5253), about Tire/İzmir
    feats = []
    for i, name in enumerate(["Gelişme Konut Alanı (Orta Yoğunluk)", "Park ve Yeşil Alan", "Ticaret Alanı"]):
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromRect(QgsRectangle(x0 + i * 120, y0, x0 + i * 120 + 100, y0 + 100)))
        f.setAttribute("fonk", name)
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    QgsProject.instance().addMapLayer(layer)
    return layer


def _boundary_4326(blocks):
    from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeature, QgsGeometry,
                           QgsProject, QgsVectorLayer)

    ext = blocks.extent()
    ext.grow(30.0)
    xform = QgsCoordinateTransform(blocks.crs(), QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance())
    geom = QgsGeometry.fromRect(ext)
    geom.transform(xform)
    layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "test_sinir_4326", "memory")
    f = QgsFeature()
    f.setGeometry(geom)
    layer.dataProvider().addFeatures([f])
    layer.updateExtents()
    QgsProject.instance().addMapLayer(layer)
    return layer


def _run_nip(dock, blocks, boundary):
    dock.set_page(getattr(dock, "nip_page_index", 3))
    dock.cmb_nip_layer.setLayer(blocks)
    pump(0.05)
    index = dock.cmb_fonk_field.findText("fonk")
    check(index >= 0, f"the function column combo does not list 'fonk': "
                      f"{[dock.cmb_fonk_field.itemText(i) for i in range(dock.cmb_fonk_field.count())]}")
    dock.cmb_fonk_field.setCurrentIndex(index)
    dock.cmb_sinir_layer.setLayer(boundary)
    pump(0.05)
    dock.btn_run_nip.click()
    pump(0.2)


def check_nip_run_estimate_and_boundary_crs(rig_factory):
    """Without a boundary the DOP is labelled an estimate and gets no pass/fail colour;
    a boundary in EPSG:4326 over EPSG:5253 blocks is transformed, not used raw.

    1.1.6 coloured an invented-road-share DOP green/red as the legal verdict and
    unioned the boundary in its own CRS, so a 4326 boundary removed every block.
    """
    from qgis.core import QgsProject

    from qgis.PyQt.QtGui import QColor

    rig = rig_factory()
    problems = []
    try:
        dock = rig.dock
        blocks = _blocks_layer()
        _run_nip(dock, blocks, None)
        summary = getattr(dock, "_last_nip_summary", None)
        check(summary, f"the analysis did not finish: {rig.boxes.shown[-1:]}")
        badge = dock.lbl_dop_badge.text()
        last = dock.tbl_dop.item(dock.tbl_dop.rowCount() - 1, 0).text()
        report = dock.txt_nip_results.toPlainText()
        if "TAHMİNİ" not in badge:
            problems.append(f"no boundary, yet the badge reads {badge!r}")
        if "TAHMİNİ" not in last:
            problems.append(f"no boundary, yet the DOP row is {last!r}")
        if "TAHMİNİ DOP ORANI" not in report:
            problems.append("the dock report does not call the DOP an estimate")
        colours = {QColor(c).name() for c in re.findall(r"#[0-9a-fA-F]{6}", dock.lbl_dop_badge.styleSheet())}
        verdict = set()
        with contextlib.suppress(Exception):
            ui_theme = importlib.import_module(f"{PACKAGE}.ui_theme")
            tokens = ui_theme.hex_colors()
            verdict = {tokens[k] for k in ("ok", "bad", "ok_bg", "bad_bg")}
        if colours & verdict or re.search(r"#(15803d|b91c1c|dcfce7|fee2e2)", dock.lbl_dop_badge.styleSheet()):
            problems.append(f"the estimate badge has a pass/fail colour: {dock.lbl_dop_badge.styleSheet()[:90]!r}")
        for warning in summary.get("uyarilar", []):
            if str(warning)[:30] not in report:
                problems.append(f"warning not shown in the dock: {str(warning)[:60]!r}")
        if not summary.get("uyarilar"):
            problems.append("the calculator gave no warning for the missing boundary")
        rig.boxes.shown.clear()

        boundary = _boundary_4326(blocks)
        _run_nip(dock, blocks, boundary)
        summary = dock._last_nip_summary
        kept = (summary.get("sinir_filtre_ozet") or {}).get("islenen_ada_sayisi")
        badge = dock.lbl_dop_badge.text()
        last = dock.tbl_dop.item(dock.tbl_dop.rowCount() - 1, 0).text()
        report = dock.txt_nip_results.toPlainText()
        if kept != 3:
            problems.append(f"a 4326 boundary around 3 blocks kept {kept} of them")
        if "TAHMİNİ" in badge or "TAHMİNİ" in last:
            problems.append(f"with a boundary the DOP is still an estimate: {badge!r} / {last!r}")
        if "dönüştürüldü" not in report:
            problems.append("the report does not say the boundary was transformed")
        if summary.get("toplam_ust_nufus", 0) <= 0:
            problems.append("population 0 with a boundary in another CRS")
    finally:
        QgsProject.instance().clear()
        rig.close()
    fail_if(problems)
    return f"estimate labelled ({dock.lbl_dop_badge.text()!r} last); 4326 boundary kept {kept}/3 blocks"


# ---------------------------------------------------------------------------
# Dashboard escaping
# ---------------------------------------------------------------------------
def check_dashboard_escapes_layer_text(_rig_factory):
    """The dashboard HTML writes layer and field text escaped.

    1.1.6 put function names straight into innerHTML and Leaflet popups:
    a value ``<img src=x onerror=...>`` ran as markup in the user's browser.
    """
    from qgis.core import QgsFeature, QgsField, QgsFields, QgsGeometry, QgsRectangle

    calculator = importlib.import_module(f"{PACKAGE}.core.nip_calculator")
    builder = importlib.import_module(f"{PACKAGE}.core.nip_dashboard_builder")
    evil = "<img src=x onerror=alert(1)> Konut Alanı"
    fields = QgsFields()
    fields.append(QgsField("fonk"))
    feats = []
    for i, name in enumerate([evil, "Park ve Yeşil Alan", "Gelişme Konut Alanı (Orta)"]):
        f = QgsFeature(fields)
        f.setGeometry(QgsGeometry.fromRect(QgsRectangle(500000 + i * 200, 4200000, 500100 + i * 200, 4200100)))
        f.setAttribute("fonk", name)
        feats.append(f)
    items, summary = calculator.NipCalculatorEngine.calculate(feats, fields, "fonk", projeksiyon_nufus=50000)
    html_text = builder.build_nip_dashboard_html(summary, items)
    problems = []
    if "<img src=x" in html_text:
        problems.append("the raw <img …> from a field value is in the HTML")
    if "&lt;img src=x" not in html_text:
        problems.append("the escaped name is missing from the HTML")
    if "38.08, 27.73" in html_text:
        problems.append("the map falls back to Tire's coordinates")
    # No boundary: the DOP is an estimate, so neither the advice text nor the pill
    # may give a legal verdict (1.1.6 said "aşım" / "tam uyumludur" regardless).
    tahmini = bool(summary["dop_ozet"].get("tahmini"))
    if not tahmini:
        problems.append("the calculator did not flag a boundary-less DOP as an estimate")
    for verdict in ("Yasal DOP Uyumu", "DOP Oranı Aşımı", "tam uyumludur", "yasal üst sınır olan"):
        if verdict in html_text:
            problems.append(f"estimate report gives a legal verdict: {verdict!r}")
    if "Tahmini DOP" not in html_text or "status-pill neutral" not in html_text:
        problems.append("no estimate wording / neutral pill in the report")
    # The gauge: an estimate branch with no coloured bands or delta arrow, and the
    # 45 % line only as a labelled reference.
    gauge = re.search(r"const dopGauge = DATA\.dop_tahmini \? \{(.*?)\} : \{", html_text, re.S)
    if gauge is None:
        problems.append("the DOP gauge has no neutral estimate variant")
    else:
        body = gauge.group(1)
        if "delta" in body or "steps: []" not in body or "yasal tavan (referans)" not in body:
            problems.append("the estimate gauge still colours/arrows against 45 % or lacks the reference label")
    # With an estimate flag off, the legal verdict is still given.
    summary_legal = dict(summary, dop_ozet=dict(summary["dop_ozet"], tahmini=False))
    legal_html = builder.build_nip_dashboard_html(summary_legal, items)
    if not any(v in legal_html for v in ("Yasal DOP Uyumu", "DOP Oranı Aşımı", "Düşük DOP Kesintisi")):
        problems.append("a real-boundary report lost its legal verdict")
    fail_if(problems)
    return f"{len(html_text)} characters, field value present only escaped; estimate has no verdict"


CHECKS = (
    check_contrast_three_themes,
    check_width_1366x728,
    check_projection_fills_target,
    check_algorithm_links_open_dialogs,
    check_names_and_network_note,
    check_nip_run_estimate_and_boundary_crs,
    check_dashboard_escapes_layer_text,
)


def run_checks(checks=CHECKS) -> bool:
    print("=" * 70)
    print(f" {PACKAGE} - dock (offscreen, 1366x728)")
    print("=" * 70)
    started = time.monotonic()
    OFFLINE.install()
    sys.path.append(os.path.join(QgsApplication.prefixPath(), "python", "plugins"))
    from processing.core.Processing import Processing
    from qgis.analysis import QgsNativeAlgorithms

    QgsApplication.processingRegistry().addProvider(QgsNativeAlgorithms())
    Processing.initialize()
    projection_module()
    if STANDINS:
        print(f"  [INFO] contract stand-ins in use: {', '.join(STANDINS)}")
    passed = 0
    for function in checks:
        name = function.__name__[len("check_"):].replace("_", " ")
        try:
            detail = function(Rig)
            passed += 1
            print(f"  [PASS] {name} - {detail}", flush=True)
        except CheckFailed as exc:
            print(f"  [FAIL] {name} - {exc}", flush=True)
        except Exception as exc:
            print(f"  [FAIL] {name} - {type(exc).__name__}: {exc}", flush=True)
            traceback.print_exc(limit=5)
    late = [s for s in STANDINS if s.startswith("algorithms")]
    if late:
        print(f"  [INFO] stand-ins added during the run: {', '.join(late)}")
    if OFFLINE.refused:
        print(f"  [FAIL] public requests were attempted: {OFFLINE.refused[:3]}")
    print("-" * 70)
    ok = passed == len(checks) and not OFFLINE.refused
    print(f"  {passed}/{len(checks)} checks passed in {time.monotonic() - started:.0f} s - {'PASS' if ok else 'FAIL'}")
    return ok


def main():
    faulthandler.dump_traceback_later(int(os.environ.get("NIP_HANG_DUMP_S") or 900), exit=True)
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(errors="backslashreplace")
    app = QgsApplication([], True)
    app.initQgis()
    from qgis.PyQt.QtGui import QFont

    app.setFont(QFont("Segoe UI", 9))
    try:
        ok = run_checks()
    except Exception:
        traceback.print_exc()
        ok = False
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0 if ok else 1)


if __name__ == "__main__":
    main()
