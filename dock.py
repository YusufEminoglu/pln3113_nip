# -*- coding: utf-8 -*-
"""PLN3113 NİP ve Kentsel Analiz DockWidget Arayüzü.

PLN3113 - pln3113_nip
"""
from __future__ import annotations

import contextlib
import csv
import html
import inspect
import os
try:
    import processing
except ImportError:
    processing = None
from qgis.PyQt.QtCore import QSize, Qt, QTimer, QUrl, QVariant
from qgis.PyQt.QtGui import QColor, QDesktopServices, QFont, QIcon
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QSizePolicy,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget
)
from qgis.core import (
    NULL,
    QgsCategorizedSymbolRenderer,
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsFillSymbol,
    QgsGeometry,
    QgsGraduatedSymbolRenderer,
    QgsMapLayerProxyModel,
    QgsMarkerSymbol,
    QgsPointXY,
    QgsProject,
    QgsRasterLayer,
    QgsRendererCategory,
    QgsRendererRange,
    QgsSingleSymbolRenderer,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgsFieldComboBox, QgsMapLayerComboBox, QgsProjectionSelectionWidget

from .core.cleaner import GeometryCleanerEngine
from .core.field_estimator import FieldEstimatorEngine
from .core.nip_calculator import NipCalculatorEngine, build_distance_area, prepare_boundary_and_roads
from .core.nip_dashboard_builder import EXTERNAL_HOSTS, open_nip_dashboard, build_nip_dashboard_html
from .core.nip_workspace import (
    create_nip_workspace,
    load_nip_layers,
    SCHEMA_MPYY_117,
    SCHEMA_YEREL_NIP,
    create_nip_drawing_workspace,
    find_mpyy_layer,
    load_nip_drawing_layers,
)
from .core.mpyy_road import YolProfili
from .maptools.mpyy_road_tool import MpyyYolCizimAraci, YolProfilDialog
from .core.symbology_manager import (
    apply_mpyy_qml_style,
    style_detour_barrier,
    style_facility_adequacy_points,
    style_fca_demand_points,
    style_front_facade,
    style_isochrone_bands,
    style_nip_denetim,
    style_od_and_centrality,
    style_road_junctions,
    style_road_platform,
    style_road_polygons,
    style_scenario_diff_network,
    style_service_area,
    style_space_syntax,
    style_validity_error_points,
)
from .core.tire_constants import (
    get_default_dop_rule,
    get_default_employment_rule,
    get_default_trip_rule,
    norm_tr
)
from .ui_theme import (
    apply_native_editor_theme,
    chip_css,
    chunk_css,
    hex_colors,
    note_css,
    studio_stylesheet,
    text_css,
)

# Scoped Qt enums (fully compatible across Qt5 and Qt6)
_POINTING_HAND = Qt.CursorShape.PointingHandCursor
_CHECKED = Qt.CheckState.Checked
_UNCHECKED = Qt.CheckState.Unchecked
_ITEM_USER_CHECKABLE = Qt.ItemFlag.ItemIsUserCheckable
_ITEM_EDITABLE = Qt.ItemFlag.ItemIsEditable
_ALIGN_CENTER = Qt.AlignmentFlag.AlignCenter
_SCROLL_OFF = Qt.ScrollBarPolicy.ScrollBarAlwaysOff
_NO_FRAME = QFrame.Shape.NoFrame
_VIEW_MODE_ICON = QListView.ViewMode.IconMode
_MOVEMENT_STATIC = QListView.Movement.Static

PLUGIN_DIR = os.path.dirname(__file__)


DOCK_TITLE = "PLN3113 NİP Analiz Stüdyosu"

# Contract C1 methods (core/projection.py) with their Turkish labels.
PROJECTION_METHODS = (
    ("aritmetik", "Aritmetik (doğrusal artış)"),
    ("geometrik", "Geometrik (sabit oranlı artış)"),
    ("iller_bankasi", "İller Bankası yöntemi"),
    ("regresyon", "En küçük kareler (doğrusal regresyon)"),
    ("polinom", "Polinom (2. derece)"),
    ("lojistik", "Lojistik (doyum sınırlı)"),
)

# Processing tools reached from the projection page (contract C1 ids).
LINKED_ALGORITHMS = (
    ("nufus_projeksiyonu", "Projeksiyon Aracı (tablo çıktısı)", "Aynı projeksiyonu Processing aracıyla tüm yöntemler için tablo olarak üretir"),
    ("kohort_projeksiyonu", "Kohort-Bileşen Projeksiyonu", "Yaş grupları ve doğum/ölüm/göç ile 5 yıllık adımlarla projeksiyon"),
    ("mahalle_dagitimi", "Mahalle Dağıtımı", "Hedef nüfusu mahallelere oransal, bölge payı veya kapasiteye göre dağıtır"),
    ("kirilganlik_endeksi", "Kırılganlık Endeksi", "Pay/payda ve bileşik kırılganlık endeksini mahalle katmanına yazar"),
)


def _tr_int(value) -> str:
    """12345.6 -> '12.346' (Turkish thousands separator)."""
    return f"{int(round(float(value))):,}".replace(",", ".")


def _tr_num(value, digits: int = 2) -> str:
    """0.98765 -> '0,988' style decimals with a Turkish comma."""
    return f"{float(value):,.{digits}f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def _get_plugin_version() -> str:
    """Read version dynamically from metadata.txt."""
    meta_path = os.path.join(PLUGIN_DIR, "metadata.txt")
    if os.path.exists(meta_path):
        import configparser
        cp = configparser.ConfigParser()
        with contextlib.suppress(Exception):
            cp.read(meta_path, encoding="utf-8")
            return cp.get("general", "version", fallback="1.1.3")
    return "1.1.3"


class _TabsAdapter:
    """Compatibility adapter for test suites or scripts calling dock.tabs."""

    def __init__(self, dock):
        self._dock = dock

    def count(self) -> int:
        return self._dock.nav_list.count()

    def currentIndex(self) -> int:
        return self._dock.main_stack.currentIndex()

    def setCurrentIndex(self, index: int) -> None:
        self._dock.set_page(index)

    def tabText(self, index: int) -> str:
        item = self._dock.nav_list.item(index)
        return item.text() if item else ""


class TireNipDockWidget(QDockWidget):
    """PLN3113 NİP ve Kentsel Analiz Stüdyosu ana dock paneli.

    (Sınıf ve nesne adı eski sürümlerle uyum ve kayıtlı pencere düzeni için korunur.)
    """

    def __init__(self, iface, parent=None):
        super().__init__(DOCK_TITLE, parent)
        self.iface = iface
        self.setObjectName("TireNipDockWidget")
        self._c = hex_colors()
        self.setStyleSheet(studio_stylesheet())
        self._last_projection = None
        self._pending_handlers = []

        self._last_nip_summary = None
        self._last_nip_html = ""
        self.last_field_out_layer = None

        self._setup_ui()

    def set_page(self, index: int) -> None:
        """Switch current navigation page."""
        if 0 <= index < self.nav_list.count():
            self.nav_list.setCurrentRow(index)
            self.main_stack.setCurrentIndex(index)

    def _setup_ui(self):
        container = QWidget()
        container.setObjectName("nipRoot")
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # 1. HEADER BANNER
        header_frame = QFrame()
        header_frame.setObjectName("nipHeaderFrame")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(6, 4, 6, 4)
        header_layout.setSpacing(8)

        icon_label = QLabel()
        icon_label.setObjectName("nipAvatarLabel")
        avatar_path = os.path.join(PLUGIN_DIR, "icons", "avatar.png")
        if not os.path.exists(avatar_path):
            avatar_path = os.path.join(PLUGIN_DIR, "icons", "icon.png")
        if os.path.exists(avatar_path):
            icon_label.setPixmap(QIcon(avatar_path).pixmap(34, 34))
        icon_label.setToolTip("Stüdyo Koordinatörü & PlanX Studio")
        header_layout.addWidget(icon_label)

        title_box = QVBoxLayout()
        title_box.setSpacing(1)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        lbl_title = QLabel(DOCK_TITLE)
        lbl_title.setObjectName("nipHeroTitle")
        title_row.addWidget(lbl_title, 1)

        badge_version = QLabel(f"v{_get_plugin_version()}")
        badge_version.setObjectName("nipVersionBadge")
        title_row.addWidget(badge_version)
        title_box.addLayout(title_row)

        lbl_sub = QLabel("PLN3113 Şehir Planlama Projesi III")
        lbl_sub.setObjectName("nipHeaderSubtitle")
        title_box.addWidget(lbl_sub)
        header_layout.addLayout(title_box, 1)

        main_layout.addWidget(header_frame)

        # 2. BODY SPLIT: VERTICAL NAV RAIL + CONTENT STACK
        body_widget = QWidget()
        body_layout = QHBoxLayout(body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(4)

        # Vertical Navigation Rail (scrolls when the dock is short)
        self.nav_list = QListWidget()
        self.nav_list.setObjectName("nipNavRail")
        self.nav_list.setFixedWidth(64)
        self.nav_list.setViewMode(_VIEW_MODE_ICON)
        self.nav_list.setIconSize(QSize(22, 22))
        self.nav_list.setMovement(_MOVEMENT_STATIC)
        self.nav_list.setHorizontalScrollBarPolicy(_SCROLL_OFF)
        self.nav_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.nav_list.setSpacing(2)

        nav_items = [
            ("clean.png", "Geometri", "1. Geometri Onarımı ve Duplike Ayıklama", self._create_tab_cleaner),
            ("database.png", "Veritabanı", "2. NİP Çizim Veritabanı ve Şablonu (GeoPackage)", self._create_tab_database),
            ("road.png", "Yol/Kavşak", "3. Yol Platformu, Bordür ve Kavşak Geometrisi", self._create_tab_roads),
            ("report.png", "Nüfus", "4. Nüfus Projeksiyonu, Kohort, Mahalle Dağıtımı ve Kırılganlık", self._create_tab_projection),
            ("plan.png", "NİP & DOP", "5. NİP Nüfus, Donatı (Ek-2) ve DOP Analizi", self._create_tab_nip),
            ("field.png", "Saha/Yapı", "6. Saha ve Bina Fiili Nüfus Kestirimi", self._create_tab_field),
            ("network.png", "Network", "7. Ulaşım Ağı, Ön Cephe, Erişim Çapları ve OD Matrisi", self._create_tab_network),
            ("report.png", "Rehber", "8. NİP Metodolojisi, Standartlar ve El Kitabı", self._create_tab_guide),
        ]

        self.main_stack = QStackedWidget()
        self.main_stack.setObjectName("nipMainStack")
        for icon_file, text, tip, factory in nav_items:
            icon_p = os.path.join(PLUGIN_DIR, "icons", icon_file)
            item = QListWidgetItem(QIcon(icon_p) if os.path.exists(icon_p) else QIcon(), text)
            item.setToolTip(tip)
            item.setTextAlignment(_ALIGN_CENTER)
            item.setSizeHint(QSize(56, 46))
            self.nav_list.addItem(item)
            self.main_stack.addWidget(factory())
        self.projection_page_index = 3
        self.nip_page_index = 4

        body_layout.addWidget(self.nav_list)

        stack_scroll = QScrollArea()
        stack_scroll.setObjectName("nipStackScroll")
        stack_scroll.setWidgetResizable(True)
        stack_scroll.setFrameShape(_NO_FRAME)
        stack_scroll.setWidget(self.main_stack)
        body_layout.addWidget(stack_scroll, 1)

        main_layout.addWidget(body_widget, 1)

        self.nav_list.currentRowChanged.connect(self.main_stack.setCurrentIndex)
        self.main_stack.currentChanged.connect(self._fit_stack_to_page)
        self.nav_list.setCurrentRow(self.nip_page_index)  # Varsayılan: NİP & DOP
        self._fit_stack_to_page(self.main_stack.currentIndex())

        self.tabs = _TabsAdapter(self)

        self._fit_narrow(container)
        apply_native_editor_theme(container)
        self.setWidget(container)

    # Layer combo handlers run after the event: on QGIS 4 layerChanged arrives (with
    # None) before the combo's current layer is updated. Bound methods, so PyQt drops
    # the connections and timers together with the dock.
    def _deferred(self, handler) -> None:
        if handler not in self._pending_handlers:
            self._pending_handlers.append(handler)
        QTimer.singleShot(0, self._run_deferred)

    def _run_deferred(self) -> None:
        pending, self._pending_handlers = self._pending_handlers, []
        for handler in pending:
            handler()

    def _nip_layer_combo_changed(self, _layer=None) -> None:
        self._deferred(self._on_nip_layer_changed)

    def _sinir_layer_combo_changed(self, _layer=None) -> None:
        self._deferred(self._on_sinir_layer_changed)

    def _road_layer_combo_changed(self, _layer=None) -> None:
        self._deferred(self._on_road_layer_changed)

    def _fca_fac_combo_changed(self, _layer=None) -> None:
        self._deferred(self._refresh_fca_fac_fields)

    def _fca_dem_combo_changed(self, _layer=None) -> None:
        self._deferred(self._refresh_fca_dem_fields)

    def _refresh_fca_fac_fields(self) -> None:
        self._on_fca_fac_layer_changed(self.cmb_fca_facilities.currentLayer())

    def _refresh_fca_dem_fields(self) -> None:
        self._on_fca_dem_layer_changed(self.cmb_fca_demand.currentLayer())

    def _fit_stack_to_page(self, index: int) -> None:
        """Only the visible page sizes the stack: hidden pages neither widen the dock
        nor lengthen its scroll range."""
        for i in range(self.main_stack.count()):
            policy = QSizePolicy.Policy.Preferred if i == index else QSizePolicy.Policy.Ignored
            self.main_stack.widget(i).setSizePolicy(policy, policy)
        self.main_stack.updateGeometry()

    @staticmethod
    def _fit_narrow(root: QWidget) -> None:
        """Lets every page shrink to a ~340 px dock: labels wrap, combo boxes do not
        demand their longest item, form rows put long labels above the field."""
        for label in root.findChildren(QLabel):
            if label.pixmap() is None or label.pixmap().isNull():
                label.setWordWrap(True)
        for combo in root.findChildren(QComboBox):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(8)
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, combo.sizePolicy().verticalPolicy())
        for form in root.findChildren(QFormLayout):
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for tabs in root.findChildren(QTabWidget):
            tabs.setUsesScrollButtons(True)
            tabs.setElideMode(Qt.TextElideMode.ElideRight)
        for button in root.findChildren(QPushButton):
            if not button.toolTip():
                button.setToolTip(button.text().strip())

    def _open_theoretical_guide(self):
        """A'dan Z'ye teorik metodoloji el kitabını kullanıcının varsayılan tarayıcısında açar."""
        # Kılavuz ve teorik rehber geophilo.com'da tek sayfada yayımlanır.
        QDesktopServices.openUrl(QUrl("https://geophilo.com/pln3113_nip/#teorik"))

    def _create_tab_guide(self) -> QWidget:
        """Metodoloji, Resmî Mevzuat ve El Kitabı sayfası."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        card_intro = QFrame()
        card_intro.setObjectName("nipAccentCard")
        intro_lay = QVBoxLayout(card_intro)
        intro_lay.setContentsMargins(10, 8, 10, 8)
        intro_lay.setSpacing(6)

        t_lbl = QLabel("📚 PLN3113 NİP Metodoloji El Kitabı")
        t_lbl.setStyleSheet(text_css("accent", "10pt", bold=True))
        intro_lay.addWidget(t_lbl)

        d_lbl = QLabel(
            "Mekânsal Planlar Yapım Yönetmeliği (MPYY), 3194 sayılı İmar Kanunu Madde 18 (DOP) "
            "ve PLN3113 Stüdyo standartlarını içeren "
            "kapsamlı referans ve teorik hesap kütüphanesi."
        )
        d_lbl.setWordWrap(True)
        intro_lay.addWidget(d_lbl)

        btn_launch = QPushButton("📖 El Kitabını Tarayıcıda Aç")
        btn_launch.setObjectName("PrimaryButton")
        btn_launch.setCursor(_POINTING_HAND)
        btn_launch.clicked.connect(self._open_theoretical_guide)
        intro_lay.addWidget(btn_launch)
        layout.addWidget(card_intro)

        # Resmî Mevzuat ve Bakanlık Standartları Bağlantıları Kartı
        box_links = QGroupBox("Resmî Mevzuat")
        box_links.setToolTip("Resmî Mevzuat, Yönetmelik ve Bakanlık Standartları")
        links_lay = QVBoxLayout(box_links)
        links_lay.setSpacing(6)

        links_data = [
            (
                "📜 MPYY (Planlar Yapım Yön.)",
                "https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=19788&MevzuatTur=7&MevzuatTertip=5",
                "Asgari kişi başı kentsel donatı standartları (Ek-2 tablosu) ve plan yapım ilkeleri."
            ),
            (
                "🏢 Planlı Alanlar İmar Yön. (PAİY)",
                "https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=23722&MevzuatTur=7&MevzuatTertip=5",
                "Yapılaşma şartları, TAKS, KAKS, emsal hesabı, kat yükseklikleri ve bina çekme mesafesi kuralları."
            ),
            (
                "⚖️ İmar Kanunu Md. 18 (DOP)",
                "https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=3194&MevzuatTur=1&MevzuatTertip=5",
                "Arazi ve arsa düzenlemesi, Düzenleme Ortaklık Payı (%45 yasal tavan) ve kamuya terk edilecek donatılar."
            ),
            (
                "🎨 Plan Gösterimleri (MPGM)",
                "https://mpgm.csb.gov.tr/plan-gosterimleri-4926",
                "Çevre, Şehircilik ve İklim Değişikliği Bakanlığı resmî gösterim (lejant) standartları ve renk kodları."
            )
        ]

        for title, url, desc in links_data:
            btn_link = QPushButton(title)
            btn_link.setCursor(_POINTING_HAND)
            btn_link.setToolTip(f"{desc}\n\nResmî bağlantıyı tarayıcıda aç: {url}")
            btn_link.clicked.connect(lambda checked=False, target_url=url: QDesktopServices.openUrl(QUrl(target_url)))
            links_lay.addWidget(btn_link)

        layout.addWidget(box_links)

        # Quick reference cards
        box_ek2 = QGroupBox("1. Ek-2 Donatı Standartları")
        box_ek2.setToolTip("MPYY Ek-2 kentsel donatı standartları (kişi başı m²), eklentinin hesapta kullandığı değerler")
        ek2_lay = QVBoxLayout(box_ek2)
        ek2_info = QLabel(self._ek2_reference_html())
        ek2_info.setWordWrap(True)
        ek2_lay.addWidget(ek2_info)
        layout.addWidget(box_ek2)

        box_dop = QGroupBox("2. İmar Kanunu Md. 18 ve DOP")
        box_dop.setToolTip("3194 Sayılı İmar Kanunu Madde 18 ve DOP ilkeleri")
        dop_lay = QVBoxLayout(box_dop)
        dop_info = QLabel(
            "• <b>DOP Oranı:</b> (Toplam DOP İçi Donatı) / (Toplam Parsel Alanı)<br>"
            "• <b>Yasal Tavan:</b> 3194 sayılı Kanun uyarınca azami DOP oranı <b>%45.0</b>'dir.<br>"
            "• <b>Kamu - Özel Ayrımı:</b><br>"
            "  - <i>DOP İçi (Kamusal):</i> Yol, Meydan, Park, Temel Eğitim, İbadet, vb.<br>"
            "  - <i>DOP Dışı (Özel / Tahsis):</i> Konut, Ticaret, Sanayi, Özel Okul, Özel Hastane, Tarım vb."
        )
        dop_info.setWordWrap(True)
        dop_lay.addWidget(dop_info)
        layout.addWidget(box_dop)

        box_field = QGroupBox("3. Saha Nüfusu Kestirimi")
        box_field.setToolTip("Fiili yapı ve saha nüfusu kestirim metodu")
        field_lay = QVBoxLayout(box_field)
        field_info = QLabel(
            "• <b>Yöntem:</b> Nüfus = (Taban Alanı × Kat Adedi × Konut Payı) ÷ (Ortalama Konut m²) × (Ortalama Hanehalkı)<br>"
            "• Kat verisi olmayan binalar için mahalle/bölge ortalaması otomatik atanır.<br>"
            "• NİP brüt yoğunluk kapasitesi ile sahadaki fiili mevcut nüfus karşılaştırılarak kapasite doygunluk analizi üretilir."
        )
        field_info.setWordWrap(True)
        field_lay.addWidget(field_info)
        layout.addWidget(box_field)

        layout.addStretch()
        return page

    # -----------------------------------------------------------------
    # SEKME 1: GEOMETRİ & DUPLİKE TEMİZLEME (HİYERARŞİK KURGU)
    # -----------------------------------------------------------------
    def _create_tab_cleaner(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # Girdi Katmanı Seçimi
        box_input = QGroupBox("Girdi Poligon Katmanı")
        box_layout = QVBoxLayout(box_input)

        lbl = QLabel("Temizlenecek ve denetlenecek poligon katmanı:")
        box_layout.addWidget(lbl)

        self.cmb_clean_layer = QgsMapLayerComboBox()
        self.cmb_clean_layer.setFilters(QgsMapLayerProxyModel.Filter.PolygonLayer)
        box_layout.addWidget(self.cmb_clean_layer)
        layout.addWidget(box_input)

        # 1. Aşama: Topoloji ve Hata Denetimi (Check Validity)
        box_check = QGroupBox("1. Aşama: Hata Denetimi")
        box_check.setToolTip("Topoloji ve hata denetimi (Check Validity)")
        check_layout = QVBoxLayout(box_check)

        info_check = QLabel(
            "Orijinal katmana müdahale etmeden QGIS Core geometri geçerlilik algoritmasını çalıştırır; "
            "kendini kesen halkaları (self-intersection), hatalı düğüm noktalarını ve mükerrer poligonları tespit eder."
        )
        info_check.setWordWrap(True)
        info_check.setStyleSheet(text_css("subtle", "8pt"))
        check_layout.addWidget(info_check)

        self.btn_run_check_validity = QPushButton("🔍 Geçerliliği Denetle")
        self.btn_run_check_validity.setToolTip("Geometri geçerliliğini ve hataları denetle")
        self.btn_run_check_validity.setObjectName("CleanButton")
        self.btn_run_check_validity.setCursor(_POINTING_HAND)
        self.btn_run_check_validity.clicked.connect(self._run_geometry_check_validity)
        check_layout.addWidget(self.btn_run_check_validity)

        # 4 Mini Dashboard Kartı (Grid)
        grid_metrics = QGridLayout()
        grid_metrics.setSpacing(6)

        self.lbl_metric_total = QLabel("Toplam: -")
        self.lbl_metric_total.setStyleSheet(chip_css())
        self.lbl_metric_total.setAlignment(_ALIGN_CENTER)

        self.lbl_metric_invalid = QLabel("Geçersiz: -")
        self.lbl_metric_invalid.setStyleSheet(chip_css("bad"))
        self.lbl_metric_invalid.setAlignment(_ALIGN_CENTER)

        self.lbl_metric_duplicate = QLabel("Mükerrer: -")
        self.lbl_metric_duplicate.setStyleSheet(chip_css("warn"))
        self.lbl_metric_duplicate.setAlignment(_ALIGN_CENTER)

        self.lbl_metric_valid = QLabel("Geçerli: -")
        self.lbl_metric_valid.setStyleSheet(chip_css("ok"))
        self.lbl_metric_valid.setAlignment(_ALIGN_CENTER)

        grid_metrics.addWidget(self.lbl_metric_total, 0, 0)
        grid_metrics.addWidget(self.lbl_metric_invalid, 0, 1)
        grid_metrics.addWidget(self.lbl_metric_duplicate, 1, 0)
        grid_metrics.addWidget(self.lbl_metric_valid, 1, 1)
        check_layout.addLayout(grid_metrics)

        # Hata Listesi Tablosu
        self.tbl_clean_errors = QTableWidget()
        self.tbl_clean_errors.setColumnCount(4)
        self.tbl_clean_errors.setHorizontalHeaderLabels(["FID", "Hata Türü", "Detay / Açıklama", "Konum (X, Y)"])
        self.tbl_clean_errors.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_clean_errors.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_clean_errors.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tbl_clean_errors.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_clean_errors.setMinimumHeight(130)
        self.tbl_clean_errors.setMaximumHeight(180)
        self.tbl_clean_errors.cellClicked.connect(self._on_clean_error_row_clicked)
        check_layout.addWidget(self.tbl_clean_errors)

        lbl_zoom_hint = QLabel("💡 <i>Bir hata satırına tıklayınca harita o geometriye odaklanır.</i>")
        lbl_zoom_hint.setStyleSheet(text_css("subtle", "8pt"))
        check_layout.addWidget(lbl_zoom_hint)

        self.btn_add_error_points = QPushButton("📍 Hata Noktalarını Haritaya Ekle")
        self.btn_add_error_points.setCursor(_POINTING_HAND)
        self.btn_add_error_points.setEnabled(False)
        self.btn_add_error_points.clicked.connect(self._add_error_points_to_map)
        check_layout.addWidget(self.btn_add_error_points)

        layout.addWidget(box_check)

        # 2. Aşama: Akıllı Onarım ve Tekilleştirme (Fix & Deduplicate)
        box_fix = QGroupBox("2. Aşama: Onarım ve Tekilleştirme")
        box_fix.setToolTip("Akıllı onarım ve tekilleştirme (Fix & Deduplicate)")
        fix_layout = QVBoxLayout(box_fix)

        info_fix = QLabel(
            "Bozuk geometrileri <code>makeValid()</code> ve sıfır-tampon motoruyla onarır, "
            "aynı alanı kaplayan mükerrer poligonları tekilleştirir. Temiz katman üretilerek "
            "2. Sekme (NİP Analizi) için otomatik atanır."
        )
        info_fix.setWordWrap(True)
        info_fix.setStyleSheet(text_css("subtle", "8pt"))
        fix_layout.addWidget(info_fix)

        self.btn_run_clean = QPushButton("⚡ Onar ve Duplikeleri Ayıkla")
        self.btn_run_clean.setToolTip("Geometriyi otomatik onar ve mükerrer (duplike) poligonları ayıkla")
        self.btn_run_clean.setObjectName("PrimaryButton")
        self.btn_run_clean.setCursor(_POINTING_HAND)
        clean_icon_path = os.path.join(PLUGIN_DIR, "icons", "clean.png")
        if os.path.exists(clean_icon_path):
            self.btn_run_clean.setIcon(QIcon(clean_icon_path))
        self.btn_run_clean.clicked.connect(self._run_geometry_clean)
        fix_layout.addWidget(self.btn_run_clean)

        self.clean_progress = QProgressBar()
        self.clean_progress.setVisible(False)
        fix_layout.addWidget(self.clean_progress)

        self.txt_clean_log = QTextEdit()
        self.txt_clean_log.setReadOnly(True)
        self.txt_clean_log.setMaximumHeight(130)
        self.txt_clean_log.setPlaceholderText("Onarım ve temizleme işlem sonuçları burada özetlenecektir...")
        fix_layout.addWidget(self.txt_clean_log)

        layout.addWidget(box_fix)
        layout.addStretch()
        return tab

    def _run_geometry_check_validity(self):
        """1. Aşama: Katmanda geometri geçerlilik denetimi ve duplike taraması yapar."""
        layer = self.cmb_clean_layer.currentLayer()
        if not layer or not isinstance(layer, QgsVectorLayer):
            QMessageBox.warning(self, "Uyarı", "Lütfen denetlenecek geçerli bir poligon katmanı seçin!")
            return

        self.btn_run_check_validity.setEnabled(False)
        self.tbl_clean_errors.setRowCount(0)
        try:
            stats = GeometryCleanerEngine.check_validity(layer)
            self._last_validity_errors = stats.get("hatalar", [])

            self.lbl_metric_total.setText(f"Toplam: {stats['toplam_girdi']:,}")
            self.lbl_metric_invalid.setText(f"Geçersiz: {stats['gecersiz_adet']:,}")
            self.lbl_metric_duplicate.setText(f"Mükerrer: {stats['duplike_adet']:,}")
            self.lbl_metric_valid.setText(f"Geçerli: {stats['gecerli_adet']:,}")

            hatalar = stats.get("hatalar", [])
            self.tbl_clean_errors.setRowCount(len(hatalar))

            for r_idx, h in enumerate(hatalar):
                item_fid = QTableWidgetItem(str(h["fid"]))
                item_fid.setFlags(item_fid.flags() & ~_ITEM_EDITABLE)

                item_tur = QTableWidgetItem(h["hata_turu"])
                item_tur.setFlags(item_tur.flags() & ~_ITEM_EDITABLE)
                if "Geçersiz" in h["hata_turu"]:
                    item_tur.setForeground(QColor(self._c["bad"]))
                elif "Mükerrer" in h["hata_turu"]:
                    item_tur.setForeground(QColor(self._c["warn"]))

                item_detay = QTableWidgetItem(h["detay"])
                item_detay.setFlags(item_detay.flags() & ~_ITEM_EDITABLE)

                coord_txt = f"{h['x']:.2f}, {h['y']:.2f}" if (h.get("x") is not None and h.get("y") is not None) else "-"
                item_coord = QTableWidgetItem(coord_txt)
                item_coord.setFlags(item_coord.flags() & ~_ITEM_EDITABLE)

                self.tbl_clean_errors.setItem(r_idx, 0, item_fid)
                self.tbl_clean_errors.setItem(r_idx, 1, item_tur)
                self.tbl_clean_errors.setItem(r_idx, 2, item_detay)
                self.tbl_clean_errors.setItem(r_idx, 3, item_coord)

            has_errors = len(hatalar) > 0
            self.btn_add_error_points.setEnabled(has_errors)

            if has_errors:
                QMessageBox.warning(
                    self, "Geometri Denetim Raporu",
                    f"'{layer.name()}' katmanında ({stats['toplam_girdi']:,} obje):\n\n"
                    f"• {stats['gecersiz_adet']:,} adet geçersiz geometri tespit edildi.\n"
                    f"• {stats['duplike_adet']:,} adet mükerrer (duplike) poligon tespit edildi.\n\n"
                    f"Hatalar aşağıdaki tabloda listelendi. Detayları harita üzerinde incelemek için "
                    f"tablodaki satırlara tıklayabilir veya 'Hata Noktalarını Haritaya Ekle' butonunu kullanabilirsiniz."
                )
            else:
                QMessageBox.information(
                    self, "Geometri Kusursuz",
                    f"Tebrikler! '{layer.name()}' katmanındaki tüm poligonlar ({stats['toplam_girdi']:,} obje) "
                    f"topolojik olarak geçerlidir ve hiçbir mükerrer geometri bulunmamaktadır."
                )
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Geometri denetimi sırasında hata oluştu:\n{str(e)}")
        finally:
            self.btn_run_check_validity.setEnabled(True)

    def _on_clean_error_row_clicked(self, row: int, col: int):
        """Hata satırına tıklandığında harita tuvalinde ilgili geometriye/noktaya zoom yapar."""
        fid_item = self.tbl_clean_errors.item(row, 0)
        layer = self.cmb_clean_layer.currentLayer()
        if not fid_item or not layer or not isinstance(layer, QgsVectorLayer):
            return
        with contextlib.suppress(Exception):
            fid = int(fid_item.text())
            feat = layer.getFeature(fid)
            if feat and feat.geometry() and not feat.geometry().isEmpty():
                box = feat.geometry().boundingBox()
                box.grow(box.width() * 0.35 if box.width() > 0 else 25.0)
                if self.iface:
                    self.iface.mapCanvas().setExtent(box)
                    self.iface.mapCanvas().refresh()


    def _add_error_points_to_map(self):
        """Tespit edilen hata noktalarını haritaya kırmızı ikaz sembolojisiyle bellek katmanı olarak ekler."""
        if not hasattr(self, "_last_validity_errors") or not self._last_validity_errors:
            QMessageBox.information(self, "Bilgi", "Haritaya eklenecek bir geometri hatası bulunamadı.")
            return

        layer = self.cmb_clean_layer.currentLayer()
        crs_auth = layer.crs().authid() if layer else "EPSG:5253"
        err_layer = QgsVectorLayer(f"Point?crs={crs_auth}", f"{layer.name() if layer else 'Plan'}_GEOMETRI_HATALARI", "memory")
        prov = err_layer.dataProvider()
        prov.addAttributes([
            QgsField("hata_no", QVariant.Int),
            QgsField("poligon_fid", QVariant.Int),
            QgsField("hata_turu", QVariant.String),
            QgsField("detay", QVariant.String),
        ])
        err_layer.updateFields()

        feats = []
        for idx, h in enumerate(self._last_validity_errors):
            x = h.get("x")
            y = h.get("y")
            if x is not None and y is not None:
                pt_feat = QgsFeature(err_layer.fields())
                pt_feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
                pt_feat.setAttribute("hata_no", idx + 1)
                pt_feat.setAttribute("poligon_fid", h["fid"])
                pt_feat.setAttribute("hata_turu", h["hata_turu"])
                pt_feat.setAttribute("detay", h["detay"])
                feats.append(pt_feat)

        if not feats:
            QMessageBox.warning(self, "Uyarı", "Hatalar arasında koordinatı belirlenebilen nokta bulunamadı.")
            return

        prov.addFeatures(feats)
        err_layer.updateExtents()

        symbol = QgsMarkerSymbol.createSimple({
            "name": "circle",
            "color": "#dc2626",
            "outline_color": "#ffffff",
            "outline_width": "0.8",
            "size": "4.5"
        })
        err_layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        QgsProject.instance().addMapLayer(err_layer)

        if self.iface:
            self.iface.mapCanvas().setExtent(err_layer.extent())
            self.iface.mapCanvas().refresh()

        QMessageBox.information(
            self, "Hata Noktaları Eklendi",
            f"Toplam {len(feats)} adet geometri hata noktası haritaya '<b>{err_layer.name()}</b>' katmanı olarak eklendi."
        )

    def _run_geometry_clean(self):
        layer = self.cmb_clean_layer.currentLayer()
        if not layer or not isinstance(layer, QgsVectorLayer):
            QMessageBox.warning(self, "Uyarı", "Lütfen geçerli bir poligon katmanı seçin!")
            return

        orig_layer_name = layer.name()

        self.btn_run_clean.setEnabled(False)
        self.clean_progress.setVisible(True)
        self.clean_progress.setRange(0, 0)
        self.txt_clean_log.clear()
        self.txt_clean_log.append(f"<b>Katman taranıyor:</b> {orig_layer_name} ({layer.featureCount():,} obje)...")

        try:
            cleaned_feats, stats = GeometryCleanerEngine.clean_layer(layer)

            # Yeni Memory Katmanı oluştur
            uri = f"MultiPolygon?crs={layer.crs().authid()}"
            out_name = f"{orig_layer_name}_TEMIZLENMIS"
            out_layer = QgsVectorLayer(uri, out_name, "memory")
            out_prov = out_layer.dataProvider()
            out_prov.addAttributes(layer.fields())
            out_layer.updateFields()
            out_prov.addFeatures(cleaned_feats)
            out_layer.updateExtents()

            QgsProject.instance().addMapLayer(out_layer)

            # cmb_clean_layer'ın yeni katmana otomatik kaymasını önle:
            # Orijinal girdi katmanını listede seçili tutuyoruz
            self.cmb_clean_layer.setLayer(layer)

            # 2. Sekmedeki NİP analiz katmanını ise otomatik olarak yeni temiz katmana geçir
            self.cmb_nip_layer.setLayer(out_layer)

            dup_oran = stats.get('duplike_orani', round((stats['duplike_elenen']/max(1, stats['toplam_girdi']))*100, 1))

            log_text = (
                f"✅ <b>Temizleme Başarıyla Tamamlandı!</b><br>"
                f"• Girdi Katmanı: <b>{orig_layer_name}</b><br>"
                f"• Toplam Taranan Obje: <b>{stats['toplam_girdi']:,}</b><br>"
                f"• Ayıklanan Mükerrer (Duplike) Poligon: <b style='color:{self._c["bad"]};'>{stats['duplike_elenen']:,}</b> (%{dup_oran})<br>"
                f"• Onarılan Geçersiz Geometri: <b>{stats['gecersiz_onarilan']:,}</b><br>"
                f"• Temiz Çıktı Obje Sayısı: <b style='color:{self._c["ok"]};'>{stats['temiz_cikan']:,}</b><br>"
                f"Yeni katman <i>'{out_name}'</i> haritaya eklendi ve 2. Sekme (NİP Analiz) için seçildi."
            )
            self.txt_clean_log.setHtml(log_text)

            if stats['duplike_elenen'] > 0 or stats['gecersiz_onarilan'] > 0:
                QMessageBox.information(
                    self, "Geometri Temizleme Başarılı",
                    f"Girdi Katmanı: {orig_layer_name} ({stats['toplam_girdi']:,} obje)\n\n"
                    f"✅ {stats['duplike_elenen']:,} adet mükerrer (duplike) poligon ayıklandı (%{dup_oran}).\n"
                    f"✅ {stats['gecersiz_onarilan']:,} adet geçersiz geometri onarıldı.\n\n"
                    f"Temiz Çıktı: {stats['temiz_cikan']:,} adet tekil ada içeren '{out_name}' katmanı oluşturuldu."
                )
            else:
                extra = ""
                if "_TEMIZLENMIS" in orig_layer_name:
                    extra = "\n\n(Not: Seçili katman zaten daha önce temizlenmiş bir katmandır. Orijinal ham katmanı temizlemek için lütfen açılır kutudan ham katmanı seçiniz.)"
                QMessageBox.information(
                    self, "Mükerrer Bulunamadı",
                    f"'{orig_layer_name}' katmanında ({stats['toplam_girdi']:,} obje) herhangi bir mükerrer poligon veya geçersiz geometriye rastlanmadı.{extra}"
                )

        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Temizleme sırasında hata: {str(e)}")
            self.txt_clean_log.append(f"<span style='color:{self._c['bad']};'>Hata: {html.escape(str(e))}</span>")
        finally:
            self.btn_run_clean.setEnabled(True)
            self.clean_progress.setVisible(False)

    # -----------------------------------------------------------------
    # SEKME 2: NİP ÇİZİM VERİTABANI VE ŞABLONU (GEOPACKAGE)
    # -----------------------------------------------------------------
    def _create_tab_database(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # Kart: Bilgilendirme
        card_info = QFrame()
        card_info.setObjectName("nipAccentCard")
        info_lay = QVBoxLayout(card_info)
        info_lay.setContentsMargins(10, 8, 10, 8)
        info_lay.setSpacing(4)

        t_lbl = QLabel("🗄️ 1/5000 NİP Çizim Veritabanı ve Şablonu")
        t_lbl.setStyleSheet(text_css("accent", "10pt", bold=True))
        info_lay.addWidget(t_lbl)

        d_lbl = QLabel(
            "Mekânsal Planlar Yapım Yönetmeliği (MPYY) standartlarına birebir uygun, "
            "resmi çizgi/alan lejant stilleri, hiyerarşik öznitelik formları, açılır menü (Value Map) "
            "kodlamaları ve 1-N ilişkileri (Relations) içeren hazır GeoPackage (.gpkg) çalışma alanı üretir."
        )
        d_lbl.setWordWrap(True)
        d_lbl.setStyleSheet(text_css("subtle", "8.5pt"))
        info_lay.addWidget(d_lbl)
        layout.addWidget(card_info)

        # Hedef Veritabanı Konumu ve CRS
        box_db = QGroupBox("Şema ve Dosya Konumu")
        form_db = QFormLayout(box_db)
        form_db.setSpacing(8)

        # Şema Seçici (MPYY 1.1.7 vs Yerel NİP)
        self.cmb_db_schema = QComboBox()
        self.cmb_db_schema.addItem("🏛️ Resmî MPYY 1.1.7 XSD (87 katman)", SCHEMA_MPYY_117)
        self.cmb_db_schema.addItem("📐 PLN3113 Yerel NİP (MpyyNipDB 1/5000)", SCHEMA_YEREL_NIP)
        self.cmb_db_schema.setToolTip("Resmî MPYY 1.1.7 XSD şeması (Bakanlık e-Plan & Ek-1e, 87 katman) veya "
                                      "PLN3113 yerel NİP şablonu (5 katman + tablo + QML)")
        self.cmb_db_schema.currentIndexChanged.connect(self._on_db_schema_changed)
        form_db.addRow("Plan Şeması / Standart:", self.cmb_db_schema)

        # GPKG Dosya Yolu Seçici
        path_box = QHBoxLayout()
        self.txt_db_path = QLineEdit()
        self.txt_db_path.setPlaceholderText("Örn: C:/Projeler/1_5000_Nazim_Imar_Plani.gpkg")
        default_dir = QgsProject.instance().homePath() or os.path.expanduser("~/Documents")
        default_file = os.path.join(default_dir, "1_5000_Nazim_Imar_Plani.gpkg").replace("\\", "/")
        self.txt_db_path.setText(default_file)
        self.btn_db_browse = QPushButton("...")
        self.btn_db_browse.setFixedWidth(32)
        self.btn_db_browse.setCursor(_POINTING_HAND)
        self.btn_db_browse.clicked.connect(self._browse_db_path)
        path_box.addWidget(self.txt_db_path)
        path_box.addWidget(self.btn_db_browse)
        form_db.addRow("Hedef GeoPackage (.gpkg):", path_box)

        # CRS Seçici
        self.crs_db_selector = QgsProjectionSelectionWidget()
        self.crs_db_selector.setCrs(QgsCoordinateReferenceSystem("EPSG:5253"))
        form_db.addRow("Projeksiyon / CRS:", self.crs_db_selector)

        layout.addWidget(box_db)

        # Seçenekler
        box_opts = QGroupBox("Seçenekler")
        opts_lay = QVBoxLayout(box_opts)
        opts_lay.setSpacing(6)

        self.chk_db_load_layers = QCheckBox("Katmanları projeye ekle")
        self.chk_db_load_layers.setToolTip("Üretilen katmanları mevcut QGIS projesine otomatik ekle")
        self.chk_db_load_layers.setChecked(True)
        opts_lay.addWidget(self.chk_db_load_layers)

        self.chk_db_apply_styles = QCheckBox("Resmî lejant stillerini bağla")
        self.chk_db_apply_styles.setToolTip("MPYY resmî lejant stillerini (.qml / SLD) otomatik bağla")
        self.chk_db_apply_styles.setChecked(True)
        opts_lay.addWidget(self.chk_db_apply_styles)

        self.chk_db_setup_forms = QCheckBox("Öznitelik formlarını kur")
        self.chk_db_setup_forms.setToolTip("Hiyerarşik öznitelik formlarını ve açılır menü (Value Map) kurallarını kur")
        self.chk_db_setup_forms.setChecked(True)
        opts_lay.addWidget(self.chk_db_setup_forms)

        self.chk_db_setup_relations = QCheckBox("Fonksiyon ilişkilerini kur")
        self.chk_db_setup_relations.setToolTip("Çoklu fonksiyon ilişkilerini (Relations: alanlar-5000 <-> fonksiyonlar) aktifleştir")
        self.chk_db_setup_relations.setChecked(True)
        opts_lay.addWidget(self.chk_db_setup_relations)

        layout.addWidget(box_opts)

        # Buton
        self.btn_create_db = QPushButton("🚀 Veritabanını Oluştur")
        self.btn_create_db.setToolTip("MPYY 1.1.7 NİP çizim veritabanını oluştur ve katmanları yükle")
        self.btn_create_db.setObjectName("PrimaryButton")
        self.btn_create_db.setCursor(_POINTING_HAND)
        self.btn_create_db.clicked.connect(self._on_create_database)
        layout.addWidget(self.btn_create_db)

        self.btn_nip_audit = QPushButton("🔍 NİP Denetimi")
        self.btn_nip_audit.setToolTip(
            "Yüklü MPYY 1.1.7 NİP veritabanını baştan sona denetler; bulguları haritaya ekler. "
            "Her katmanın öznitelik tablosundaki ⚠ Kontrol sütunu da nesne başına sorunu gösterir.")
        self.btn_nip_audit.setObjectName("SecondaryButton")
        self.btn_nip_audit.setCursor(_POINTING_HAND)
        self.btn_nip_audit.clicked.connect(self._on_run_nip_audit)
        layout.addWidget(self.btn_nip_audit)

        # Bilgilendirme Kartı: Üretilecek Katman Şeması
        self.box_schema = QGroupBox("Oluşturulacak Katmanlar")
        schema_lay = QVBoxLayout(self.box_schema)
        self.schema_html = QLabel(
            "<div style='font-size:8.5pt; line-height:1.45;'>"
            "• <b>Alanlar (58 Poligon Katmanı)</b>: GelismeKonut, MevcutKonut, DonusumKonutAlanlari, KentselCalisma, "
            "AcikYesilAlan, EgitimTesisAlani, SaglikTesisAlani, PlanSiniri, YolDuzenlemeAlanlari, AfetHizmetAlani, AraziKoruma vb.<br/>"
            "• <b>Çizgiler (23 Çizgi Katmanı)</b>: KarayoluGuzergahi, Demiryolu, AdaKenari, ManiaSiniri, SuUlasimBaglantisi vb.<br/>"
            "• <b>Noktalar (6 Nokta Katmanı)</b>: Heliport, OzelKanunlarlaBelirlenenAlan, Merkez vb.<br/>"
            "• <b>Ek-1e Sembol Kataloğu (mpyy_detay_katalogu)</b>: 199 adet mevzuat sembolü ve detay sınıflandırması.<br/>"
            "• <b>Resmî e-Plan SLD Stilleri & Formlar</b>: Her katman için Bakanlık e-Plan renkleri, taramaları ve ValueMap açılır menüleri hazır."
            "</div>"
        )
        self.schema_html.setWordWrap(True)
        schema_lay.addWidget(self.schema_html)
        layout.addWidget(self.box_schema)

        layout.addStretch()
        return tab

    def _on_db_schema_changed(self, index=0):
        schema_type = self.cmb_db_schema.currentData()
        if schema_type == SCHEMA_YEREL_NIP:
            self.btn_create_db.setText("🚀 Veritabanını Oluştur")
            self.btn_create_db.setToolTip("PLN3113 yerel NİP veritabanını oluştur ve katmanları yükle")
            self.box_schema.setTitle("Oluşturulacak Katmanlar")
            self.box_schema.setToolTip("PLN3113 Yerel NİP (MpyyNipDB) katmanları")
            self.schema_html.setText(
                "<div style='font-size:8.5pt; line-height:1.45;'>"
                "• <b>alanlar-5000 (Poligon)</b>: 1/5000 NİP arazi kullanım fonksiyon lekeleri ve alan kullanım kararları.<br/>"
                "• <b>cizgiler_5000_v2 (Çizgi)</b>: 1/5000 NİP yol aksları, plan onama sınırı, koruma kuşakları ve hatlar.<br/>"
                "• <b>fonksiyonlar-5000_tablo (Öznitelik Tablosu)</b>: 1-N ilişkili çoklu fonksiyon, lejant kodu ve alt detay tanımları.<br/>"
                "• <b>5000_revizyon_planonama_snr & yollar_ve_Adalar_icin_cizgiler</b>: Yardımcı sınır ve yol/ada aks katmanları.<br/>"
                "• <b>layer_styles & Hazır QML Lejantı</b>: GeoPackage içinde gömülü resmî renk paleti ve QML form/ilişki tanımları."
                "</div>"
            )
            self.chk_db_setup_relations.setEnabled(True)
            self.chk_db_setup_relations.setChecked(True)
        else:
            self.btn_create_db.setText("🚀 Veritabanını Oluştur")
            self.btn_create_db.setToolTip("MPYY 1.1.7 NİP çizim veritabanını oluştur ve katmanları yükle")
            self.box_schema.setTitle("Oluşturulacak Katmanlar")
            self.box_schema.setToolTip("Resmî MPYY 1.1.7 NİP katmanları ve hiyerarşisi")
            self.schema_html.setText(
                "<div style='font-size:8.5pt; line-height:1.45;'>"
                "• <b>Alanlar (58 Poligon Katmanı)</b>: GelismeKonut, MevcutKonut, DonusumKonutAlanlari, KentselCalisma, "
                "AcikYesilAlan, EgitimTesisAlani, SaglikTesisAlani, PlanSiniri, YolDuzenlemeAlanlari, AfetHizmetAlani, AraziKoruma vb.<br/>"
                "• <b>Çizgiler (23 Çizgi Katmanı)</b>: KarayoluGuzergahi, Demiryolu, AdaKenari, ManiaSiniri, SuUlasimBaglantisi vb.<br/>"
                "• <b>Noktalar (6 Nokta Katmanı)</b>: Heliport, OzelKanunlarlaBelirlenenAlan, Merkez vb.<br/>"
                "• <b>Ek-1e Sembol Kataloğu (mpyy_detay_katalogu)</b>: 199 adet mevzuat sembolü ve detay sınıflandırması.<br/>"
                "• <b>Resmî e-Plan SLD Stilleri & Formlar</b>: Her katman için Bakanlık e-Plan renkleri, taramaları ve ValueMap açılır menüleri hazır."
                "</div>"
            )

    def _browse_db_path(self):
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "1/5000 NİP GeoPackage Dosyasını Seçin veya Oluşturun",
            self.txt_db_path.text() or "",
            "GeoPackage (*.gpkg)"
        )
        if filename:
            if not filename.lower().endswith(".gpkg"):
                filename += ".gpkg"
            self.txt_db_path.setText(filename)

    def _on_create_database(self):
        gpkg_path = self.txt_db_path.text().strip()
        if not gpkg_path:
            QMessageBox.warning(self, "Eksik Bilgi", "Lütfen geçerli bir GeoPackage dosya yolu belirtin.")
            return

        crs = self.crs_db_selector.crs()
        crs_authid = crs.authid() if crs.isValid() else "EPSG:5253"
        schema_type = self.cmb_db_schema.currentData() or SCHEMA_MPYY_117

        load_layers = self.chk_db_load_layers.isChecked()
        apply_styles = self.chk_db_apply_styles.isChecked()
        setup_forms = self.chk_db_setup_forms.isChecked()
        setup_relations = self.chk_db_setup_relations.isChecked()

        try:
            self.btn_create_db.setEnabled(False)
            create_nip_workspace(gpkg_path, crs=crs_authid, schema_type=schema_type)

            loaded_names = []
            if load_layers:
                layers_dict = load_nip_layers(
                    gpkg_path,
                    project=QgsProject.instance(),
                    schema_type=schema_type,
                    apply_styles=apply_styles,
                    setup_forms=setup_forms,
                    setup_relations=setup_relations
                )
                loaded_names = list(layers_dict.keys())

            schema_name = "Resmî MPYY 1.1.7 XSD" if schema_type == SCHEMA_MPYY_117 else "PLN3113 Yerel NİP (MpyyNipDB)"
            msg = (
                f"1/5000 NİP Çizim Veritabanı ({schema_name}) başarıyla oluşturuldu!\n\n"
                f"📁 Dosya: {gpkg_path}\n"
                f"🌐 Projeksiyon: {crs_authid}\n"
            )
            if loaded_names:
                msg += f"✅ Projeye Yüklenen Katmanlar ({len(loaded_names)} adet):\n- " + "\n- ".join(loaded_names[:15])
                if len(loaded_names) > 15:
                    msg += f"\n... ve {len(loaded_names) - 15} katman daha."

            QMessageBox.information(self, "Veritabanı Hazır", msg)

        except Exception as e:
            QMessageBox.critical(self, "Hata", f"NİP Veritabanı oluşturulurken hata meydana geldi:\n{str(e)}")
        finally:
            self.btn_create_db.setEnabled(True)

    # -----------------------------------------------------------------
    # SEKME 3: YOL PLATFORMU, BORDÜR VE KAVŞAK GEOMETRİSİ
    # -----------------------------------------------------------------
    def _create_tab_roads(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        card_info = QFrame()
        card_info.setObjectName("nipAccentCard")
        info_lay = QVBoxLayout(card_info)
        info_lay.setContentsMargins(10, 8, 10, 8)
        info_lay.setSpacing(4)

        t_lbl = QLabel("🛣️ Yol Platformu, Bordür ve Kavşak")
        t_lbl.setStyleSheet(text_css("accent", "10pt", bold=True))
        info_lay.addWidget(t_lbl)

        d_lbl = QLabel(
            "Ulaşım aksı orta çizgilerinden yasal yol genişliklerine göre platform sınırları, "
            "orta refüj ve kaldırım/bordür hatları üretir; kavşak yaklaşımlarını kırpar ve "
            "dış sınırları otomatik poligonlaştırarak NİP imar adalarıyla eşleştirir."
        )
        d_lbl.setWordWrap(True)
        d_lbl.setStyleSheet(text_css("subtle", "8.5pt"))
        info_lay.addWidget(d_lbl)
        layout.addWidget(card_info)

        # MPYY 1.1.7 NİP: orta akstan Yolorta + DigerYolNesneleri + AdaKenari
        box_mpyy = QGroupBox("MPYY 1.1.7 NİP Yolu")
        box_mpyy.setToolTip("Ek-1e: NİP yolları Yolorta + AdaKenari + DigerYolNesneleri olarak birlikte çizilir")
        lay_mpyy = QVBoxLayout(box_mpyy)
        lay_mpyy.setSpacing(6)
        lbl_mpyy = QLabel(
            "Yol profilini (şerit, refüj, kaldırım) girin, orta aksı haritada çizin. Yolorta, "
            "taşıt yolu/refüj/kaldırım poligonları ve ada kenarları birlikte yazılır; kesişen "
            "yollarda kavşak açılır.")
        lbl_mpyy.setWordWrap(True)
        lbl_mpyy.setStyleSheet(text_css("subtle", "8.5pt"))
        lay_mpyy.addWidget(lbl_mpyy)
        self.btn_mpyy_road = QPushButton("🛣 MPYY Yol Çiz")
        self.btn_mpyy_road.setToolTip("Sol tık: nokta, Backspace: geri al, Sağ tık/Enter: bitir, Esc: iptal")
        self.btn_mpyy_road.setObjectName("PrimaryButton")
        self.btn_mpyy_road.setCursor(_POINTING_HAND)
        self.btn_mpyy_road.clicked.connect(self._on_mpyy_road_draw)
        lay_mpyy.addWidget(self.btn_mpyy_road)
        self.btn_mpyy_platform = QPushButton("🧱 Yolorta'dan Platform")
        self.btn_mpyy_platform.setToolTip("YolGenisligi değerinden platformu olmayan akslar için platform üretir")
        self.btn_mpyy_platform.setObjectName("SecondaryButton")
        self.btn_mpyy_platform.setCursor(_POINTING_HAND)
        self.btn_mpyy_platform.clicked.connect(self._on_mpyy_platform_batch)
        lay_mpyy.addWidget(self.btn_mpyy_platform)
        layout.addWidget(box_mpyy)

        # 1. Bölüm: Yol Platformu & Bordür Üretici
        box_plat = QGroupBox("1. Aşama: Yol Platformu")
        box_plat.setToolTip("Yol platformu, refüj ve bordür/kaldırım üretimi")
        lay_plat = QVBoxLayout(box_plat)
        lay_plat.setSpacing(6)

        form_plat = QFormLayout()
        form_plat.setSpacing(6)

        self.cmb_road_layer = QgsMapLayerComboBox()
        self.cmb_road_layer.setFilters(QgsMapLayerProxyModel.Filter.LineLayer)
        form_plat.addRow("Yol Orta Çizgisi Katmanı:", self.cmb_road_layer)

        self.cmb_road_width_field = QComboBox()
        self.cmb_road_layer.layerChanged.connect(self._road_layer_combo_changed)
        form_plat.addRow("Yol genişliği alanı:", self.cmb_road_width_field)

        self.spn_default_road_width = QDoubleSpinBox()
        self.spn_default_road_width.setRange(3.0, 100.0)
        self.spn_default_road_width.setValue(12.0)
        self.spn_default_road_width.setSuffix(" metre")
        form_plat.addRow("Sabit / Varsayılan Genişlik:", self.spn_default_road_width)

        self.spn_sidewalk_width = QDoubleSpinBox()
        self.spn_sidewalk_width.setRange(0.0, 20.0)
        self.spn_sidewalk_width.setValue(2.0)
        self.spn_sidewalk_width.setSuffix(" metre")
        form_plat.addRow("Kaldırım / Bordür Genişliği:", self.spn_sidewalk_width)

        self.spn_median_width = QDoubleSpinBox()
        self.spn_median_width.setRange(0.0, 20.0)
        self.spn_median_width.setValue(0.0)
        self.spn_median_width.setSuffix(" metre")
        form_plat.addRow("Orta Refüj Genişliği (Varsa):", self.spn_median_width)

        lay_plat.addLayout(form_plat)

        self.btn_run_platform = QPushButton("📐 Platform ve Kaldırımı Üret")
        self.btn_run_platform.setToolTip("Yol platformu ve kaldırım çizgilerini üret")
        self.btn_run_platform.setObjectName("PrimaryButton")
        self.btn_run_platform.setCursor(_POINTING_HAND)
        self.btn_run_platform.clicked.connect(self._on_run_road_platform)
        lay_plat.addWidget(self.btn_run_platform)
        layout.addWidget(box_plat)

        # 2. Bölüm: Kavşak Geometrisi & Yaklaşım Kırpma
        box_kavsak = QGroupBox("2. Aşama: Kavşak Kırpma")
        box_kavsak.setToolTip("Kavşak geometrisi ve yaklaşım kırpma (5 m)")
        lay_kavsak = QVBoxLayout(box_kavsak)
        lay_kavsak.setSpacing(6)

        form_kavsak = QFormLayout()
        form_kavsak.setSpacing(6)

        self.cmb_kavsak_layer = QgsMapLayerComboBox()
        self.cmb_kavsak_layer.setFilters(QgsMapLayerProxyModel.Filter.LineLayer)
        form_kavsak.addRow("İşlenecek Platform Çizgileri:", self.cmb_kavsak_layer)

        self.spn_kavsak_trim = QDoubleSpinBox()
        self.spn_kavsak_trim.setRange(1.0, 50.0)
        self.spn_kavsak_trim.setValue(5.0)
        self.spn_kavsak_trim.setSuffix(" metre")
        form_kavsak.addRow("Kavşak Kırpma Mesafesi:", self.spn_kavsak_trim)

        lay_kavsak.addLayout(form_kavsak)

        self.btn_run_kavsak = QPushButton("✂️ Kavşak Hatlarını Kırp")
        self.btn_run_kavsak.setToolTip("Kavşak hatlarını kırp ve yaklaşımları ayır")
        self.btn_run_kavsak.setObjectName("SecondaryButton")
        self.btn_run_kavsak.setCursor(_POINTING_HAND)
        self.btn_run_kavsak.clicked.connect(self._on_run_kavsak_trim)
        lay_kavsak.addWidget(self.btn_run_kavsak)
        layout.addWidget(box_kavsak)

        # 3. Bölüm: Yol Poligonlaştırma ve Plan Alanı Eşleştirme
        box_poly = QGroupBox("3. Aşama: Poligonlaştırma")
        box_poly.setToolTip("Yol dış çizgilerini poligonlaştırma ve fonksiyon eşleştirme")
        lay_poly = QVBoxLayout(box_poly)
        lay_poly.setSpacing(6)

        form_poly = QFormLayout()
        form_poly.setSpacing(6)

        self.cmb_poly_road_layer = QgsMapLayerComboBox()
        self.cmb_poly_road_layer.setFilters(QgsMapLayerProxyModel.Filter.LineLayer)
        form_poly.addRow("Kapanmış Yol Sınır Çizgileri:", self.cmb_poly_road_layer)

        self.cmb_poly_plan_layer = QgsMapLayerComboBox()
        self.cmb_poly_plan_layer.setFilters(QgsMapLayerProxyModel.Filter.PolygonLayer)
        form_poly.addRow("NİP İmar Planı Fonksiyon Katmanı:", self.cmb_poly_plan_layer)

        lay_poly.addLayout(form_poly)

        self.btn_run_poly = QPushButton("🔄 Yolları Poligonlaştır")
        self.btn_run_poly.setToolTip("Yolları poligonlaştır ve plan fonksiyonlarına bağla")
        self.btn_run_poly.setObjectName("AccentButton")
        self.btn_run_poly.setCursor(_POINTING_HAND)
        self.btn_run_poly.clicked.connect(self._on_run_road_polygonize)
        lay_poly.addWidget(self.btn_run_poly)
        layout.addWidget(box_poly)

        layout.addStretch()

        # Trigger initial field population
        self._on_road_layer_changed()

        return tab

    def _on_mpyy_road_draw(self):
        katmanlar, eksik = MpyyYolCizimAraci.katmanlari_bul()
        if eksik:
            QMessageBox.warning(
                self, "MPYY Yol",
                "Projede bulunamayan katman: " + ", ".join(eksik)
                + "\n\nÖnce 'NİP Veritabanı' sekmesinden Resmî MPYY 1.1.7 veritabanını oluşturup yükleyin.")
            return
        dlg = YolProfilDialog(self, getattr(self, "_mpyy_profil", None) or YolProfili())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._mpyy_profil = dlg.profil()
        hatalar = self._mpyy_profil.dogrula()
        if hatalar:
            QMessageBox.warning(self, "MPYY Yol", "\n".join(hatalar))
            return
        if not self.iface:
            return
        self._mpyy_road_tool = MpyyYolCizimAraci(self.iface, self._mpyy_profil)
        self._mpyy_road_tool.mesaj.connect(lambda text: self.iface.statusBarIface().showMessage(text))
        self.iface.mapCanvas().setMapTool(self._mpyy_road_tool)

    def _on_mpyy_platform_batch(self):
        katmanlar, eksik = MpyyYolCizimAraci.katmanlari_bul()
        if eksik:
            QMessageBox.warning(self, "MPYY Yol", "Projede bulunamayan katman: " + ", ".join(eksik))
            return
        processing.execAlgorithmDialog("pln3113:nip_mpyy_yol_platform", {
            "YOLORTA": katmanlar["Yolorta"],
            "DIGER": katmanlar["DigerYolNesneleri"],
            "ADA": katmanlar["AdaKenari"],
        })

    def _on_run_nip_audit(self):
        ref = find_mpyy_layer("GelismeKonut") or find_mpyy_layer("PlanSiniri")
        gpkg = ref.source().split("|")[0] if ref is not None else self.txt_db_path.text().strip()
        if not gpkg or not os.path.exists(gpkg):
            QMessageBox.warning(self, "NİP Denetimi", "Denetlenecek MPYY 1.1.7 NİP GeoPackage bulunamadı.")
            return
        project = QgsProject.instance()
        unsaved = [lyr.name() for lyr in project.mapLayers().values()
                   if isinstance(lyr, QgsVectorLayer) and lyr.isModified() and lyr.source().split("|")[0] == gpkg]
        if unsaved:
            QMessageBox.information(
                self, "NİP Denetimi",
                "Denetim kayıtlı veriyi okur; şu katmanlarda kaydedilmemiş düzenleme var:\n- "
                + "\n- ".join(unsaved[:10]) + "\n\nSonuç bu düzenlemeleri içermeyecek.")
        try:
            self.btn_nip_audit.setEnabled(False)
            res = processing.run("pln3113:nip_mpyy_denetim", {"INPUT": gpkg, "OUTPUT": "TEMPORARY_OUTPUT"})
        except Exception as exc:
            QMessageBox.critical(self, "NİP Denetimi", f"Denetim çalıştırılamadı:\n{exc}")
            return
        finally:
            self.btn_nip_audit.setEnabled(True)
        out = res.get("OUTPUT")
        if isinstance(out, str):
            out = QgsVectorLayer(out, "NİP Denetim Bulguları", "ogr")
        for old in project.mapLayersByName("NİP Denetim Bulguları"):
            project.removeMapLayer(old.id())
        out.setName("NİP Denetim Bulguları")
        style_nip_denetim(out)
        project.addMapLayer(out)
        count = int(res.get("BULGU_SAYISI") or 0)
        if count:
            QMessageBox.information(
                self, "NİP Denetimi",
                f"{count} bulgu 'NİP Denetim Bulguları' katmanına eklendi.\n"
                "Katmanın öznitelik tablosunda bir satırı seçip 'Seçili nesneye yakınlaştır' ile yerine gidebilirsiniz.")
        else:
            QMessageBox.information(self, "NİP Denetimi", "Bulgu yok: çizim denetimden geçti.")

    def _on_road_layer_changed(self):
        if not hasattr(self, "cmb_road_width_field"):
            return
        self.cmb_road_width_field.clear()
        self.cmb_road_width_field.addItem("[Sabit / Varsayılan Değeri Kullan]", "")
        layer = self.cmb_road_layer.currentLayer()
        if layer and isinstance(layer, QgsVectorLayer):
            for field in layer.fields():
                self.cmb_road_width_field.addItem(field.name(), field.name())
            for candidate in ["yolGenislik2", "genislik", "GENISLIK", "width", "WIDTH", "yol_genisligi"]:
                idx = self.cmb_road_width_field.findText(candidate)
                if idx >= 0:
                    self.cmb_road_width_field.setCurrentIndex(idx)
                    break

    def _on_run_road_platform(self):
        layer = self.cmb_road_layer.currentLayer()
        if not layer or not isinstance(layer, QgsVectorLayer):
            QMessageBox.warning(self, "Uyarı", "Lütfen geçerli bir yol orta çizgi katmanı seçin!")
            return

        width_field = self.cmb_road_width_field.currentData() or ""
        default_width = self.spn_default_road_width.value()

        params = {
            'INPUT': layer,
            'FIELD_GENISLIK': width_field if width_field else None,
            'DEFAULT_GENISLIK': default_width,
            'OUTPUT': 'TEMPORARY_OUTPUT'
        }

        try:
            self.btn_run_platform.setEnabled(False)
            res = processing.run("pln3113:nip_yol_platform_uretici", params)
            out_layer = res.get('OUTPUT')
            if out_layer:
                if isinstance(out_layer, str):
                    out_layer = QgsVectorLayer(out_layer, f"Yol Platformu ({layer.name()})", "ogr")
                else:
                    out_layer.setName(f"Yol Platformu ({layer.name()})")
                style_road_platform(out_layer)
                QgsProject.instance().addMapLayer(out_layer)
                self.cmb_kavsak_layer.setLayer(out_layer)
                QMessageBox.information(
                    self, "Başarılı",
                    f"Yol platformu, refüj ve bordür çizgileri başarıyla üretildi!\n"
                    f"Üretilen Katman: {out_layer.name()}\n"
                    f"Öğe Sayısı: {out_layer.featureCount()}"
                )
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Yol platformu üretilirken hata:\n{str(e)}")
        finally:
            self.btn_run_platform.setEnabled(True)

    def _on_run_kavsak_trim(self):
        layer = self.cmb_kavsak_layer.currentLayer()
        if not layer or not isinstance(layer, QgsVectorLayer):
            QMessageBox.warning(self, "Uyarı", "Lütfen geçerli bir yol platform katmanı seçin!")
            return

        radius = self.spn_kavsak_trim.value() * 4.0
        split_dist = self.spn_kavsak_trim.value()

        params = {
            'INPUT': layer,
            'RADIUS': radius,
            'SPLIT_DIST': split_dist,
            'TOLERANCE': 0.25,
            'OUTPUT': 'TEMPORARY_OUTPUT'
        }

        try:
            self.btn_run_kavsak.setEnabled(False)
            res = processing.run("pln3113:nip_yol_kavsak_trim", params)
            out_layer = res.get('OUTPUT')
            if out_layer:
                if isinstance(out_layer, str):
                    out_layer = QgsVectorLayer(out_layer, f"Kavşak Trim ({layer.name()})", "ogr")
                else:
                    out_layer.setName(f"Kavşak Trim ({layer.name()})")
                style_road_junctions(out_layer)
                QgsProject.instance().addMapLayer(out_layer)
                self.cmb_poly_road_layer.setLayer(out_layer)
                QMessageBox.information(
                    self, "Başarılı",
                    f"Kavşak hatları kırpıldı ve yaklaşımlar parçalandı!\n"
                    f"Üretilen Katman: {out_layer.name()}\n"
                    f"Öğe Sayısı: {out_layer.featureCount()}"
                )
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Kavşak kırpma işleminde hata:\n{str(e)}")
        finally:
            self.btn_run_kavsak.setEnabled(True)

    def _on_run_road_polygonize(self):
        road_layer = self.cmb_poly_road_layer.currentLayer()
        if not road_layer or not isinstance(road_layer, QgsVectorLayer):
            QMessageBox.warning(self, "Uyarı", "Lütfen kapanmış yol dış sınır çizgileri katmanını seçin!")
            return

        plan_layer = self.cmb_poly_plan_layer.currentLayer()
        if not plan_layer or not isinstance(plan_layer, QgsVectorLayer):
            QMessageBox.warning(self, "Uyarı", "Lütfen referans NİP plan kullanım poligonları katmanını seçin!")
            return

        params = {
            'INPUT_LINES': road_layer,
            'INPUT_ZONES': plan_layer,
            'INCLUDE_MANUAL': True,
            'OUTPUT': 'TEMPORARY_OUTPUT'
        }

        try:
            self.btn_run_poly.setEnabled(False)
            res = processing.run("pln3113:nip_yol_poligonlasma_esleme", params)
            out_layer = res.get('OUTPUT')
            if out_layer:
                if isinstance(out_layer, str):
                    out_layer = QgsVectorLayer(out_layer, f"Poligonlaşan Yollar/Adalar ({road_layer.name()})", "ogr")
                else:
                    out_layer.setName(f"Poligonlaşan Yollar/Adalar ({road_layer.name()})")
                style_road_polygons(out_layer)
                QgsProject.instance().addMapLayer(out_layer)
                QMessageBox.information(
                    self, "Başarılı",
                    f"Yol sınırları poligonlaştırıldı ve plan fonksiyonları eşleştirildi!\n"
                    f"Üretilen Poligon Katmanı: {out_layer.name()}\n"
                    f"Poligon Sayısı: {out_layer.featureCount()}"
                )
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Poligonlaştırma işleminde hata:\n{str(e)}")
        finally:
            self.btn_run_poly.setEnabled(True)

    # -----------------------------------------------------------------
    # SEKME 4: NİP PLAN NÜFUSU, DONATI, KAMU-ÖZEL & DOP ANALİZİ
    # -----------------------------------------------------------------
    # -----------------------------------------------------------------
    # SEKME: NÜFUS PROJEKSİYONU (C1 core/projection.py; formül dock'ta yok)
    # -----------------------------------------------------------------
    def _create_tab_projection(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        box = QGroupBox("Nüfus Projeksiyonu")
        box.setToolTip("Sayım / ADNKS yılları ve nüfuslarından hedef yıl nüfusunu kestirir; "
                       "sonucu NİP hedef nüfusuna aktarabilirsiniz.")
        lay = QVBoxLayout(box)
        lay.setSpacing(6)

        lbl_in = QLabel("Yıl ve nüfus değerlerini girin (en az iki yıl):")
        lay.addWidget(lbl_in)

        self.tbl_proj_input = QTableWidget(4, 2)
        self.tbl_proj_input.setHorizontalHeaderLabels(["Yıl", "Nüfus"])
        self.tbl_proj_input.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_proj_input.verticalHeader().setVisible(False)
        self.tbl_proj_input.setMinimumHeight(120)
        self.tbl_proj_input.setMaximumHeight(170)
        lay.addWidget(self.tbl_proj_input)

        row_btns = QHBoxLayout()
        btn_add = QPushButton("Ekle")
        btn_add.setToolTip("Tabloya yeni bir yıl satırı ekle")
        btn_add.clicked.connect(lambda: self.tbl_proj_input.insertRow(self.tbl_proj_input.rowCount()))
        btn_del = QPushButton("Sil")
        btn_del.setToolTip("Seçili (ya da son) satırı sil")
        btn_del.clicked.connect(self._proj_remove_row)
        self.btn_proj_example = QPushButton("Örnek: Tire")
        self.btn_proj_example.setToolTip("Örnek veri: Tire (İzmir) ilçe toplamı — 1990 DİE sayımı, "
                                         "2015 ve 2025 TÜİK ADNKS. Kendi yerleşmenizin değerleriyle değiştirin.")
        self.btn_proj_example.clicked.connect(self._proj_fill_example)
        row_btns.addWidget(btn_add)
        row_btns.addWidget(btn_del)
        row_btns.addWidget(self.btn_proj_example)
        lay.addLayout(row_btns)

        form = QFormLayout()
        self.cmb_proj_method = QComboBox()
        for key, label in PROJECTION_METHODS:
            self.cmb_proj_method.addItem(label, key)
        self.cmb_proj_method.setToolTip("İller Bankası oranı sınırlandığında, lojistik model doyum "
                                        "sınırına yaklaştığında sonuçla birlikte uyarı verilir.")
        form.addRow("Yöntem:", self.cmb_proj_method)
        self.spn_proj_target_year = QSpinBox()
        self.spn_proj_target_year.setRange(1950, 2200)
        self.spn_proj_target_year.setValue(2045)
        form.addRow("Hedef yıl:", self.spn_proj_target_year)
        lay.addLayout(form)

        self.btn_proj_run = QPushButton("📈 Projeksiyonu Hesapla")
        self.btn_proj_run.setObjectName("PrimaryButton")
        self.btn_proj_run.setCursor(_POINTING_HAND)
        self.btn_proj_run.clicked.connect(self._run_projection)
        lay.addWidget(self.btn_proj_run)

        self.lbl_proj_result = QLabel("Sonuç burada görünecek: hedef yıl nüfusu, R², geriye dönük "
                                      "sınama hatası ve uyarılar.")
        self.lbl_proj_result.setWordWrap(True)
        self.lbl_proj_result.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_proj_result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_proj_result.setStyleSheet(note_css("info"))
        lay.addWidget(self.lbl_proj_result)

        self.btn_proj_apply = QPushButton("⤵ Hedef Nüfusa Aktar")
        self.btn_proj_apply.setToolTip("Hesaplanan nüfusu NİP & DOP sayfasındaki hedef nüfus kutusuna yazar")
        self.btn_proj_apply.setEnabled(False)
        self.btn_proj_apply.clicked.connect(self._apply_projection_to_target)
        lay.addWidget(self.btn_proj_apply)
        layout.addWidget(box)

        box_tools = QGroupBox("İleri Nüfus Araçları")
        box_tools.setToolTip("Processing araç kutusundaki algoritmaları iletişim penceresiyle açar")
        tools_lay = QVBoxLayout(box_tools)
        tools_lay.setSpacing(4)
        for alg_name, title, tip in LINKED_ALGORITHMS:
            btn = QPushButton(f"⚙️ {title}")
            btn.setToolTip(tip)
            btn.setCursor(_POINTING_HAND)
            btn.clicked.connect(lambda _checked=False, n=alg_name: self._open_algorithm_dialog(n))
            setattr(self, f"btn_open_{alg_name}", btn)
            tools_lay.addWidget(btn)
        self.lbl_proj_tools_status = QLabel("")
        self.lbl_proj_tools_status.setWordWrap(True)
        self.lbl_proj_tools_status.setStyleSheet(text_css("subtle", "8pt"))
        tools_lay.addWidget(self.lbl_proj_tools_status)
        layout.addWidget(box_tools)

        lbl_credit = QLabel("Nüfus projeksiyonu, dağıtım ve kırılganlık araçları Kent Öngörü v1.0.0 "
                            "(Berkay Memiş, GPL-2.0-or-later) temel alınarak yeniden yazıldı.")
        lbl_credit.setStyleSheet(text_css("subtle", "8pt"))
        layout.addWidget(lbl_credit)
        layout.addStretch()
        return tab

    def _proj_remove_row(self):
        table = self.tbl_proj_input
        row = table.currentRow() if table.currentRow() >= 0 else table.rowCount() - 1
        if row >= 0:
            table.removeRow(row)

    def _proj_fill_example(self):
        """Örnek ön ayar: Tire (İzmir) ilçe toplamı (yalnızca örnek)."""
        rows = []
        try:
            from .core.tire_constants import TIRE_POPULATION_BENCHMARKS as bench
            for key, year in (("plan_1997_die", 1990), ("tuik_2015_kesin", 2015), ("tuik_2026_guncel", 2025)):
                if key in bench:
                    rows.append((year, int(bench[key]["ilce"])))
        except (ImportError, KeyError, TypeError, ValueError):
            rows = []
        table = self.tbl_proj_input
        table.setRowCount(max(len(rows), 2))
        for r, (year, pop) in enumerate(rows):
            table.setItem(r, 0, QTableWidgetItem(str(year)))
            table.setItem(r, 1, QTableWidgetItem(str(pop)))

    def _projection_input(self):
        """Tablodaki yıl/nüfus satırlarını okur. Dönüş: (yıllar, nüfuslar, hata_metni)."""
        pairs, bad = [], []
        table = self.tbl_proj_input
        for r in range(table.rowCount()):
            cells = [table.item(r, c).text().strip() if table.item(r, c) else "" for c in range(2)]
            if not any(cells):
                continue
            try:
                year = int(cells[0])
                pop = float(cells[1].replace(".", "").replace(" ", "").replace(",", "."))
            except ValueError:
                bad.append(r + 1)
                continue
            pairs.append((year, pop))
        if bad:
            return [], [], f"{', '.join(map(str, bad))}. satır sayı değil; yılı ve nüfusu rakamla yazın."
        pairs.sort()
        years = [p[0] for p in pairs]
        if len(set(years)) < 2:
            return [], [], "En az iki farklı yıl ve nüfus girin."
        if len(set(years)) != len(years):
            return [], [], "Aynı yıl birden çok kez girilmiş."
        return years, [p[1] for p in pairs], ""

    def _run_projection(self):
        """C1 project_trend'i çağırır; sonucu ve uyarıları dock'ta gösterir."""
        self._last_projection = None
        self.btn_proj_apply.setEnabled(False)
        years, pops, error = self._projection_input()
        target_year = self.spn_proj_target_year.value()
        if not error and target_year <= years[-1]:
            error = f"Hedef yıl son veri yılından ({years[-1]}) sonra olmalı."
        if error:
            self._show_projection_message(error, "warn")
            return
        method = self.cmb_proj_method.currentData()
        try:
            from .core import projection
            result = projection.project_trend(years, pops, method, target_year)
        except ImportError:
            self._show_projection_message("Projeksiyon modülü (core/projection.py) bu kurulumda yok.", "bad")
            return
        except (ValueError, ZeroDivisionError, OverflowError, TypeError) as exc:
            self._show_projection_message(f"Bu verilerle {self.cmb_proj_method.currentText()} hesaplanamadı: {exc}", "bad")
            return
        self._last_projection = dict(result, method=method, target_year=target_year)
        lines = [f"<b>{target_year} nüfusu: {_tr_int(result['value'])} kişi</b> "
                 f"({html.escape(str(result.get('label') or self.cmb_proj_method.currentText()))})"]
        if result.get("params_text"):
            lines.append(html.escape(str(result["params_text"])))
        if result.get("r2") is not None:
            lines.append(f"R² = {_tr_num(result['r2'], 3)}")
        if result.get("backtest_pct") is not None:
            lines.append(f"Geriye dönük sınama hatası: %{_tr_num(result['backtest_pct'], 1)}")
        warnings = [str(w) for w in (result.get("warnings") or [])]
        for warning in warnings:
            lines.append(f"⚠ {html.escape(warning)}")
        self._show_projection_message("<br>".join(lines), "warn" if warnings else "ok", rich=True)
        self.btn_proj_apply.setEnabled(True)

    def _show_projection_message(self, text: str, tone: str, rich: bool = False):
        self.lbl_proj_result.setStyleSheet(note_css(tone))
        self.lbl_proj_result.setText(text if rich else html.escape(text))

    def _apply_projection_to_target(self):
        """Projeksiyon sonucunu NİP hedef nüfus kutusuna aktarır ve NİP sayfasını açar."""
        if not self._last_projection:
            return
        value = int(round(float(self._last_projection["value"])))
        if value > self.spn_proj_nufus.maximum():
            self.spn_proj_nufus.setMaximum(value)
        self.spn_proj_nufus.setValue(max(value, self.spn_proj_nufus.minimum()))
        self.set_page(self.nip_page_index)

    @staticmethod
    def _algorithm_id(name: str) -> str | None:
        """Bu eklentinin sağlayıcısındaki algoritma kimliği (sağlayıcı kimliğinden bağımsız)."""
        from qgis.core import QgsApplication
        registry = QgsApplication.processingRegistry()
        for provider_id in ("pln3113", "pln3113_nip"):
            alg = registry.algorithmById(f"{provider_id}:{name}")
            if alg is not None:
                return alg.id()
        return None

    def _open_algorithm_dialog(self, name: str):
        alg_id = self._algorithm_id(name)
        if alg_id is None or processing is None or not hasattr(processing, "execAlgorithmDialog"):
            self.lbl_proj_tools_status.setText(
                f"“{name}” algoritması Processing araç kutusunda bulunamadı; eklentiyi yeniden yükleyin.")
            return
        self.lbl_proj_tools_status.setText("")
        processing.execAlgorithmDialog(alg_id, {})

    def _ek2_reference_html(self) -> str:
        """Rehber sayfası için Ek-2 değerleri — hesapta kullanılan tablodan okunur."""
        try:
            from .core.tire_constants import EK2_NUFUS_GRUPLARI as groups
            from .core.tire_constants import MPYY_DONATI_STANDARTLARI as table
            rows = [(v.get("adi", k), [float(x) for x in v["kademeler"]]) for k, v in table.items()]
            labels = [str(label) for _upper, label in groups]
        except (ImportError, AttributeError, KeyError, TypeError, ValueError):
            rows, labels = [], []
        if not rows or not labels:
            return "Ek-2 standart tablosu bu kurulumda okunamadı."
        items = "<br>".join(
            f"• <b>{html.escape(str(name))}:</b> " + " | ".join(_tr_num(v, 2) for v in values) + " m²/kişi"
            for name, values in rows)
        totals = " | ".join(_tr_num(sum(values[i] for _n, values in rows), 2) for i in range(len(labels)))
        return (f"<i>Nüfus grupları: {html.escape(' | '.join(labels))} (ilçe projeksiyon nüfusu)</i><br>"
                f"{items}<br>➡️ <i>Toplam: <b>{totals} m²/kişi</b>. Kaynak: MPYY (RG 14.06.2014/29030) "
                "md. 11 ve EK-2 tablosu (Değişik: RG 17.05.2017/30069); teknik altyapı yol ve otopark "
                "hariçtir; semt spor alanı açık-yeşil alana, ÖZEL eğitim/sağlık/sosyal/kültürel tesisler "
                "standarda dahildir (EK-2 Açıklama 8-9).</i>")

    def _create_tab_nip(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Bilgi Barı
        info_banner = QFrame()
        info_banner.setStyleSheet(note_css("info"))
        info_l = QVBoxLayout(info_banner)
        info_l.setContentsMargins(6, 4, 6, 4)
        lbl_hint = QLabel("💡 <b>NİP Metodolojisi:</b> Nüfus aralıkları, MPYY Ek-2 standartları, DOP ve yol hesapları.")
        lbl_hint.setStyleSheet(f"color: {self._c['info']}; background: transparent; border: none;")
        btn_hint_guide = QPushButton("📖 El Kitabı")
        btn_hint_guide.setCursor(_POINTING_HAND)
        btn_hint_guide.clicked.connect(self._open_theoretical_guide)
        info_l.addWidget(lbl_hint)
        info_l.addWidget(btn_hint_guide)
        layout.addWidget(info_banner)

        # 1. Girdi Kutusu
        box_nip = QGroupBox("Katman ve Parametreler")
        box_nip.setToolTip("NİP & fiziki mevcut durum katmanı ve parametreler")
        f_layout = QFormLayout(box_nip)

        self.cmb_analysis_mode = QComboBox()
        self.cmb_analysis_mode.addItem("Nazım İmar Planı (NİP - Öneri / Revizyon)")
        self.cmb_analysis_mode.addItem("Fiziki Mevcut Durum (TUCBS / Arazi Kullanımı)")
        self.cmb_analysis_mode.currentIndexChanged.connect(self._on_analysis_mode_changed)
        f_layout.addRow("Analiz modu:", self.cmb_analysis_mode)

        self.cmb_nip_layer = QgsMapLayerComboBox()
        self.cmb_nip_layer.setFilters(QgsMapLayerProxyModel.Filter.PolygonLayer)
        self.cmb_nip_layer.layerChanged.connect(self._nip_layer_combo_changed)
        f_layout.addRow("Analiz katmanı:", self.cmb_nip_layer)

        self.cmb_fonk_field = QComboBox()
        self.cmb_fonk_field.currentTextChanged.connect(self._on_fonk_col_changed)
        f_layout.addRow("Fonksiyon sütunu:", self.cmb_fonk_field)

        self.cmb_secondary_fonk_field = QComboBox()
        self.cmb_secondary_fonk_field.currentTextChanged.connect(self._on_fonk_col_changed)
        f_layout.addRow("İkincil sütun (ops.):", self.cmb_secondary_fonk_field)

        self.cmb_sinir_layer = QgsMapLayerComboBox()
        self.cmb_sinir_layer.setFilters(QgsMapLayerProxyModel.Filter.PolygonLayer)
        self.cmb_sinir_layer.setAllowEmptyLayer(True)
        self.cmb_sinir_layer.layerChanged.connect(self._sinir_layer_combo_changed)
        f_layout.addRow("Plan onama sınırı (ops.):", self.cmb_sinir_layer)

        self.cmb_sinir_modu = QComboBox()
        self.cmb_sinir_modu.addItem("✂️ Sınırla Kırp (Clip - Önerilen)", "clip")
        self.cmb_sinir_modu.addItem("➕ Değenleri Dahil Et (Intersect)", "intersect")
        self.cmb_sinir_modu.addItem("⛔ Yalnız Tamamen İçeridekiler (Within)", "within")
        self.cmb_sinir_modu.addItem("🎯 Ağırlık Merkezine Göre (Centroid)", "centroid")
        f_layout.addRow("Sınır kesişim modu:", self.cmb_sinir_modu)

        self.lbl_sinir_foolproof = QLabel(
            "<b>💡 Öğrenci Kılavuzu — Plan Onama Sınırı & Kesişim Mantığı:</b><br>"
            "• <b>Sınır Dışındaki Adalar:</b> Belirlediğiniz Plan Onama Sınırının <u>tamamen dışında</u> kalan "
            "tüm ada ve poligonlar analize KESİNLİKLE dahil edilmez (otomatik filtrelenip elenir).<br>"
            "• <b>Sınırı Aşan / Kısmen Dışarı Taşan Adalar İçin Seçenekler:</b><br>"
            "&nbsp;&nbsp;<b>1. Sınırla Kırp / Kes (Clip - Önerilen):</b> Taşan kısmı tam sınır çizgisinden keser, "
            "sadece sınır içinde kalan net parçayı ve nüfusu hesaba katar.<br>"
            "&nbsp;&nbsp;<b>2. Sınıra Değenleri Dahil Et (Intersect):</b> Adanın ucu dahi sınıra giriyorsa adayı bölmeden tamamını analize katar.<br>"
            "&nbsp;&nbsp;<b>3. Kesişenleri Hariç Tut (Within):</b> Dışarıya 1 mm bile taşan adaları tamamen eler; sadece %100 içeride kalanları alır.<br>"
            "&nbsp;&nbsp;<b>4. Ağırlık Merkezine Göre (Centroid):</b> Adanın ağırlık merkezi sınır içindeyse tamamını alır, dışındaysa eler.<br>"
            "• <b>Sınır yoksa</b> yol alanı tahmin edilir; DOP oranı tahminidir ve yasal sınır değerlendirmesi yapılmaz."
        )
        self.lbl_sinir_foolproof.setWordWrap(True)
        self.lbl_sinir_foolproof.setStyleSheet(note_css("warn", "8.5pt"))
        f_layout.addRow(self.lbl_sinir_foolproof)

        self.cmb_yol_layer = QgsMapLayerComboBox()
        self.cmb_yol_layer.setFilters(QgsMapLayerProxyModel.Filter.LineLayer)
        self.cmb_yol_layer.setAllowEmptyLayer(True)
        f_layout.addRow("Yol aksları (ops.):", self.cmb_yol_layer)

        self.spn_proj_nufus = QSpinBox()
        self.spn_proj_nufus.setRange(100, 50000000)
        self.spn_proj_nufus.setValue(65000)
        self.spn_proj_nufus.setSingleStep(1000)
        self.spn_proj_nufus.setGroupSeparatorShown(True)
        self.spn_proj_nufus.setSuffix(" kişi")
        self.spn_proj_nufus.setToolTip("Plan hedef yılı nüfusu. “Nüfus” sayfasındaki projeksiyondan aktarılabilir.")
        f_layout.addRow("Hedef nüfus:", self.spn_proj_nufus)

        self.spn_kirsal_nufus = QSpinBox()
        self.spn_kirsal_nufus.setRange(0, 50000000)
        self.spn_kirsal_nufus.setValue(0)
        self.spn_kirsal_nufus.setSingleStep(1000)
        self.spn_kirsal_nufus.setGroupSeparatorShown(True)
        self.spn_kirsal_nufus.setSuffix(" kişi")
        self.spn_kirsal_nufus.setToolTip("İlçe toplamı için NİP nüfusuna eklenecek kırsal nüfus (yoksa 0).")
        f_layout.addRow("Kırsal nüfus (ops.):", self.spn_kirsal_nufus)

        self.btn_go_projection = QPushButton("📈 Projeksiyondan Hesapla")
        self.btn_go_projection.setToolTip("Nüfus sayfasını açar: yıl/nüfus verisinden hedef nüfusu kestirin")
        self.btn_go_projection.clicked.connect(lambda: self.set_page(self.projection_page_index))
        f_layout.addRow(self.btn_go_projection)

        layout.addWidget(box_nip)

        # 2. Planlama, DOP, İstihdam & Yolculuk Kuralları (Dahil / Hariç) - Açılır Kutu
        self.box_rules = QGroupBox("⚙️ DOP, İstihdam ve Yolculuk")
        self.box_rules.setToolTip("İstihdam, yolculuk ve DOP kuralları (dahil / hariç ve katsayılar)")
        self.box_rules.setCheckable(True)
        self.box_rules.setChecked(False)  # Başlangıçta derli toplu dursun
        rules_layout = QVBoxLayout(self.box_rules)

        lbl_rules_info = QLabel(
            "<b>Dahil / Hariç Düzeni:</b> Varsayılan planlama katsayıları ve DOP kapsamı aktiftir. "
            "İstediğiniz fonksiyonu DOP içi (düzenlemeye dahil) veya nDOP / DOP Dışı (harice ayrılan) olarak seçebilir; "
            "istihdam veya yolculuktan hariç tutabilir ya da katsayılarını değiştirebilirsiniz."
        )
        lbl_rules_info.setWordWrap(True)
        lbl_rules_info.setStyleSheet(note_css("ok", "8.5pt"))
        rules_layout.addWidget(lbl_rules_info)

        btn_rules_bar = QHBoxLayout()
        self.btn_load_fonks = QPushButton("🔄 Katmandan Oku")
        self.btn_load_fonks.setToolTip("Katmandaki fonksiyonları tabloya oku")
        self.btn_load_fonks.clicked.connect(self._load_rules_table_from_layer)
        self.btn_reset_rules = QPushButton("Sıfırla")
        self.btn_reset_rules.setToolTip("Varsayılanlara sıfırla")
        self.btn_reset_rules.clicked.connect(self._reset_rules_to_defaults)
        btn_rules_bar.addWidget(self.btn_load_fonks)
        btn_rules_bar.addWidget(self.btn_reset_rules)
        rules_layout.addLayout(btn_rules_bar)

        self.tbl_rules = QTableWidget()
        self.tbl_rules.setColumnCount(9)
        self.tbl_rules.setHorizontalHeaderLabels([
            "Plan Fonksiyonu", "DOP İçi (Dahil)?", "DOP Türü",
            "İstihdam Dahil?", "m²/Çalışan", "Verim (0-1)",
            "Araç Dahil?", "Yaya Dahil?", "Araç (100m²)"
        ])
        self.tbl_rules.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_rules.horizontalHeader().setStretchLastSection(True)
        self.tbl_rules.verticalHeader().setVisible(False)
        self.tbl_rules.setMinimumHeight(150)
        self.tbl_rules.setMaximumHeight(230)
        self.tbl_rules.itemChanged.connect(self._on_rules_table_item_changed)
        rules_layout.addWidget(self.tbl_rules)

        layout.addWidget(self.box_rules)

        # 3. Nüfus Kıyaslama Tablosu (ön ayar; Tire yalnızca örnek)
        box_bench = QGroupBox("Nüfus Kıyaslaması")
        box_bench.setToolTip("Tarihsel nüfus ve plan hedefleriyle kıyas; hazır veri yalnızca örnektir.")
        bench_layout = QVBoxLayout(box_bench)

        self.cmb_kiyas_preset = QComboBox()
        self.cmb_kiyas_preset.addItem("Kıyas verisi yok", "yok")
        self.cmb_kiyas_preset.addItem("Örnek: Tire (İzmir) tarihsel nüfusu", "tire")
        self.cmb_kiyas_preset.currentIndexChanged.connect(self._fill_benchmark_table)
        bench_layout.addWidget(self.cmb_kiyas_preset)

        self.tbl_benchmark = QTableWidget(0, 3)
        self.tbl_benchmark.setHorizontalHeaderLabels(["Kapsam", "Kentsel merkez", "İlçe toplamı"])
        self.tbl_benchmark.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_benchmark.verticalHeader().setVisible(False)
        self.tbl_benchmark.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_benchmark.setMaximumHeight(150)
        bench_layout.addWidget(self.tbl_benchmark)

        self.lbl_bench_note = QLabel("")
        self.lbl_bench_note.setWordWrap(True)
        self.lbl_bench_note.setStyleSheet(text_css("subtle", "8pt"))
        bench_layout.addWidget(self.lbl_bench_note)
        layout.addWidget(box_bench)
        self._fill_benchmark_table()

        # 4. Çalıştır Butonu
        self.btn_run_nip = QPushButton("NİP Analizini Başlat")
        self.btn_run_nip.setToolTip("PLN3113 NİP nüfus, donatı, kamu-özel ve DOP analizini başlat")
        self.btn_run_nip.setObjectName("PrimaryButton")
        plan_icon_path = os.path.join(PLUGIN_DIR, "icons", "plan.png")
        if os.path.exists(plan_icon_path):
            self.btn_run_nip.setIcon(QIcon(plan_icon_path))
        self.btn_run_nip.clicked.connect(self._run_nip_analysis)
        layout.addWidget(self.btn_run_nip)

        # 5. Dışa Aktarma Buton Çubuğu
        export_bar = QHBoxLayout()
        self.btn_export_csv = QPushButton("CSV Kaydet")
        self.btn_export_csv.setToolTip("Tabloları CSV (Excel uyumlu) olarak kaydet")
        self.btn_export_csv.clicked.connect(self._export_nip_tables_csv)
        self.btn_export_csv.setEnabled(False)

        self.btn_export_html = QPushButton("HTML Rapor")
        self.btn_export_html.setToolTip("İnteraktif raporu HTML dosyası olarak kaydet")
        self.btn_export_html.clicked.connect(self._export_nip_report_html)
        self.btn_export_html.setEnabled(False)

        export_bar.addWidget(self.btn_export_csv)
        export_bar.addWidget(self.btn_export_html)
        layout.addLayout(export_bar)

        # Canlı Görsel Göstergeler (Mikro-Barlar)
        box_kpi_gauges = QGroupBox("Yasal Oran Göstergeleri")
        lay_kpi = QVBoxLayout(box_kpi_gauges)
        lay_kpi.setSpacing(4)

        lbl_dop_bar = QLabel("DOP oranı (yasal tavan %45):")
        lbl_dop_bar.setStyleSheet("font-weight: 600;")
        lay_kpi.addWidget(lbl_dop_bar)
        row_dop_bar = QHBoxLayout()
        self.bar_dop = QProgressBar()
        self.bar_dop.setRange(0, 80)
        self.bar_dop.setValue(0)
        self.bar_dop.setTextVisible(True)
        self.bar_dop.setFormat("%v% / tavan %45")
        self.bar_dop.setStyleSheet(chunk_css("ok"))
        self.lbl_dop_badge = QLabel("-")
        self.lbl_dop_badge.setStyleSheet(chip_css())
        row_dop_bar.addWidget(self.bar_dop, 1)
        row_dop_bar.addWidget(self.lbl_dop_badge)
        lay_kpi.addLayout(row_dop_bar)

        lbl_yesil_bar = QLabel("PAİY Md. 9 açık-yeşil payı (asgari %75):")
        lbl_yesil_bar.setStyleSheet("font-weight: 600;")
        lay_kpi.addWidget(lbl_yesil_bar)
        row_yesil_bar = QHBoxLayout()
        self.bar_yesil = QProgressBar()
        self.bar_yesil.setRange(0, 100)
        self.bar_yesil.setValue(0)
        self.bar_yesil.setTextVisible(True)
        self.bar_yesil.setFormat("%v% / asgari %75")
        self.bar_yesil.setStyleSheet(chunk_css("ok"))
        self.lbl_yesil_badge = QLabel("-")
        self.lbl_yesil_badge.setStyleSheet(chip_css())
        row_yesil_bar.addWidget(self.bar_yesil, 1)
        row_yesil_bar.addWidget(self.lbl_yesil_badge)
        lay_kpi.addLayout(row_yesil_bar)

        layout.addWidget(box_kpi_gauges)

        # İnteraktif Dashboard Butonu
        self.btn_open_dashboard = QPushButton("📊 İnteraktif Raporu Aç")
        self.btn_open_dashboard.setToolTip("İnteraktif NİP & DOP raporunu tarayıcıda aç (Plotly + Leaflet)")
        self.btn_open_dashboard.setObjectName("AccentButton")
        self.btn_open_dashboard.setCursor(_POINTING_HAND)
        self.btn_open_dashboard.setEnabled(False)
        self.btn_open_dashboard.clicked.connect(self._open_nip_dashboard)
        layout.addWidget(self.btn_open_dashboard)

        self.lbl_dashboard_network = QLabel(
            "🌐 İnteraktif rapor tarayıcıda açılırken plotly, Leaflet ve OpenStreetMap karolarını "
            f"internetten yükler ({', '.join(EXTERNAL_HOSTS)}).")
        self.lbl_dashboard_network.setWordWrap(True)
        self.lbl_dashboard_network.setStyleSheet(text_css("subtle", "8pt"))
        layout.addWidget(self.lbl_dashboard_network)

        # Katman Lejantı ve Stil Değiştirme Çubuğu
        style_nip_bar = QHBoxLayout()
        self.btn_style_density = QPushButton("📊 Yoğunluk")
        self.btn_style_density.setToolTip("Yoğunluk (UST_SNR) stilini uygula")
        self.btn_style_density.setCursor(_POINTING_HAND)
        self.btn_style_density.setEnabled(False)
        self.btn_style_density.clicked.connect(self._apply_density_style_nip)

        self.btn_style_mpyy = QPushButton("🎨 MPYY Lejantı")
        self.btn_style_mpyy.setToolTip("Resmî MPYY lejantını uygula")
        self.btn_style_mpyy.setCursor(_POINTING_HAND)
        self.btn_style_mpyy.setEnabled(False)
        self.btn_style_mpyy.clicked.connect(self._apply_mpyy_style_nip)

        style_nip_bar.addWidget(self.btn_style_density)
        style_nip_bar.addWidget(self.btn_style_mpyy)
        layout.addLayout(style_nip_bar)


        # 6. Sonuç Sekmeleri (Tab Widget)
        self.tabs_nip_results = QTabWidget()
        self.tabs_nip_results.setMinimumHeight(280)

        # 1. Alt Sekme: ⚖️ Kamu-Özel & DOP Dengesi
        self.tbl_dop = QTableWidget()
        self.tbl_dop.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_dop.verticalHeader().setVisible(False)
        self.tabs_nip_results.addTab(self.tbl_dop, "⚖️ Kamu-Özel & DOP")

        # 2. Alt Sekme: 🏛️ Kent Karakteri Tablosu
        self.tbl_kent_karakter = QTableWidget()
        self.tbl_kent_karakter.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_kent_karakter.verticalHeader().setVisible(False)
        self.tabs_nip_results.addTab(self.tbl_kent_karakter, "🏛️ Kent Karakteri")

        # 3. Alt Sekme: 📋 MPYY Ek-2 Donatı Dengesi
        self.tbl_ek2 = QTableWidget()
        self.tbl_ek2.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_ek2.verticalHeader().setVisible(False)
        self.tabs_nip_results.addTab(self.tbl_ek2, "📋 Ek-2 Donatı")

        # 4. Alt Sekme: 📊 Fonksiyon Dağılım Tablosu
        self.tbl_fonk_dagilim = QTableWidget()
        self.tbl_fonk_dagilim.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_fonk_dagilim.verticalHeader().setVisible(False)
        self.tabs_nip_results.addTab(self.tbl_fonk_dagilim, "📊 Fonksiyon Dağılımı")

        # 5. Alt Sekme: 📑 Detaylı HTML Konsol Özeti
        self.txt_nip_results = QTextEdit()
        self.txt_nip_results.setReadOnly(True)
        self.txt_nip_results.setPlaceholderText("Analiz sonuçları, DOP hesabı, kent karakteri ve donatı dengesi burada görüntülenecektir...")
        self.tabs_nip_results.addTab(self.txt_nip_results, "📑 Detaylı Rapor")

        layout.addWidget(self.tabs_nip_results)

        layout.addStretch()
        self._on_nip_layer_changed()
        return tab

    def _on_analysis_mode_changed(self, idx: int):
        self._load_rules_table_from_layer()

    def _on_nip_layer_changed(self):
        layer = self.cmb_nip_layer.currentLayer()
        self.cmb_fonk_field.blockSignals(True)
        self.cmb_secondary_fonk_field.blockSignals(True)
        try:
            self.cmb_fonk_field.clear()
            self.cmb_secondary_fonk_field.clear()
            self.cmb_secondary_fonk_field.addItem("<Yok / İkincil Sütun Yok>")
            if not layer or not isinstance(layer, QgsVectorLayer) or not layer.isValid():
                self.tbl_rules.blockSignals(True)
                self.tbl_rules.setRowCount(0)
                self.tbl_rules.blockSignals(False)
                return

            fields = [f.name() for f in layer.fields()]
            self.cmb_fonk_field.addItems(fields)
            self.cmb_secondary_fonk_field.addItems(fields)

            fields_lower = {f.lower(): f for f in fields}
            layer_name_lower = layer.name().lower()

            # Otomatik Mod ve Sütun Tespiti
            is_fiziki = (
                "tucbs_sinifi" in fields_lower
                or "arazi_kullanim_tanimi" in fields_lower
                or "kadastro" in layer_name_lower
                or "fiziki" in layer_name_lower
                or "mevcut" in layer_name_lower
            )

            if is_fiziki:
                self.cmb_analysis_mode.setCurrentIndex(1)
                if "tucbs_sinifi" in fields_lower:
                    self.cmb_fonk_field.setCurrentText(fields_lower["tucbs_sinifi"])
                elif "arazi_kullanim_tanimi" in fields_lower:
                    self.cmb_fonk_field.setCurrentText(fields_lower["arazi_kullanim_tanimi"])

                if "arazi_kullanim_tanimi" in fields_lower and self.cmb_fonk_field.currentText() != fields_lower["arazi_kullanim_tanimi"]:
                    self.cmb_secondary_fonk_field.setCurrentText(fields_lower["arazi_kullanim_tanimi"])
            else:
                self.cmb_analysis_mode.setCurrentIndex(0)
                priority = ["Ort__Detay", "Ort_Detay", "nipfonksiyon", "plan_fonksiyon", "fonksiyon", "Kullan__m_"]
                for p in priority:
                    if p in fields:
                        self.cmb_fonk_field.setCurrentText(p)
                        break
                self.cmb_secondary_fonk_field.setCurrentIndex(0)
        finally:
            self.cmb_fonk_field.blockSignals(False)
            self.cmb_secondary_fonk_field.blockSignals(False)

        # Fonksiyon tablosunu katmandan güvenle tek seferde doldur
        self._load_rules_table_from_layer()

    def _on_fonk_col_changed(self, col_name: str = ""):
        self._load_rules_table_from_layer(preserve_custom=False)

    def _on_sinir_layer_changed(self):
        has_sinir = (self.cmb_sinir_layer.currentLayer() is not None)
        self.cmb_sinir_modu.setEnabled(has_sinir)
        if hasattr(self, 'lbl_sinir_foolproof'):
            self.lbl_sinir_foolproof.setStyleSheet(note_css("warn" if has_sinir else "info", "8.5pt"))

    def _load_rules_table_from_layer(self, preserve_custom: bool = True):
        """Seçili katmandaki fonksiyonları okuyup kurallar tablosuna doldurur.
        Daha önce yapılmış kullanıcı özelleştirmeleri varsa korur, yeni fonksiyonlar için varsayılanları atar.
        """
        layer = self.cmb_nip_layer.currentLayer()
        col = self.cmb_fonk_field.currentText()
        if not layer or not isinstance(layer, QgsVectorLayer) or not layer.isValid() or not col:
            self.tbl_rules.blockSignals(True)
            self.tbl_rules.setRowCount(0)
            self.tbl_rules.blockSignals(False)
            return

        idx = layer.fields().indexOf(col)
        if idx == -1:
            return

        sec_col = self.cmb_secondary_fonk_field.currentText() if hasattr(self, 'cmb_secondary_fonk_field') else ""
        sec_idx = layer.fields().indexOf(sec_col) if sec_col and not sec_col.startswith("<") else -1

        unique_fonks_set = set()
        MAX_SAFE_FONKS = 120
        # Halihazır, kadastro veya ham CAD katmanlarında binlerce benzersiz ID/kot/etiket olabilir.
        # NİP plan fonksiyonları asla 60-80'i geçmez. 120'den fazlası bir fonksiyon sütunu değil sayısal/ID verisidir.
        for i, feat in enumerate(layer.getFeatures()):
            val1 = feat[idx]
            val = None
            if val1 is not None and str(val1).strip() not in ("", "NULL", "None"):
                val = str(val1).strip()
            elif sec_idx != -1:
                val2 = feat[sec_idx]
                if val2 is not None and str(val2).strip() not in ("", "NULL", "None"):
                    val = str(val2).strip()
            if val:
                unique_fonks_set.add(val)
                if len(unique_fonks_set) > MAX_SAFE_FONKS:
                    break
            if i > 50000:
                break

        if len(unique_fonks_set) > MAX_SAFE_FONKS:
            # Sütun bir fonksiyon sütunu değil (ID veya kot gibi benzersiz veri). Tabloyu doldurma (çökme koruması).
            self.tbl_rules.blockSignals(True)
            self.tbl_rules.setRowCount(0)
            self.tbl_rules.blockSignals(False)
            return

        unique_fonks = sorted(list(unique_fonks_set))
        if not unique_fonks:
            self.tbl_rules.blockSignals(True)
            self.tbl_rules.setRowCount(0)
            self.tbl_rules.blockSignals(False)
            return

        # Mevcut kullanıcı düzenlemelerini fonksiyon adına göre sakla
        existing_custom = {}
        if preserve_custom and self.tbl_rules.rowCount() > 0:
            for r in range(self.tbl_rules.rowCount()):
                f_item = self.tbl_rules.item(r, 0)
                if not f_item:
                    continue
                f_txt = f_item.text().strip()
                d_item = self.tbl_rules.item(r, 1)
                c_dop = self.tbl_rules.cellWidget(r, 2)
                e_item = self.tbl_rules.item(r, 3)
                s_item = self.tbl_rules.item(r, 4)
                ef_item = self.tbl_rules.item(r, 5)
                a_item = self.tbl_rules.item(r, 6)
                y_item = self.tbl_rules.item(r, 7)
                ra_item = self.tbl_rules.item(r, 8)
                existing_custom[f_txt] = {
                    "dop_inc": (d_item.checkState() == _CHECKED) if d_item else True,
                    "dop_combo_idx": c_dop.currentIndex() if (c_dop and isinstance(c_dop, QComboBox)) else 0,
                    "emp_inc": (e_item.checkState() == _CHECKED) if e_item else True,
                    "std_m2": s_item.text().strip() if s_item else "50.0",
                    "eff": ef_item.text().strip() if ef_item else "0.50",
                    "tr_arac": (a_item.checkState() == _CHECKED) if a_item else True,
                    "tr_yaya": (y_item.checkState() == _CHECKED) if y_item else True,
                    "r_arac": ra_item.text().strip() if ra_item else "1.0",
                }

        self.tbl_rules.blockSignals(True)
        self.tbl_rules.setRowCount(len(unique_fonks))
        for r_idx, fonk in enumerate(unique_fonks):
            # 0. Fonksiyon adı (Salt okunur)
            item_f = QTableWidgetItem(fonk)
            item_f.setFlags(item_f.flags() & ~_ITEM_EDITABLE)
            self.tbl_rules.setItem(r_idx, 0, item_f)

            if fonk in existing_custom:
                saved = existing_custom[fonk]
                dop_inc = saved["dop_inc"]
                combo_idx = saved["dop_combo_idx"]
                emp_inc = saved["emp_inc"]
                std_m2_str = saved["std_m2"]
                eff_str = saved["eff"]
                tr_arac = saved["tr_arac"]
                tr_yaya = saved["tr_yaya"]
                r_arac_str = saved["r_arac"]
            else:
                dop_inc, dop_durumu, dop_turu = get_default_dop_rule(fonk)
                if not dop_inc or "HARİÇ" in dop_turu.upper() or "HARIC" in norm_tr(dop_turu):
                    combo_idx = 2
                elif "ÖZEL" in dop_turu.upper():
                    combo_idx = 0
                else:
                    combo_idx = 1

                emp_inc, std_m2, eff = get_default_employment_rule(fonk)
                std_m2_str = str(std_m2) if std_m2 > 0 else "50.0"
                eff_str = str(eff) if eff > 0 else "0.50"

                tr_arac, tr_yaya, r_arac, _ = get_default_trip_rule(fonk)
                r_arac_str = str(r_arac) if r_arac > 0 else "1.0"

            # 1-2. DOP Dahil / Hariç ve DOP Türü
            item_dop = QTableWidgetItem("DOP İçi" if dop_inc else "nDOP (Hariç)")
            item_dop.setFlags(item_dop.flags() | _ITEM_USER_CHECKABLE)
            item_dop.setCheckState(_CHECKED if dop_inc else _UNCHECKED)
            item_dop.setToolTip("İşaretli ise Düzenleme Sahasına Dahil (DOP İçi) edilir. İşaretsiz ise Harice Ayrılan (nDOP / DOP Dışı) alandır.")
            self.tbl_rules.setItem(r_idx, 1, item_dop)

            combo_dop = QComboBox()
            combo_dop.addItems([
                "DOP İçi - Özel (Tahsis)",
                "DOP İçi - Kamu (Kesinti)",
                "nDOP - DOP Dışı (Hariç)"
            ])
            combo_dop.setCurrentIndex(combo_idx)
            combo_dop.currentIndexChanged.connect(lambda idx, row=r_idx: self._on_dop_combo_changed(row, idx))
            self.tbl_rules.setCellWidget(r_idx, 2, combo_dop)

            # 3-5. İstihdam varsayılanları
            item_emp = QTableWidgetItem("Dahil" if emp_inc else "Hariç")
            item_emp.setFlags(item_emp.flags() | _ITEM_USER_CHECKABLE)
            item_emp.setCheckState(_CHECKED if emp_inc else _UNCHECKED)
            self.tbl_rules.setItem(r_idx, 3, item_emp)

            item_std = QTableWidgetItem(std_m2_str)
            self.tbl_rules.setItem(r_idx, 4, item_std)

            item_eff = QTableWidgetItem(eff_str)
            self.tbl_rules.setItem(r_idx, 5, item_eff)

            # 6-8. Yolculuk varsayılanları
            item_arac = QTableWidgetItem("Dahil" if tr_arac else "Hariç")
            item_arac.setFlags(item_arac.flags() | _ITEM_USER_CHECKABLE)
            item_arac.setCheckState(_CHECKED if tr_arac else _UNCHECKED)
            self.tbl_rules.setItem(r_idx, 6, item_arac)

            item_yaya = QTableWidgetItem("Dahil" if tr_yaya else "Hariç")
            item_yaya.setFlags(item_yaya.flags() | _ITEM_USER_CHECKABLE)
            item_yaya.setCheckState(_CHECKED if tr_yaya else _UNCHECKED)
            self.tbl_rules.setItem(r_idx, 7, item_yaya)

            item_r_arac = QTableWidgetItem(r_arac_str)
            self.tbl_rules.setItem(r_idx, 8, item_r_arac)

        self.tbl_rules.blockSignals(False)

    def _on_rules_table_item_changed(self, item: QTableWidgetItem):
        """Kullanıcı kurallar tablosunda onay kutusunu değiştirdiğinde ilgili metin ve kontrolleri senkronize eder."""
        col = item.column()
        row = item.row()

        if col == 1:  # DOP İçi (Dahil)?
            is_checked = (item.checkState() == _CHECKED)
            self.tbl_rules.blockSignals(True)
            item.setText("DOP İçi" if is_checked else "nDOP (Hariç)")
            self.tbl_rules.blockSignals(False)

            combo = self.tbl_rules.cellWidget(row, 2)
            if combo and isinstance(combo, QComboBox):
                combo.blockSignals(True)
                if not is_checked:
                    combo.setCurrentIndex(2)  # nDOP - DOP Dışı (Hariç)
                else:
                    if combo.currentIndex() == 2:
                        f_item = self.tbl_rules.item(row, 0)
                        fonk = f_item.text().strip() if f_item else ""
                        _, _, def_turu = get_default_dop_rule(fonk)
                        combo.setCurrentIndex(0 if "ÖZEL" in def_turu.upper() else 1)
                combo.blockSignals(False)

        elif col == 3:  # İstihdam Dahil?
            self.tbl_rules.blockSignals(True)
            item.setText("Dahil" if item.checkState() == _CHECKED else "Hariç")
            self.tbl_rules.blockSignals(False)

        elif col == 6:  # Araç Dahil?
            self.tbl_rules.blockSignals(True)
            item.setText("Dahil" if item.checkState() == _CHECKED else "Hariç")
            self.tbl_rules.blockSignals(False)

        elif col == 7:  # Yaya Dahil?
            self.tbl_rules.blockSignals(True)
            item.setText("Dahil" if item.checkState() == _CHECKED else "Hariç")
            self.tbl_rules.blockSignals(False)

    def _on_dop_combo_changed(self, row: int, index: int):
        """DOP Türü açılır kutusu değiştiğinde DOP İçi (Dahil)? onay kutusunu senkronize eder."""
        item_dop = self.tbl_rules.item(row, 1)
        if not item_dop:
            return
        self.tbl_rules.blockSignals(True)
        if index == 2:  # nDOP - DOP Dışı (Hariç)
            item_dop.setCheckState(_UNCHECKED)
            item_dop.setText("nDOP (Hariç)")
        else:
            item_dop.setCheckState(_CHECKED)
            item_dop.setText("DOP İçi")
        self.tbl_rules.blockSignals(False)

    def _reset_rules_to_defaults(self):
        """Kurallar tablosunu sıfırlayıp katmandan varsayılanlarla yeniden doldurur."""
        self._load_rules_table_from_layer(preserve_custom=False)

    def _get_rules_config(self) -> dict | None:
        """Kullanıcının kurallar tablosundaki seçimlerini dict olarak çıkarır."""
        if not self.box_rules.isChecked() or self.tbl_rules.rowCount() == 0:
            return None

        dop_rules = {}
        emp_rules = {}
        trip_rules = {}

        for r in range(self.tbl_rules.rowCount()):
            f_item = self.tbl_rules.item(r, 0)
            if not f_item:
                continue
            fonk = f_item.text().strip()
            fn = norm_tr(fonk)

            # 1. DOP Kuralı (DOP İçi vs nDOP / Harice Ayrılan)
            dop_item = self.tbl_rules.item(r, 1)
            inc_dop = (dop_item.checkState() == _CHECKED) if dop_item else True
            combo_dop = self.tbl_rules.cellWidget(r, 2)
            if combo_dop and isinstance(combo_dop, QComboBox):
                c_idx = combo_dop.currentIndex()
                if c_idx == 0:
                    dop_durumu_val = "DOP İÇİ"
                    dop_turu_val = "DOP İÇİ - ÖZEL (TAHSİS)"
                elif c_idx == 1:
                    dop_durumu_val = "DOP İÇİ"
                    dop_turu_val = "DOP İÇİ - KAMU (KESİNTİ)"
                else:
                    dop_durumu_val = "DOP DIŞI"
                    dop_turu_val = "DOP DIŞI (HARİÇ)"
                    inc_dop = False
            else:
                dop_durumu_val = "DOP İÇİ" if inc_dop else "DOP DIŞI"
                dop_turu_val = "DOP İÇİ - ÖZEL (TAHSİS)" if inc_dop else "DOP DIŞI (HARİÇ)"

            if not inc_dop:
                dop_durumu_val = "DOP DIŞI"
                dop_turu_val = "DOP DIŞI (HARİÇ)"

            dop_rules[fn] = {
                "include": inc_dop,
                "dop_durumu": dop_durumu_val,
                "dop_turu": dop_turu_val
            }

            # 2. İstihdam Kuralı
            emp_item = self.tbl_rules.item(r, 3)
            inc_emp = (emp_item.checkState() == _CHECKED) if emp_item else True
            try:
                std_m2 = float(self.tbl_rules.item(r, 4).text().strip())
            except (ValueError, AttributeError):
                std_m2 = 50.0
            try:
                eff = float(self.tbl_rules.item(r, 5).text().strip())
            except (ValueError, AttributeError):
                eff = 0.5

            emp_rules[fn] = {"include": inc_emp, "m2_per_worker": std_m2, "eff": eff}

            # 3. Yolculuk Kuralı
            arac_item = self.tbl_rules.item(r, 6)
            yaya_item = self.tbl_rules.item(r, 7)
            inc_arac = (arac_item.checkState() == _CHECKED) if arac_item else True
            inc_yaya = (yaya_item.checkState() == _CHECKED) if yaya_item else True
            try:
                r_arac = float(self.tbl_rules.item(r, 8).text().strip())
            except (ValueError, AttributeError):
                r_arac = 1.0

            trip_rules[fn] = {
                "include_arac": inc_arac,
                "include_yaya": inc_yaya,
                "rate_arac": r_arac,
                "rate_yaya": 2.0
            }

        return {"dop": dop_rules, "employment": emp_rules, "trips": trip_rules}

    def _populate_table(self, tbl: QTableWidget, headers: list[str], rows: list[list]):
        """QTableWidget tablosunu verilen başlık ve satırlarla doldurur."""
        tbl.clear()
        tbl.setColumnCount(len(headers))
        tbl.setRowCount(len(rows))
        tbl.setHorizontalHeaderLabels(headers)
        for r_idx, row in enumerate(rows):
            for c_idx, val in enumerate(row):
                item = QTableWidgetItem(str(val))
                tbl.setItem(r_idx, c_idx, item)
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        tbl.horizontalHeader().setStretchLastSection(True)

    # -----------------------------------------------------------------
    # NİP: kıyaslama ön ayarı, DOP satırları (tek kaynak), analiz
    # -----------------------------------------------------------------
    def _kiyas_referanslari(self) -> dict:
        """Seçili kıyaslama ön ayarının satırları (Tire yalnızca örnek)."""
        key = self.cmb_kiyas_preset.currentData() if hasattr(self, "cmb_kiyas_preset") else "yok"
        if key in (None, "yok"):
            return {}
        try:
            from .core.tire_constants import NUFUS_KIYAS_ONAYARLARI
            return dict(NUFUS_KIYAS_ONAYARLARI.get(key) or {})
        except ImportError:
            from .core.tire_constants import TIRE_POPULATION_BENCHMARKS
            return dict(TIRE_POPULATION_BENCHMARKS) if key == "tire" else {}

    @staticmethod
    def _fmt_pop(value) -> str:
        if isinstance(value, (int, float)):
            return _tr_int(value)
        return str(value)

    def _fill_benchmark_table(self, *_args, kiyaslama: list | None = None):
        """Kıyaslama tablosunu ön ayardan ya da analiz özetindeki 'kiyaslama' listesinden doldurur."""
        if kiyaslama is None:
            kiyaslama = [dict(v) for v in self._kiyas_referanslari().values()]
        self.tbl_benchmark.setRowCount(len(kiyaslama))
        for r, row in enumerate(kiyaslama):
            for c, key in enumerate(("kapsam", "merkez", "ilce")):
                item = QTableWidgetItem(self._fmt_pop(row.get(key, "-")))
                item.setToolTip(str(row.get("kaynak", "")))
                self.tbl_benchmark.setItem(r, c, item)
        key = self.cmb_kiyas_preset.currentData()
        if key == "tire":
            self.lbl_bench_note.setText(
                "📌 Örnek veri: Tire (İzmir) — 1997 planı (1990 DİE), 2015 ve 2025 TÜİK ADNKS. "
                "6360 sayılı yasa sonrası kentsel merkez, yerleşik lekedeki mahallelerin toplamıdır. "
                "Kendi yerleşmeniz için kıyas verisi yoksa “Kıyas verisi yok” seçin.")
        else:
            self.lbl_bench_note.setText("Kıyas için hazır veri seçilmedi; analizden sonra hesaplanan "
                                        "NİP nüfusu burada görünür.")

    @staticmethod
    def _dop_rows(dop: dict) -> list[tuple]:
        """DOP ve kamu-özel dengesi satırları: (parametre, alan_m2, alan_ha, oran_yuzde, açıklama).

        Tablo, katman, CSV ve rapor bu tek listeden yazılır. Plan onama sınırı
        yoksa DOP oranı tahminidir ve öyle adlandırılır.
        """
        p_m2 = dop["toplam_plan_alani_m2"]
        e_m2 = dop["dop_esas_alan_m2"]
        tahmini = bool(dop.get("tahmini"))
        sinir_aciklama = ("Plan Onama Sınırına Göre" if dop.get("sinir_katmani_kullanildi")
                          else "İmar Adaları Toplamı Esas Alındı")
        yol_aciklama = ("Yol alanı TAHMİNİ (sınır yok)" if tahmini else "Plan Sınırı - İmar Adaları Boşluğu")
        rows = [
            ("Plan Onama Sınırı / Toplam Alan", p_m2, dop["toplam_plan_alani_ha"], 100.0, sinir_aciklama),
            ("İmar Adaları (Kullanım Poligonları)", dop["adalar_toplam_m2"], dop["adalar_toplam_ha"],
             round(dop["adalar_toplam_m2"] / max(1, p_m2) * 100.0, 2), "Plan Fonksiyon Blokları"),
            ("Net Yol ve Ulaşım Ağı Alanı", dop["hesaplanan_yol_m2"], dop["hesaplanan_yol_ha"],
             dop["yol_orani_yuzde"], yol_aciklama),
            ("DOP Dışı Alanlar (Harice Ayrılan)", dop["dop_disi_alan_m2"], round(dop["dop_disi_alan_m2"] / 10000.0, 2),
             round(dop["dop_disi_alan_m2"] / max(1, p_m2) * 100.0, 2), "Orman, Tarım, Su, Sit vb."),
            ("Düzenleme Sahası (DOP Esas Alan)", e_m2, round(e_m2 / 10000.0, 2),
             round(e_m2 / max(1, p_m2) * 100.0, 2), "Düzenlemeye Giren Net Saha"),
            ("Toplam Özel Mülkiyet (Tahsis)", dop["toplam_ozel_tahsis_m2"], round(dop["toplam_ozel_tahsis_m2"] / 10000.0, 2),
             round(dop["toplam_ozel_tahsis_m2"] / max(1, e_m2) * 100.0, 2), "Konut, Ticaret, Sanayi vb."),
            ("Kamu Poligon Donatıları", dop["kamu_poligonlar_m2"], round(dop["kamu_poligonlar_m2"] / 10000.0, 2),
             round(dop["kamu_poligonlar_m2"] / max(1, e_m2) * 100.0, 2), "Eğitim, Sağlık, Yeşil vb."),
            ("Toplam Kamu Kesintisi (Donatı + Yol)", dop["toplam_kamu_kesinti_m2"],
             round(dop["toplam_kamu_kesinti_m2"] / 10000.0, 2), dop["dop_orani"], "Donatılar + Yol Ağı"),
            ("Kamu / Özel Mülkiyet Oranı", 0.0, 0.0, dop.get("kamu_ozel_orani", 0.0), "Kamu Kesintisi / Özel Tahsis"),
            ("TAHMİNİ DOP ORANI (%)" if tahmini else "HESAPLANAN DOP ORANI (%)", 0.0, 0.0,
             dop["dop_orani"], dop.get("dop_uygunluk", "")),
        ]
        if dop.get("ortalama_yol_genisligi_m"):
            rows.insert(3, ("Ortalama Fiili Yol Genişliği (m)", 0.0, 0.0, dop["ortalama_yol_genisligi_m"],
                            f"{dop.get('yol_agi_uzunlugu_km', 0)} km Yol Ağı / Yol Alanı"))
        return rows

    def _dop_tone(self, dop: dict) -> str | None:
        """Yasal sınır renklendirmesi: tahminde renk yok (None)."""
        if dop.get("tahmini"):
            return None
        limit = float(dop.get("yasal_sinir", 45.0) or 45.0)
        return "ok" if dop["dop_orani"] <= limit else "bad"

    def _populate_dop_table(self, dop: dict):
        """DOP ve Kamu-Özel Dengesi Tablosunu oluşturur ve biçimlendirir."""
        headers = ["Parametre", "Alan (m²)", "Alan (ha)", "Oran (%)", "Açıklama / Yasal Durum"]
        rows = []
        for name, m2, ha, pct, note in self._dop_rows(dop):
            rows.append([name, f"{m2:,.0f} m²" if m2 else "-", f"{ha:.2f} ha" if ha else "-", f"{pct:.2f} %", note])
        self._populate_table(self.tbl_dop, headers, rows)
        bold_font = QFont()
        bold_font.setBold(True)
        tone = self._dop_tone(dop)
        last_idx = len(rows) - 1
        for col in range(5):
            it = self.tbl_dop.item(last_idx, col)
            if it:
                it.setFont(bold_font)
                if tone:
                    it.setForeground(QColor(self._c[tone]))

    def _populate_kk_table(self, kk_list: list):
        """Kent Karakteri Tablosunu oluşturur."""
        headers = ["Plan Fonksiyonu", "Toplam Alan (m²)", "Alt Nüfus (m²/k)", "Üst Nüfus (m²/k)", "Projeksiyon (m²/k)"]
        rows = []
        for it in kk_list:
            rows.append([
                it["fonksiyon"],
                f"{it['toplam_m2']:,.0f} m²",
                f"{it['alt_nufus_m2_kisi']:.2f} m²/k",
                f"{it['ust_nufus_m2_kisi']:.2f} m²/k",
                f"{it['proj_nufus_m2_kisi']:.2f} m²/k"
            ])
        self._populate_table(self.tbl_kent_karakter, headers, rows)

    def _populate_ek2_table(self, ek2_list: list):
        """MPYY Ek-2 Donatı Dengesi Tablosunu oluşturur."""
        headers = ["Donatı Grubu", "Mevcut Alan", "Ek-2 Std", "Mevcut (Üst Nüfus)", "Durum"]
        rows = []
        for ek in ek2_list:
            rows.append([
                ek["kategori_adi"],
                f"{ek['toplam_m2']:,.0f} m²",
                f"{ek['standart_m2']:.2f} m²/k",
                f"{ek['kb_ust']:.2f} m²/k",
                ek["durum_ust"]
            ])
        self._populate_table(self.tbl_ek2, headers, rows)
        font = QFont()
        font.setBold(True)
        for r_idx, ek in enumerate(ek2_list):
            it = self.tbl_ek2.item(r_idx, 4)
            if it:
                it.setForeground(QColor(self._c["ok"] if ek["durum_ust"] == "YETERLİ" else self._c["bad"]))
                it.setFont(font)

    def _populate_fd_table(self, fd_list: list):
        """Detaylı Fonksiyon Dağılım Tablosunu oluşturur."""
        headers = ["Plan Fonksiyonu", "DOP Durumu", "Alan Türü", "Adet", "Alan (ha)", "Kişi Başı (m²)", "Plan Payı (%)"]
        rows = []
        for fd in fd_list:
            rows.append([
                fd["fonksiyon"],
                fd["dop_durumu"],
                fd["dop_turu"],
                str(fd["adet"]),
                f"{fd['alan_ha']:.2f} ha",
                f"{fd['kisi_basi_m2']:.2f} m²/k",
                f"% {fd['tum_plan_yuzdesi']:.2f}"
            ])
        self._populate_table(self.tbl_fonk_dagilim, headers, rows)

    def _run_nip_analysis(self):
        layer = self.cmb_nip_layer.currentLayer()
        fonk_col = self.cmb_fonk_field.currentText()
        proj_nufus = self.spn_proj_nufus.value()

        sec_col_text = self.cmb_secondary_fonk_field.currentText() if hasattr(self, 'cmb_secondary_fonk_field') else ""
        secondary_fonk_col = sec_col_text if sec_col_text and not sec_col_text.startswith("<") else None

        mode_idx = self.cmb_analysis_mode.currentIndex() if hasattr(self, 'cmb_analysis_mode') else 0
        analysis_mode = "TUCBS" if mode_idx == 1 else "NIP"
        mode_title = "Fiziki Mevcut Durum (TUCBS)" if analysis_mode == "TUCBS" else "1/5000 NİP"

        if not layer or not isinstance(layer, QgsVectorLayer):
            QMessageBox.warning(self, "Uyarı", "Lütfen bir analiz katmanı seçin!")
            return
        if not fonk_col:
            QMessageBox.warning(self, "Uyarı", "Lütfen birincil fonksiyon veya TUCBS sütununu seçin!")
            return

        self.btn_run_nip.setEnabled(False)
        self.txt_nip_results.clear()
        self.txt_nip_results.append(f"<i>{mode_title} Analizi hesaplanıyor, lütfen bekleyiniz...</i>")

        try:
            project = QgsProject.instance()
            context = project.transformContext()
            # Alan ve uzunluklar her zaman elipsoit üzerinde ölçülür (proje elipsoidi 'NONE' olsa da).
            da, _ellipsoid, _fixed = build_distance_area(layer.crs(), context, project.ellipsoid())

            # Plan onama sınırı ve yol aksları ada katmanının KRS'sine dönüştürülür.
            sinir_layer = self.cmb_sinir_layer.currentLayer()
            yol_layer = self.cmb_yol_layer.currentLayer()
            sinir_geom, yol_uzunlugu_m, input_warnings = prepare_boundary_and_roads(
                layer.crs(), context, da,
                sinir_layer=sinir_layer if isinstance(sinir_layer, QgsVectorLayer) else None,
                yol_layer=yol_layer if isinstance(yol_layer, QgsVectorLayer) else None,
            )

            sinir_modu = "clip"
            if hasattr(self, 'cmb_sinir_modu'):
                cur_data = self.cmb_sinir_modu.currentData()
                if cur_data:
                    sinir_modu = str(cur_data)

            rules_config = self._get_rules_config()

            # Otomatik duplike kontrolü ve geometri temizliği
            feats, clean_stats = GeometryCleanerEngine.clean_layer(layer)
            if clean_stats["duplike_elenen"] > 0:
                self.txt_nip_results.append(
                    f"<p style='color:{self._c['warn']};'>ℹ️ <i>Katmanda tespit edilen <b>{clean_stats['duplike_elenen']:,} adet mükerrer poligon</b> otomatik olarak ayıklandı; hesaplama <b>{clean_stats['temiz_cikan']:,} tekil ada</b> üzerinden yapıldı.</i></p>"
                )

            calc_kwargs = dict(
                sinir_geom=sinir_geom,
                sinir_modu=sinir_modu,
                yol_uzunlugu_m=yol_uzunlugu_m,
                rules_config=rules_config,
                secondary_fonk_col=secondary_fonk_col,
                analysis_mode=analysis_mode,
            )
            accepted = inspect.signature(NipCalculatorEngine.calculate).parameters
            if "kirsal_nufus" in accepted:
                calc_kwargs["kirsal_nufus"] = self.spn_kirsal_nufus.value()
            if "kiyas_referanslari" in accepted:
                calc_kwargs["kiyas_referanslari"] = self._kiyas_referanslari()
            parsed_items, summary = NipCalculatorEngine.calculate(
                feats, layer.fields(), fonk_col, proj_nufus, da, **calc_kwargs)
            warnings = list(input_warnings) + [str(w) for w in summary.get("uyarilar", [])]

            # 4. Ana Poligon Analiz Katmanı
            uri = f"MultiPolygon?crs={layer.crs().authid()}"
            out_layer = QgsVectorLayer(uri, f"{layer.name()}_{analysis_mode}_ANALIZ", "memory")
            out_prov = out_layer.dataProvider()

            out_fields = QgsFields(layer.fields())
            out_fields.append(QgsField('AlanHa', QVariant.Double))
            out_fields.append(QgsField('ALT_SNR', QVariant.Double))
            out_fields.append(QgsField('UST_SNR', QVariant.Double))
            out_fields.append(QgsField('ALT_NUFUS', QVariant.Double))
            out_fields.append(QgsField('UST_NUFUS', QVariant.Double))
            out_fields.append(QgsField('k_m2_ALT_NUFUS', QVariant.Double))
            out_fields.append(QgsField('k_m2_UST_NUFUS', QVariant.Double))
            out_fields.append(QgsField('T_ISTIHDAM', QVariant.Int))
            out_fields.append(QgsField('GUNLUK_ARAC', QVariant.Double))
            out_fields.append(QgsField('GUNLUK_YAYA', QVariant.Double))
            out_fields.append(QgsField('DOP_DURUMU', QVariant.String))
            out_fields.append(QgsField('DOP_TURU', QVariant.String))
            out_fields.append(QgsField('DONATI_KATEGORI', QVariant.String))

            out_prov.addAttributes(out_fields)
            out_layer.updateFields()

            new_feats = []
            for it in parsed_items:
                feat = it["feat"]
                nf = QgsFeature(out_fields)
                nf.setGeometry(it["geom"])
                attrs = feat.attributes()
                attrs.extend([
                    round(it["alan_ha"], 4),
                    it["alt_snr"] if it["alt_snr"] is not None else 0.0,
                    it["ust_snr"] if it["ust_snr"] is not None else 0.0,
                    it["alt_nufus"],
                    it["ust_nufus"],
                    it["km2_alt_nufus"] if it["km2_alt_nufus"] is not None else NULL,
                    it["km2_ust_nufus"] if it["km2_ust_nufus"] is not None else NULL,
                    it["istihdam"],
                    it["gunluk_arac"],
                    it["gunluk_yaya"],
                    it["dop_durumu"],
                    it["dop_turu"],
                    it["donati_kategori"] or ""
                ])
                nf.setAttributes(attrs)
                new_feats.append(nf)

            out_prov.addFeatures(new_feats)
            out_layer.updateExtents()
            self._apply_nip_styling(out_layer)

            # 5. DOP ve Kamu-Özel Dengesi Tablosu Katmanı (NoGeometry)
            tbl_dop_layer = QgsVectorLayer("None", f"PLN3113_{analysis_mode}_2_DOP_ve_Kamu_Ozel_Dengesi", "memory")
            tbl_dop_pr = tbl_dop_layer.dataProvider()
            tbl_dop_pr.addAttributes([
                QgsField('parametre', QVariant.String),
                QgsField('alan_m2', QVariant.Double),
                QgsField('alan_ha', QVariant.Double),
                QgsField('oran_yuzde', QVariant.Double),
                QgsField('aciklama', QVariant.String)
            ])
            tbl_dop_layer.updateFields()

            dop = summary["dop_ozet"]
            dop_rows = self._dop_rows(dop)
            dop_feats = []
            for r in dop_rows:
                df = QgsFeature(tbl_dop_layer.fields())
                df.setAttributes(list(r))
                dop_feats.append(df)
            tbl_dop_pr.addFeatures(dop_feats)

            # 6. Kent Karakteri Tablosu Katmanı (NoGeometry)
            tbl_kk_layer = QgsVectorLayer("None", f"PLN3113_{analysis_mode}_3_Kent_Karakter_Tablosu", "memory")
            tbl_kk_pr = tbl_kk_layer.dataProvider()
            tbl_kk_pr.addAttributes([
                QgsField('nip_fonksiyon', QVariant.String),
                QgsField('toplam_m2', QVariant.Double),
                QgsField('alt_nufus_m2_kisi', QVariant.Double),
                QgsField('ust_nufus_m2_kisi', QVariant.Double),
                QgsField('proj_nufus_m2_kisi', QVariant.Double)
            ])
            tbl_kk_layer.updateFields()
            kk_feats = []
            for kk in summary["kent_karakter"]:
                kf = QgsFeature(tbl_kk_layer.fields())
                kf.setAttributes([kk["fonksiyon"], kk["toplam_m2"], kk["alt_nufus_m2_kisi"], kk["ust_nufus_m2_kisi"], kk["proj_nufus_m2_kisi"]])
                kk_feats.append(kf)
            tbl_kk_pr.addFeatures(kk_feats)

            # 7. MPYY Ek-2 Donatı Tablosu Katmanı (NoGeometry)
            tbl_ek2_layer = QgsVectorLayer("None", f"PLN3113_{analysis_mode}_4_Ek2_Donati_Dengesi", "memory")
            tbl_ek2_pr = tbl_ek2_layer.dataProvider()
            tbl_ek2_pr.addAttributes([
                QgsField('donati_turu', QVariant.String),
                QgsField('toplam_m2', QVariant.Double),
                QgsField('mpyy_standart_m2', QVariant.Double),
                QgsField('mevcut_m2_alt_nufus', QVariant.Double),
                QgsField('mevcut_m2_ust_nufus', QVariant.Double),
                QgsField('durum_ust_nufus', QVariant.String)
            ])
            tbl_ek2_layer.updateFields()
            ek2_feats = []
            for ek in summary["ek2_rapor"]:
                ef = QgsFeature(tbl_ek2_layer.fields())
                ef.setAttributes([ek["kategori_adi"], ek["toplam_m2"], ek["standart_m2"], ek["kb_alt"], ek["kb_ust"], ek["durum_ust"]])
                ek2_feats.append(ef)
            tbl_ek2_pr.addFeatures(ek2_feats)

            # 8. Detaylı Fonksiyon Dağılım Tablosu Katmanı (NoGeometry)
            tbl_fd_layer = QgsVectorLayer("None", f"PLN3113_{analysis_mode}_5_Fonksiyon_Dagilim_Tablosu", "memory")
            tbl_fd_pr = tbl_fd_layer.dataProvider()
            tbl_fd_pr.addAttributes([
                QgsField('nip_fonksiyon', QVariant.String),
                QgsField('dop_durumu', QVariant.String),
                QgsField('alan_turu', QVariant.String),
                QgsField('adet', QVariant.Int),
                QgsField('alan_m2', QVariant.Double),
                QgsField('alan_ha', QVariant.Double),
                QgsField('kisi_basi_m2', QVariant.Double),
                QgsField('tum_plan_yuzdesi', QVariant.Double),
                QgsField('dop_ici_yuzde', QVariant.Double)
            ])
            tbl_fd_layer.updateFields()
            fd_feats = []
            for fd in summary["fonksiyon_dagilim"]:
                ff = QgsFeature(tbl_fd_layer.fields())
                ff.setAttributes([
                    fd["fonksiyon"], fd["dop_durumu"], fd["dop_turu"], fd["adet"],
                    fd["alan_m2"], fd["alan_ha"], fd["kisi_basi_m2"], fd["tum_plan_yuzdesi"], fd["dop_ici_yuzde"]
                ])
                fd_feats.append(ff)
            tbl_fd_pr.addFeatures(fd_feats)

            # Katmanları QGIS Projesinde Düzenli Bir Gruba Ekle
            root = project.layerTreeRoot()
            grp_name = f"PLN3113 {mode_title} Analiz Çıktıları ({layer.name()})"
            grp = root.findGroup(grp_name)
            if not grp:
                grp = root.insertGroup(0, grp_name)

            for lyr in [out_layer, tbl_dop_layer, tbl_kk_layer, tbl_ek2_layer, tbl_fd_layer]:
                project.addMapLayer(lyr, False)
                grp.addLayer(lyr)

            # DockWidget Tablolarını Doldur
            self._populate_dop_table(dop)
            self._populate_kk_table(summary["kent_karakter"])
            self._populate_ek2_table(summary["ek2_rapor"])
            self._populate_fd_table(summary["fonksiyon_dagilim"])

            alt_str = _tr_int(summary['toplam_alt_nufus'])
            ust_str = _tr_int(summary['toplam_ust_nufus'])

            # Kıyaslama tablosu: özetteki liste (ön ayar + hesaplanan satır) ya da yerel satır
            kiyaslama = summary.get("kiyaslama")
            if kiyaslama is None:
                kiyaslama = [dict(v) for v in self._kiyas_referanslari().values()]
                kiyaslama.append({"kapsam": f"Hesaplanan {mode_title} Nüfusu",
                                  "merkez": f"{alt_str} - {ust_str}", "ilce": "-", "kaynak": "PLN3113 NİP Analiz Modeli"})
            self._fill_benchmark_table(kiyaslama=kiyaslama)

            self._last_nip_html = self._nip_report_html(summary, dop_rows, mode_title, warnings)
            self.txt_nip_results.setHtml(self._last_nip_html)

            # Durumu Sakla ve Dışa Aktarmayı Etkinleştir
            self._last_nip_summary = summary
            self._last_nip_items = parsed_items
            self._last_nip_sinir_geom = sinir_geom
            self._last_nip_crs = layer.crs()
            self._last_nip_out_layer = out_layer
            self.btn_export_csv.setEnabled(True)
            self.btn_export_html.setEnabled(True)
            self.btn_open_dashboard.setEnabled(True)
            self.btn_style_density.setEnabled(True)
            self.btn_style_mpyy.setEnabled(True)

            # Canlı Görsel Göstergeleri Güncelle
            dop_val = dop.get('dop_orani', 0.0)
            limit = float(dop.get("yasal_sinir", 45.0) or 45.0)
            self.bar_dop.setValue(min(80, max(0, int(round(dop_val)))))
            tone = self._dop_tone(dop)
            if tone is None:
                self.bar_dop.setStyleSheet(chunk_css("subtle"))
                self.lbl_dop_badge.setText(f"%{dop_val:.2f} TAHMİNİ")
                self.lbl_dop_badge.setToolTip("Plan onama sınırı verilmedi: yol alanı tahmin edildi, "
                                              "yasal sınır değerlendirmesi yapılmadı.")
                self.lbl_dop_badge.setStyleSheet(chip_css())
            elif tone == "ok":
                self.bar_dop.setStyleSheet(chunk_css("ok"))
                self.lbl_dop_badge.setText(f"%{dop_val:.2f} YASAL UYGUN")
                self.lbl_dop_badge.setToolTip("")
                self.lbl_dop_badge.setStyleSheet(chip_css("ok"))
            else:
                self.bar_dop.setStyleSheet(chunk_css("bad"))
                self.lbl_dop_badge.setText(f"%{dop_val:.2f} AŞIM (+%{dop_val - limit:.2f})")
                self.lbl_dop_badge.setToolTip("")
                self.lbl_dop_badge.setStyleSheet(chip_css("bad"))

            toplam_kamu_donati_m2 = dop.get("kamu_poligonlar_m2", 0.0)
            yesil_alan_m2 = sum(it.get("alan_m2", 0.0) for it in parsed_items if any(k in it.get("fonk_raw", "").upper() for k in ["PARK", "YEŞİL", "YESIL", "ÇOCUK", "COCUK", "MEYDAN", "REKREASYON", "SPOR"]) and it.get("dop_durumu") == "DOP İÇİ")
            acik_yesil_pct = round((yesil_alan_m2 / max(1.0, toplam_kamu_donati_m2)) * 100.0, 1)
            self.bar_yesil.setValue(min(100, max(0, int(round(acik_yesil_pct)))))
            if acik_yesil_pct >= 75.0:
                self.bar_yesil.setStyleSheet(chunk_css("ok"))
                self.lbl_yesil_badge.setText(f"%{acik_yesil_pct:.1f} YETERLİ")
                self.lbl_yesil_badge.setStyleSheet(chip_css("ok"))
            else:
                self.bar_yesil.setStyleSheet(chunk_css("warn"))
                self.lbl_yesil_badge.setText(f"%{acik_yesil_pct:.1f} EKSİK")
                self.lbl_yesil_badge.setStyleSheet(chip_css("warn"))

            dop_name = "Tahmini DOP Oranı" if dop.get("tahmini") else "Hesaplanan DOP Oranı"
            warn_text = ("\n\nUyarılar:\n• " + "\n• ".join(warnings)) if warnings else ""
            QMessageBox.information(
                self, f"{mode_title} Analizi Tamamlandı",
                f"Hesaplanan {mode_title} Nüfusu:\nAlt Sınır: {alt_str} Kişi\nÜst Sınır: {ust_str} Kişi\n\n"
                f"{dop_name}: %{dop['dop_orani']:.2f} ({dop.get('dop_uygunluk', '')})\n"
                f"Net Yol Ağı Alanı: {dop['hesaplanan_yol_ha']:.2f} ha (%{dop['yol_orani_yuzde']:.2f})\n\n"
                f"Analiz katmanı ve 4 adet detaylı tablo (DOP, Kent Karakteri, Ek-2 ve Fonksiyon Dağılımı) "
                f"harita projenize 'PLN3113 {mode_title} Analiz Çıktıları' grubu altında eklendi.{warn_text}"
            )

        except Exception as e:
            QMessageBox.critical(self, "Hata", f"NİP Analizi sırasında hata: {str(e)}")
            self.txt_nip_results.append(f"<span style='color:{self._c['bad']};'>Hata: {html.escape(str(e))}</span>")
        finally:
            self.btn_run_nip.setEnabled(True)

    def _nip_report_html(self, summary: dict, dop_rows: list, mode_title: str, warnings: list) -> str:
        """Dock içindeki ayrıntılı rapor (tema renkleriyle; metinler kaçışlanır)."""
        c = self._c
        esc = html.escape
        dop = summary["dop_ozet"]
        alt_str, ust_str = _tr_int(summary['toplam_alt_nufus']), _tr_int(summary['toplam_ust_nufus'])
        head = f"background:{c['primary']}; color:{c['on_accent']};"
        out = [f"<h3>🏙️ {esc(mode_title.upper())} ANALİZ VE KAPASİTE RAPORU</h3>"]

        if warnings:
            items = "".join(f"<li>{esc(str(w))}</li>" for w in warnings)
            out.append(f"<h4>⚠️ Uyarılar</h4><div style='color:{c['warn']};'><ul>{items}</ul></div>")
        elenen = summary.get("elenen_ada") or {}
        elenen_labels = {"bos_geometri": "boş/geçersiz geometri", "sifir_alan": "sıfır alan",
                         "sinir_disi": "sınır dışı", "fonksiyonu_bos": "fonksiyonu boş (NULL)"}
        elenen_parts = [f"{n} ada {elenen_labels.get(k, k)}" for k, n in elenen.items() if n]
        if elenen_parts:
            out.append(f"<p style='color:{c['warn']};'><b>Hesap dışı kalan / eksik veri:</b> {esc(', '.join(elenen_parts))}</p>")

        out.append("<h4>0. 👥 Nüfus Kıyaslaması</h4>")
        out.append(f"<table border='1' cellpadding='4' style='border-collapse:collapse; width:100%;'>"
                   f"<tr style='{head}'><th>Kapsam</th><th>Kentsel Merkez</th><th>İlçe Toplamı</th></tr>")
        kiyaslama = summary.get("kiyaslama") or [{"kapsam": f"Hesaplanan {mode_title} Nüfusu",
                                                   "merkez": f"{alt_str} - {ust_str}", "ilce": "-"}]
        for row in kiyaslama:
            out.append(f"<tr><td>{esc(str(row.get('kapsam', '')))}</td><td>{esc(self._fmt_pop(row.get('merkez', '-')))}</td>"
                       f"<td>{esc(self._fmt_pop(row.get('ilce', '-')))}</td></tr>")
        out.append("</table>")
        out.append(f"<p>Hedef (projeksiyon) nüfusu: <b>{_tr_int(summary.get('projeksiyon_nufus', 0))} kişi</b></p>")

        s_stats = summary.get("sinir_filtre_ozet")
        if s_stats and s_stats.get("aktif"):
            mod_names = {
                "clip": "Sınırla Kırp / Kes (Sınır Dışını At, Net İç Alanı Al)",
                "intersect": "Sınıra Değenleri Dahil Et (Bütünsel Korunur)",
                "within": "Sınırı Aşanları Hariç Tut (Yalnızca Tamamı İçte Olanlar)",
                "centroid": "Ağırlık Merkezine Göre (Merkezi İçte Olanlar)"
            }
            elenen_tone = c["bad"] if s_stats.get('sinir_disi_elenen', 0) > 0 else c["ok"]
            out.append(
                f"<h4>🌐 Plan Onama Sınırı Kapsamı</h4><p>"
                f"<b>Mod:</b> {esc(str(mod_names.get(s_stats.get('mod'), s_stats.get('mod'))))}<br>"
                f"• Toplam girdi ada: {s_stats.get('toplam_girdi_ada', 0)}<br>"
                f"• Hesaplamaya alınan: {s_stats.get('islenen_ada_sayisi', 0)}<br>"
                f"• Tamamı sınır içinde: {s_stats.get('tamamen_icinde', 0)}<br>"
                f"• Sınırı kesen / işlenen: {s_stats.get('kesisen_islenen', 0)}<br>"
                f"• Sınır dışında elenen: <b style='color:{elenen_tone};'>{s_stats.get('sinir_disi_elenen', 0)} ada</b></p>")

        out.append(f"<h4>1. Genel Nüfus, Alan ve Ulaşım Göstergeleri</h4>"
                   f"<table border='1' cellpadding='4' style='border-collapse:collapse; width:100%;'>"
                   f"<tr style='{head}'><th>Metrik</th><th>Alt Sınır</th><th>Üst Sınır</th></tr>"
                   f"<tr><td><b>Toplam Plan Nüfusu</b></td><td><b>{alt_str} Kişi</b></td><td><b>{ust_str} Kişi</b></td></tr>"
                   f"<tr><td><b>Toplam Konut & Karma Alanı</b></td><td colspan='2'>{summary['toplam_konut_alani_ha']:.2f} ha</td></tr>"
                   f"<tr><td><b>Tahmini İstihdam</b></td><td colspan='2'>{summary['toplam_istihdam']:,} çalışan</td></tr>"
                   f"<tr><td><b>Günlük Araç Yolculuğu</b></td><td colspan='2'>{summary['toplam_gunluk_arac']:,} araç</td></tr>"
                   f"<tr><td><b>Günlük Yaya Yolculuğu</b></td><td colspan='2'>{summary['toplam_gunluk_yaya']:,} yaya</td></tr>"
                   f"</table>")

        tone = self._dop_tone(dop)
        verdict_style = f"color:{c[tone]}; font-weight:bold;" if tone else "font-weight:bold;"
        out.append(f"<h4>2. ⚖️ Kamu - Özel Mülkiyet Dengesi ve DOP</h4>"
                   f"<table border='1' cellpadding='4' style='border-collapse:collapse; width:100%;'>"
                   f"<tr style='{head}'><th>Parametre</th><th>Alan (m²)</th><th>Alan (ha)</th><th>Oran (%)</th><th>Açıklama</th></tr>")
        for i, (name, m2, ha, pct, note) in enumerate(dop_rows):
            last = i == len(dop_rows) - 1
            style = f" style='{verdict_style}'" if last else ""
            out.append(f"<tr><td><b>{esc(name)}</b></td><td>{(f'{m2:,.0f}' if m2 else '-')}</td>"
                       f"<td>{(f'{ha:.2f}' if ha else '-')}</td><td{style}>{pct:.2f}</td><td{style}>{esc(str(note))}</td></tr>")
        out.append("</table>")

        out.append(f"<h4>3. 📋 MPYY Ek-2 Donatı Yeterliliği</h4>"
                   f"<table border='1' cellpadding='3' style='border-collapse:collapse; width:100%;'>"
                   f"<tr style='{head}'><th>Donatı Grubu</th><th>Mevcut Alan</th><th>Ek-2 Std</th><th>Üst Nüfusa Göre</th><th>Durum</th></tr>")
        for ek in summary["ek2_rapor"]:
            durum_color = c["ok"] if ek["durum_ust"] == "YETERLİ" else c["bad"]
            out.append(f"<tr><td>{esc(str(ek['kategori_adi']))}</td><td>{ek['toplam_m2']:,.0f} m²</td>"
                       f"<td>{ek['standart_m2']} m²/k</td><td>{ek['kb_ust']:.2f} m²/k</td>"
                       f"<td style='color:{durum_color}; font-weight:bold;'>{esc(str(ek['durum_ust']))}</td></tr>")
        out.append("</table>")
        return "\n".join(out)

    def _export_nip_tables_csv(self):
        """Tüm hesaplanan analiz tablolarını UTF-8-BOM formatında CSV olarak dışa aktarır."""
        if not self._last_nip_summary:
            QMessageBox.warning(self, "Uyarı", "Lütfen önce NİP analizini çalıştırın!")
            return

        folder = QFileDialog.getExistingDirectory(self, "Tabloların Kaydedileceği Klasörü Seçin")
        if not folder:
            return

        summary = self._last_nip_summary
        dop = summary["dop_ozet"]

        try:
            # 1. DOP CSV
            dop_csv = os.path.join(folder, "pln3113_nip_dop_kamu_ozel_dengesi.csv")
            with open(dop_csv, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["Parametre", "Alan (m²)", "Alan (ha)", "Oran (%)", "Açıklama / Değerlendirme"])
                w.writerows([list(r) for r in self._dop_rows(dop)])
                for warning in summary.get("uyarilar", []):
                    w.writerow(["UYARI", "", "", "", warning])

            # 2. Kent Karakteri CSV
            kk_csv = os.path.join(folder, "pln3113_nip_kent_karakter_tablosu.csv")
            with open(kk_csv, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["Plan Fonksiyonu", "Toplam Alan (m²)", "Alt Nüfus Kişi Başı (m²)", "Üst Nüfus Kişi Başı (m²)", "Projeksiyon Kişi Başı (m²)"])
                for kk in summary["kent_karakter"]:
                    w.writerow([kk["fonksiyon"], kk["toplam_m2"], kk["alt_nufus_m2_kisi"], kk["ust_nufus_m2_kisi"], kk["proj_nufus_m2_kisi"]])

            # 3. MPYY Ek-2 CSV
            ek2_csv = os.path.join(folder, "pln3113_nip_mpyy_ek2_donati_dengesi.csv")
            with open(ek2_csv, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["Donatı Grubu", "Mevcut Alan (m²)", "Ek-2 Standart (m²/k)", "Mevcut Alt Nüfus (m²/k)", "Mevcut Üst Nüfus (m²/k)", "Durum (Üst Nüfus)"])
                for ek in summary["ek2_rapor"]:
                    w.writerow([ek["kategori_adi"], ek["toplam_m2"], ek["standart_m2"], ek["kb_alt"], ek["kb_ust"], ek["durum_ust"]])

            # 4. Fonksiyon Dağılımı CSV
            fd_csv = os.path.join(folder, "pln3113_nip_fonksiyon_dagilimi.csv")
            with open(fd_csv, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["Fonksiyon", "DOP Durumu", "Alan Türü", "Poligon Adedi", "Alan (m²)", "Alan (ha)", "Kişi Başı (m²)", "Plan Payı (%)", "DOP İçi Payı (%)"])
                for fd in summary["fonksiyon_dagilim"]:
                    w.writerow([fd["fonksiyon"], fd["dop_durumu"], fd["dop_turu"], fd["adet"], fd["alan_m2"], fd["alan_ha"], fd["kisi_basi_m2"], fd["tum_plan_yuzdesi"], fd["dop_ici_yuzde"]])

            QMessageBox.information(
                self, "Başarılı",
                f"Tüm analiz tabloları CSV (Excel uyumlu UTF-8) formatında kaydedildi:\n\n{folder}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"CSV dışa aktarım hatası: {str(e)}")

    def _open_nip_dashboard(self):
        """İnteraktif Plotly + Leaflet NİP & DOP Dashboard raporunu tarayıcıda açar."""
        if not self._last_nip_summary or not hasattr(self, "_last_nip_items"):
            QMessageBox.warning(self, "Uyarı", "Lütfen önce NİP analizini çalıştırın!")
            return

        try:
            open_nip_dashboard(
                self._last_nip_summary,
                self._last_nip_items,
                sinir_geom=self._last_nip_sinir_geom,
                crs=self._last_nip_crs,
                ideal_dop=45.0
            )
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Dashboard açılırken hata:\n{str(e)}")

    def _export_nip_report_html(self):
        """İnteraktif Plotly + Leaflet NİP & DOP Dashboard raporunu HTML dosyası olarak kaydeder."""
        if not self._last_nip_summary or not hasattr(self, "_last_nip_items"):
            QMessageBox.warning(self, "Uyarı", "Lütfen önce NİP analizini çalıştırın!")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "İnteraktif NİP & DOP Dashboard Raporunu Kaydet",
            "pln3113_nip_dashboard.html", "HTML Dosyaları (*.html)"
        )
        if not file_path:
            return

        if not file_path.lower().endswith(".html"):
            file_path += ".html"

        try:
            html_content = build_nip_dashboard_html(
                self._last_nip_summary,
                self._last_nip_items,
                sinir_geom=self._last_nip_sinir_geom,
                crs=self._last_nip_crs,
                ideal_dop=45.0
            )
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            reply = QMessageBox.question(
                self, "Rapor Kaydedildi",
                f"İnteraktif NİP & DOP Dashboard raporu başarıyla kaydedildi:\n{file_path}\n\n"
                f"Raporu şimdi varsayılan tarayıcınızda açmak ister misiniz?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                QDesktopServices.openUrl(QUrl.fromLocalFile(file_path))
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"HTML Dashboard kaydedilirken hata: {str(e)}")

    def _apply_nip_styling(self, layer: QgsVectorLayer):
        """UST_SNR yoğunluk değerlerine göre katmana şık bir graduated semboloji atar."""
        ranges = [
            QgsRendererRange(0, 0, QgsFillSymbol.createSimple({'color': '#94a3b8', 'outline_color': '#64748b'}), "Donatı / Çalışma"),
            QgsRendererRange(1, 50, QgsFillSymbol.createSimple({'color': '#fef08a', 'outline_color': '#ca8a04'}), "Seyrek Konut (25-50 k/ha)"),
            QgsRendererRange(51, 150, QgsFillSymbol.createSimple({'color': '#fde047', 'outline_color': '#ca8a04'}), "Düşük Konut (51-150 k/ha)"),
            QgsRendererRange(151, 300, QgsFillSymbol.createSimple({'color': '#fb923c', 'outline_color': '#ea580c'}), "Orta Konut (151-300 k/ha)"),
            QgsRendererRange(301, 600, QgsFillSymbol.createSimple({'color': '#f87171', 'outline_color': '#dc2626'}), "Yüksek Konut (301-600 k/ha)"),
            QgsRendererRange(601, 1200, QgsFillSymbol.createSimple({'color': '#b91c1c', 'outline_color': '#7f1d1d'}), "Çok Yüksek (601-900 k/ha)")
        ]
        renderer = QgsGraduatedSymbolRenderer("UST_SNR", ranges)
        layer.setRenderer(renderer)
        layer.triggerRepaint()

    def _apply_density_style_nip(self):
        """Hesaplanan son NİP katmanına nüfus yoğunluğu (UST_SNR) kademeli stilini uygular."""
        if hasattr(self, "_last_nip_out_layer") and self._last_nip_out_layer:
            self._apply_nip_styling(self._last_nip_out_layer)
            if self.iface and hasattr(self.iface, "layerTreeView") and self.iface.layerTreeView():
                self.iface.layerTreeView().refreshLayerSymbology(self._last_nip_out_layer.id())

    def _apply_mpyy_style_nip(self):
        """Hesaplanan son NİP katmanına resmî MPYY alanlar-5000 QML lejant stilini uygular."""
        if hasattr(self, "_last_nip_out_layer") and self._last_nip_out_layer:
            apply_mpyy_qml_style(self._last_nip_out_layer, "alanlar-5000.qml")
            if self.iface and hasattr(self.iface, "layerTreeView") and self.iface.layerTreeView():
                self.iface.layerTreeView().refreshLayerSymbology(self._last_nip_out_layer.id())


    # -----------------------------------------------------------------
    # SEKME 3: SAHA & BİNA BAZLI FİİLİ NÜFUS
    # -----------------------------------------------------------------
    def _create_tab_field(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Bilgi Barı
        info_banner = QFrame()
        info_banner.setStyleSheet(note_css("warn"))
        info_l = QVBoxLayout(info_banner)
        info_l.setContentsMargins(6, 4, 6, 4)
        lbl_hint = QLabel("💡 <b>Fiili Nüfus Metodolojisi:</b> Bina kat, taban alanı, TÜİK hanehalkı ve fiili istihdam hesabı.")
        lbl_hint.setStyleSheet(f"color: {self._c['warn']}; background: transparent; border: none;")
        btn_hint_guide = QPushButton("📖 Rehberde İncele")
        btn_hint_guide.setCursor(_POINTING_HAND)
        btn_hint_guide.clicked.connect(self._open_theoretical_guide)
        info_l.addWidget(lbl_hint)
        info_l.addWidget(btn_hint_guide)
        layout.addWidget(info_banner)

        box_field = QGroupBox("Mevcut Durum Katmanları")
        f_layout = QFormLayout(box_field)

        self.cmb_ada_layer = QgsMapLayerComboBox()
        self.cmb_ada_layer.setFilters(QgsMapLayerProxyModel.Filter.PolygonLayer)
        f_layout.addRow("Kadastro / saha adaları:", self.cmb_ada_layer)

        self.cmb_bina_layer = QgsMapLayerComboBox()
        self.cmb_bina_layer.setFilters(QgsMapLayerProxyModel.Filter.PolygonLayer)
        f_layout.addRow("Bina katmanı:", self.cmb_bina_layer)

        self.spn_hh = QDoubleSpinBox()
        self.spn_hh.setRange(1.0, 8.0)
        self.spn_hh.setValue(2.85)
        self.spn_hh.setSingleStep(0.05)
        f_layout.addRow("Ort. hanehalkı büyüklüğü:", self.spn_hh)

        self.spn_daire_m2 = QDoubleSpinBox()
        self.spn_daire_m2.setRange(40.0, 300.0)
        self.spn_daire_m2.setValue(110.0)
        self.spn_daire_m2.setSuffix(" m²")
        f_layout.addRow("Ortalama Daire Alanı:", self.spn_daire_m2)

        self.spn_net_oran = QDoubleSpinBox()
        self.spn_net_oran.setRange(0.5, 1.0)
        self.spn_net_oran.setValue(0.85)
        self.spn_net_oran.setSingleStep(0.05)
        f_layout.addRow("İnşaat Net Alan Oranı:", self.spn_net_oran)

        layout.addWidget(box_field)

        lbl_kural = QLabel(
            "<b>Planlama İlkesi Koruması:</b><br>"
            "Sanayi, OSB, depo, mezarlık, saf ticaret ve park alanlarında yaşayan nüfus kesinlikle <b>0</b> atanır. "
            "Yalnızca Konut ve Karma Kullanım (TİCK) alanlarında yaşayan nüfus toplanır."
        )
        lbl_kural.setWordWrap(True)
        lbl_kural.setStyleSheet(note_css("info"))
        layout.addWidget(lbl_kural)

        self.btn_run_field = QPushButton("Fiili Nüfusu Hesapla")
        self.btn_run_field.setToolTip("Saha ve bina bazlı fiili nüfus ve morfolojiyi hesapla")
        self.btn_run_field.setObjectName("FieldButton")
        field_icon_path = os.path.join(PLUGIN_DIR, "icons", "field.png")
        if os.path.exists(field_icon_path):
            self.btn_run_field.setIcon(QIcon(field_icon_path))
        self.btn_run_field.clicked.connect(self._run_field_analysis)
        layout.addWidget(self.btn_run_field)

        self.field_progress = QProgressBar()
        self.field_progress.setVisible(False)
        layout.addWidget(self.field_progress)

        # 1-Tıkla Tematik Harita ve Morfoloji Görselleştirme Kutusu
        self.box_field_styles = QGroupBox("🎨 Tematik Stiller")
        self.box_field_styles.setToolTip("1-tıkla tematik harita ve morfoloji stilleri")
        self.box_field_styles.setVisible(False)
        st_layout = QVBoxLayout(self.box_field_styles)
        st_layout.setSpacing(4)

        lbl_style_desc = QLabel("Hesaplanan ada katmanını tek tıkla renklendirin:")
        lbl_style_desc.setStyleSheet(text_css("subtle", "8.5pt"))
        st_layout.addWidget(lbl_style_desc)

        btn_grid = QGridLayout()
        btn_grid.setSpacing(4)
        self.btn_style_pop = QPushButton("👥 Nüfus (k/ha)")
        self.btn_style_pop.setToolTip("Brüt nüfus yoğunluğu kademeleri (0, 1-50, 51-150, 151-300, 301-600, 600+)")
        self.btn_style_pop.clicked.connect(self._apply_style_pop)

        self.btn_style_taks = QPushButton("🏗️ TAKS (GSI)")
        self.btn_style_taks.setToolTip("Taban Alanı Katsayısı / Zemin Doluluk Oranı (GSI: <0.20, 0.20-0.40, 0.40-0.60, >0.60)")
        self.btn_style_taks.clicked.connect(self._apply_style_taks)

        self.btn_style_kaks = QPushButton("🏢 KAKS (Emsal)")
        self.btn_style_kaks.setToolTip("Kat Alanı Katsayısı / Emsal (FSI: <0.60, 0.60-1.20, 1.20-2.0, 2.0-3.5, >3.5)")
        self.btn_style_kaks.clicked.connect(self._apply_style_kaks)
        self.btn_style_kat = QPushButton("📏 Kat Sayısı (L)")
        self.btn_style_kat.setToolTip("Ağırlıklı Ortalama Kat Adedi (L = İnşaat Alanı / Taban Alanı)")
        self.btn_style_kat.clicked.connect(self._apply_style_ort_kat)

        self.btn_style_open = QPushButton("🌳 Açık Alan (%)")
        self.btn_style_open.setToolTip("Ada Zeminindeki Açık / Boş Alan Yüzdesi (100 - TAKS*100)")
        self.btn_style_open.clicked.connect(self._apply_style_open)

        self.btn_style_nizam = QPushButton("🏘️ Yapı Nizamı (A4)")
        self.btn_style_nizam.setToolTip("PlanX Morfoloji Motoru (A4): Ayrık, Bitişik / Blok, Karma, Boş Ada")
        self.btn_style_nizam.clicked.connect(self._apply_style_nizam)

        self.btn_style_doku = QPushButton("📐 Spacematrix")
        self.btn_style_doku.setToolTip("Spacematrix Morfolojik Tipolojisi: Seyrek Bahçeli, Orta Yoğunluk, Kompakt Blok, Kule Blok, Geleneksel Doku")
        self.btn_style_doku.clicked.connect(self._apply_style_doku)
        style_buttons = (self.btn_style_pop, self.btn_style_taks, self.btn_style_kaks, self.btn_style_kat,
                         self.btn_style_open, self.btn_style_nizam, self.btn_style_doku)
        for n, btn in enumerate(style_buttons):
            btn_grid.addWidget(btn, n // 2, n % 2)
        st_layout.addLayout(btn_grid)

        layout.addWidget(self.box_field_styles)

        self.txt_field_results = QTextEdit()
        self.txt_field_results.setReadOnly(True)
        self.txt_field_results.setMinimumHeight(200)
        self.txt_field_results.setPlaceholderText("Ada bazında fiili bina sayısı, TAKS, KAKS, konut birimleri ve nüfus sonuçları burada listelenecektir...")
        layout.addWidget(self.txt_field_results)

        layout.addStretch()
        return tab

    def _run_field_analysis(self):
        ada_layer = self.cmb_ada_layer.currentLayer()
        bina_layer = self.cmb_bina_layer.currentLayer()
        hh = self.spn_hh.value()
        daire_m2 = self.spn_daire_m2.value()
        net_oran = self.spn_net_oran.value()

        if not ada_layer or not bina_layer:
            QMessageBox.warning(self, "Uyarı", "Lütfen hem ada hem de bina katmanını seçin!")
            return

        self.btn_run_field.setEnabled(False)
        self.field_progress.setVisible(True)
        self.field_progress.setRange(0, 0)
        self.txt_field_results.clear()
        self.txt_field_results.append("<i>Binalar adalarla mekânsal eşleştiriliyor, morfolojik metrikler ve fiili nüfus modelleniyor...</i>")

        try:
            result_items, stats = FieldEstimatorEngine.estimate_ada_population(
                ada_layer, bina_layer, hh, daire_m2, net_oran
            )

            # Çıktı Katmanı
            uri = f"MultiPolygon?crs={ada_layer.crs().authid()}"
            out_layer = QgsVectorLayer(uri, f"{ada_layer.name()}_FIILI_NUFUS", "memory")
            out_prov = out_layer.dataProvider()

            out_fields = QgsFields(ada_layer.fields())
            out_fields.append(QgsField('FIILI_BINA_SAYISI', QVariant.Int))
            out_fields.append(QgsField('FIILI_KONUT_SAYISI', QVariant.Int))
            out_fields.append(QgsField('FIILI_TAHMINI_NUFUS', QVariant.Int))
            out_fields.append(QgsField('FIILI_BRUT_YOGUNLUK_HA', QVariant.Double))
            out_fields.append(QgsField('FIILI_TAKS', QVariant.Double))
            out_fields.append(QgsField('FIILI_KAKS', QVariant.Double))
            out_fields.append(QgsField('ORT_KAT', QVariant.Double))
            out_fields.append(QgsField('ACIK_ALAN_YUZDE', QVariant.Double))
            out_fields.append(QgsField('SPACEMATRIX_OSR', QVariant.Double))
            out_fields.append(QgsField('BINA_YOGUNLUK_HA', QVariant.Double))
            out_fields.append(QgsField('ORT_KOMPAKLIK_IPQ', QVariant.Double))
            out_fields.append(QgsField('YAPI_NIZAMI', QVariant.String))
            out_fields.append(QgsField('MAX_BITISIK_DIZI', QVariant.Int))
            out_fields.append(QgsField('DOKU_TIPI', QVariant.String))
            out_fields.append(QgsField('FIILI_ISTIHDAM', QVariant.Int))
            out_fields.append(QgsField('FIILI_ARAC_YOLCULUK', QVariant.Int))
            out_fields.append(QgsField('FIILI_YAYA_YOLCULUK', QVariant.Int))

            out_prov.addAttributes(out_fields)
            out_layer.updateFields()

            new_feats = []
            for item in result_items:
                feat = item["feat"]
                nf = QgsFeature(out_fields)
                nf.setGeometry(item["geom"])
                attrs = feat.attributes()
                attrs.extend([
                    item["bina_sayisi"],
                    item["konut_birim_sayisi"],
                    item["tahmini_nufus"],
                    item["fiili_brut_yogunluk_ha"],
                    item.get("fiili_taks", 0.0),
                    item.get("fiili_kaks", 0.0),
                    item.get("ort_kat", 0.0),
                    item.get("acik_alan_yuzde", 0.0),
                    item.get("spacematrix_osr", 0.0),
                    item.get("bina_yogunluk_ha", 0.0),
                    item.get("ort_kompaklik_ipq", 0.0),
                    str(item.get("yapi_nizami", "")),
                    item.get("max_bitisik_dizi", 0),
                    str(item.get("doku_tipi", "")),
                    item["istihdam"],
                    item["gunluk_arac"],
                    item["gunluk_yaya"]
                ])
                nf.setAttributes(attrs)
                new_feats.append(nf)

            out_prov.addFeatures(new_feats)
            out_layer.updateExtents()

            self.last_field_out_layer = out_layer
            self._apply_style_pop()

            QgsProject.instance().addMapLayer(out_layer)
            self.box_field_styles.setVisible(True)

            # Raporlama
            report_text = f"""
            <h3>🏠 MEVCUT DURUM FİİLİ NÜFUS VE MORFOLOJİ RAPORU</h3>
            <table border="1" cellpadding="4" style="border-collapse:collapse; width:100%; margin-bottom:8px;">
                <tr style="background:{self._c['accent_amber']}; color:{self._c['on_amber']};"><th colspan="2">1. Demografi & Yapılaşma Kapasitesi</th></tr>
                <tr><td><b>Toplam İncelenen Kadastro Adası</b></td><td>{stats['toplam_ada_sayisi']:,} Adet</td></tr>
                <tr><td><b>Eşleşen Toplam Bina Sayısı</b></td><td>{stats['toplam_eslesen_bina']:,} Adet</td></tr>
                <tr><td><b>Tahmini Konut Birim Sayısı</b></td><td>{stats['toplam_konut_birimi']:,} Bağımsız Bölüm</td></tr>
                <tr><td><b>Tahmini Fiili Yaşayan Nüfus</b></td><td style="color:{self._c['warn']}; font-weight:bold; font-size:13px;">{stats['toplam_fiili_nufus']:,} Kişi</td></tr>
                <tr><td><b>Tahmini Fiili İstihdam</b></td><td><b>{stats['toplam_fiili_istihdam']:,}</b> Çalışan</td></tr>
                <tr><td><b>Ortalama Hanehalkı Büyüklüğü</b></td><td>{stats['ortalama_hanehalki']} Kişi/Hane (Daire: {stats['ortalama_daire_m2']} m²)</td></tr>
            </table>

            <table border="1" cellpadding="4" style="border-collapse:collapse; width:100%;">
                <tr style="background:{self._c['primary']}; color:{self._c['on_accent']};"><th colspan="2">2. Kentsel Morfoloji, TAKS / KAKS ve Spacematrix Göstergeleri</th></tr>
                <tr><td><b>Toplam Bina Taban Alanı (m²)</b></td><td>{stats['toplam_taban_m2']:,.1f} m²</td></tr>
                <tr><td><b>Toplam İnşaat Alanı (m²)</b></td><td>{stats['toplam_insaat_m2']:,.1f} m²</td></tr>
                <tr><td><b>Ortalama Fiili TAKS (GSI)</b></td><td style="font-weight:bold; color:{self._c['accent']};">{stats['ortalama_taks']:.3f}</td></tr>
                <tr><td><b>Ortalama Fiili KAKS (Emsal / FSI)</b></td><td style="font-weight:bold; color:{self._c['accent']};">{stats['ortalama_kaks']:.3f}</td></tr>
                <tr><td><b>Ortalama Kat Adedi (L)</b></td><td><b>{stats['ortalama_kat']:.1f}</b> Kat</td></tr>
                <tr><td><b>Ortalama Açık Alan Oranı (%)</b></td><td><b>%{stats['ortalama_acik_alan_yuzde']:.1f}</b></td></tr>
            </table>
            <div style="font-size:10px; color:{self._c['subtle']}; margin-top:6px;">
                <i>* PlanX kentsel morfoloji motoru ve Spacematrix (Berghauser Pont & Haupt) analitik kütüphanesi ile hesaplanmıştır. Yukarıdaki 1-tıkla stil butonlarıyla tematik analiz haritaları üretebilirsiniz.</i>
            </div>
            """
            self.txt_field_results.setHtml(report_text)

            QMessageBox.information(
                self, "Mevcut Durum Analizi Tamamlandı",
                f"Tahmini Fiili Yaşayan Nüfus: {stats['toplam_fiili_nufus']:,} Kişi\n"
                f"Ortalama TAKS: {stats['ortalama_taks']:.3f} | KAKS: {stats['ortalama_kaks']:.3f}\n"
                f"Tahmini İstihdam: {stats['toplam_fiili_istihdam']:,} Çalışan\n\n"
                f"Fiili nüfus ve ada morfolojisi katmanı haritanıza eklendi. "
                f"Arayüzdeki butonlarla tematik harita görünümlerini anında değiştirebilirsiniz."
            )

        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Mevcut Durum Analizi sırasında hata: {str(e)}")
            self.txt_field_results.append(f"<span style='color:{self._c['bad']};'>Hata: {html.escape(str(e))}</span>")
        finally:
            self.btn_run_field.setEnabled(True)
            self.field_progress.setVisible(False)

    def _apply_style_pop(self):
        if not self.last_field_out_layer or not self.last_field_out_layer.isValid():
            QMessageBox.warning(self, "Uyarı", "Geçerli bir saha analiz çıktısı katmanı bulunamadı! Lütfen önce analizi çalıştırın.")
            return
        ranges = [
            QgsRendererRange(0.0, 0.0, QgsFillSymbol.createSimple({'color': '#cbd5e1', 'outline_color': '#94a3b8'}), "0 (Konut Dışı / Boş)"),
            QgsRendererRange(0.1, 50.0, QgsFillSymbol.createSimple({'color': '#d9f99d', 'outline_color': '#65a30d'}), "1 - 50 k/ha (Seyrek)"),
            QgsRendererRange(50.1, 150.0, QgsFillSymbol.createSimple({'color': '#fde047', 'outline_color': '#ca8a04'}), "51 - 150 k/ha (Düşük)"),
            QgsRendererRange(150.1, 300.0, QgsFillSymbol.createSimple({'color': '#fb923c', 'outline_color': '#ea580c'}), "151 - 300 k/ha (Orta)"),
            QgsRendererRange(300.1, 600.0, QgsFillSymbol.createSimple({'color': '#f87171', 'outline_color': '#dc2626'}), "301 - 600 k/ha (Yüksek)"),
            QgsRendererRange(600.1, 5000.0, QgsFillSymbol.createSimple({'color': '#991b1b', 'outline_color': '#450a0a'}), "600+ k/ha (Çok Yüksek)")
        ]
        self.last_field_out_layer.setRenderer(QgsGraduatedSymbolRenderer("FIILI_BRUT_YOGUNLUK_HA", ranges))
        self.last_field_out_layer.triggerRepaint()
        if self.iface and hasattr(self.iface, "layerTreeView") and self.iface.layerTreeView():
            self.iface.layerTreeView().refreshLayerSymbology(self.last_field_out_layer.id())

    def _apply_style_taks(self):
        if not self.last_field_out_layer or not self.last_field_out_layer.isValid():
            QMessageBox.warning(self, "Uyarı", "Geçerli bir saha analiz çıktısı katmanı bulunamadı! Lütfen önce analizi çalıştırın.")
            return
        ranges = [
            QgsRendererRange(0.0, 0.0, QgsFillSymbol.createSimple({'color': '#f1f5f9', 'outline_color': '#cbd5e1'}), "0.00 (Taban Yok / Boş)"),
            QgsRendererRange(0.001, 0.20, QgsFillSymbol.createSimple({'color': '#dcfce7', 'outline_color': '#16a34a'}), "0.01 - 0.20 (Çok Düşük Doluluk)"),
            QgsRendererRange(0.201, 0.40, QgsFillSymbol.createSimple({'color': '#fef08a', 'outline_color': '#ca8a04'}), "0.21 - 0.40 (Düşük/Orta Doluluk)"),
            QgsRendererRange(0.401, 0.60, QgsFillSymbol.createSimple({'color': '#fdba74', 'outline_color': '#ea580c'}), "0.41 - 0.60 (Orta/Yüksek Doluluk)"),
            QgsRendererRange(0.601, 1.00, QgsFillSymbol.createSimple({'color': '#ef4444', 'outline_color': '#b91c1c'}), "0.61 - 1.00 (Bitişik / Yoğun Doluluk)")
        ]
        self.last_field_out_layer.setRenderer(QgsGraduatedSymbolRenderer("FIILI_TAKS", ranges))
        self.last_field_out_layer.triggerRepaint()
        if self.iface and hasattr(self.iface, "layerTreeView") and self.iface.layerTreeView():
            self.iface.layerTreeView().refreshLayerSymbology(self.last_field_out_layer.id())

    def _apply_style_kaks(self):
        if not self.last_field_out_layer or not self.last_field_out_layer.isValid():
            QMessageBox.warning(self, "Uyarı", "Geçerli bir saha analiz çıktısı katmanı bulunamadı! Lütfen önce analizi çalıştırın.")
            return
        ranges = [
            QgsRendererRange(0.0, 0.0, QgsFillSymbol.createSimple({'color': '#f1f5f9', 'outline_color': '#cbd5e1'}), "0.00 (İnşaat Yok / Boş)"),
            QgsRendererRange(0.001, 0.60, QgsFillSymbol.createSimple({'color': '#dbeafe', 'outline_color': '#2563eb'}), "0.01 - 0.60 (Düşük Emsal)"),
            QgsRendererRange(0.601, 1.20, QgsFillSymbol.createSimple({'color': '#93c5fd', 'outline_color': '#1d4ed8'}), "0.61 - 1.20 (Orta-Düşük Emsal)"),
            QgsRendererRange(1.201, 2.00, QgsFillSymbol.createSimple({'color': '#fde047', 'outline_color': '#ca8a04'}), "1.21 - 2.00 (Orta Emsal)"),
            QgsRendererRange(2.001, 3.50, QgsFillSymbol.createSimple({'color': '#fb923c', 'outline_color': '#ea580c'}), "2.01 - 3.50 (Yüksek Emsal)"),
            QgsRendererRange(3.501, 25.0, QgsFillSymbol.createSimple({'color': '#dc2626', 'outline_color': '#991b1b'}), "3.50+ (Çok Yüksek Emsal)")
        ]
        self.last_field_out_layer.setRenderer(QgsGraduatedSymbolRenderer("FIILI_KAKS", ranges))
        self.last_field_out_layer.triggerRepaint()
        if self.iface and hasattr(self.iface, "layerTreeView") and self.iface.layerTreeView():
            self.iface.layerTreeView().refreshLayerSymbology(self.last_field_out_layer.id())

    def _apply_style_ort_kat(self):
        if not self.last_field_out_layer or not self.last_field_out_layer.isValid():
            QMessageBox.warning(self, "Uyarı", "Geçerli bir saha analiz çıktısı katmanı bulunamadı! Lütfen önce analizi çalıştırın.")
            return
        ranges = [
            QgsRendererRange(0.0, 0.0, QgsFillSymbol.createSimple({'color': '#f1f5f9', 'outline_color': '#cbd5e1'}), "0 (Yapısız Ada)"),
            QgsRendererRange(0.1, 1.5, QgsFillSymbol.createSimple({'color': '#e0e7ff', 'outline_color': '#4338ca'}), "1 Katlı"),
            QgsRendererRange(1.51, 2.5, QgsFillSymbol.createSimple({'color': '#a5b4fc', 'outline_color': '#4338ca'}), "2 Katlı"),
            QgsRendererRange(2.51, 4.5, QgsFillSymbol.createSimple({'color': '#818cf8', 'outline_color': '#3730a3'}), "3 - 4 Katlı"),
            QgsRendererRange(4.51, 6.5, QgsFillSymbol.createSimple({'color': '#f59e0b', 'outline_color': '#b45309'}), "5 - 6 Katlı"),
            QgsRendererRange(6.51, 50.0, QgsFillSymbol.createSimple({'color': '#dc2626', 'outline_color': '#991b1b'}), "7+ Katlı")
        ]
        self.last_field_out_layer.setRenderer(QgsGraduatedSymbolRenderer("ORT_KAT", ranges))
        self.last_field_out_layer.triggerRepaint()
        if self.iface and hasattr(self.iface, "layerTreeView") and self.iface.layerTreeView():
            self.iface.layerTreeView().refreshLayerSymbology(self.last_field_out_layer.id())

    def _apply_style_open(self):
        if not self.last_field_out_layer or not self.last_field_out_layer.isValid():
            QMessageBox.warning(self, "Uyarı", "Geçerli bir saha analiz çıktısı katmanı bulunamadı! Lütfen önce analizi çalıştırın.")
            return
        ranges = [
            QgsRendererRange(0.0, 25.0, QgsFillSymbol.createSimple({'color': '#ef4444', 'outline_color': '#b91c1c'}), "% 0 - 25 (Çok Az Açık Alan / Bitişik)"),
            QgsRendererRange(25.01, 50.0, QgsFillSymbol.createSimple({'color': '#f97316', 'outline_color': '#c2410c'}), "% 25 - 50 (Düşük Açık Alan)"),
            QgsRendererRange(50.01, 70.0, QgsFillSymbol.createSimple({'color': '#facc15', 'outline_color': '#a16207'}), "% 50 - 70 (Orta Açık Alan)"),
            QgsRendererRange(70.01, 85.0, QgsFillSymbol.createSimple({'color': '#86efac', 'outline_color': '#16a34a'}), "% 70 - 85 (Yüksek Açık Alan)"),
            QgsRendererRange(85.01, 100.0, QgsFillSymbol.createSimple({'color': '#22c55e', 'outline_color': '#15803d'}), "% 85 - 100 (Geniş Açık Alan / Bahçeli)")
        ]
        self.last_field_out_layer.setRenderer(QgsGraduatedSymbolRenderer("ACIK_ALAN_YUZDE", ranges))
        self.last_field_out_layer.triggerRepaint()
        if self.iface and hasattr(self.iface, "layerTreeView") and self.iface.layerTreeView():
            self.iface.layerTreeView().refreshLayerSymbology(self.last_field_out_layer.id())

    def _apply_style_nizam(self):
        if not self.last_field_out_layer or not self.last_field_out_layer.isValid():
            QMessageBox.warning(self, "Uyarı", "Geçerli bir saha analiz çıktısı katmanı bulunamadı! Lütfen önce analizi çalıştırın.")
            return
        categories = [
            QgsRendererCategory("Ayrık", QgsFillSymbol.createSimple({'color': '#3b82f6', 'outline_color': '#1d4ed8'}), "Ayrık"),
            QgsRendererCategory("Bitişik / Blok", QgsFillSymbol.createSimple({'color': '#ef4444', 'outline_color': '#b91c1c'}), "Bitişik / Blok"),
            QgsRendererCategory("Karma (Ayrık + Bitişik)", QgsFillSymbol.createSimple({'color': '#f59e0b', 'outline_color': '#b45309'}), "Karma (Ayrık + Bitişik)"),
            QgsRendererCategory("Boş Ada", QgsFillSymbol.createSimple({'color': '#94a3b8', 'outline_color': '#64748b'}), "Boş Ada")
        ]
        self.last_field_out_layer.setRenderer(QgsCategorizedSymbolRenderer("YAPI_NIZAMI", categories))
        self.last_field_out_layer.triggerRepaint()
        if self.iface and hasattr(self.iface, "layerTreeView") and self.iface.layerTreeView():
            self.iface.layerTreeView().refreshLayerSymbology(self.last_field_out_layer.id())

    def _apply_style_doku(self):
        if not self.last_field_out_layer or not self.last_field_out_layer.isValid():
            QMessageBox.warning(self, "Uyarı", "Geçerli bir saha analiz çıktısı katmanı bulunamadı! Lütfen önce analizi çalıştırın.")
            return
        categories = [
            QgsRendererCategory("Seyrek / Az Katlı Bahçeli", QgsFillSymbol.createSimple({'color': '#10b981', 'outline_color': '#047857'}), "Seyrek / Az Katlı Bahçeli"),
            QgsRendererCategory("Orta Yoğunluklu Doku", QgsFillSymbol.createSimple({'color': '#3b82f6', 'outline_color': '#1d4ed8'}), "Orta Yoğunluklu Doku"),
            QgsRendererCategory("Yüksek Yoğunluklu / Kompakt Blok", QgsFillSymbol.createSimple({'color': '#ef4444', 'outline_color': '#b91c1c'}), "Yüksek Yoğunluklu / Kompakt Blok"),
            QgsRendererCategory("Nokta / Kule Bloklar", QgsFillSymbol.createSimple({'color': '#8b5cf6', 'outline_color': '#6d28d9'}), "Nokta / Kule Bloklar"),
            QgsRendererCategory("Geleneksel / Karma Kentsel Doku", QgsFillSymbol.createSimple({'color': '#f59e0b', 'outline_color': '#b45309'}), "Geleneksel / Karma Kentsel Doku"),
            QgsRendererCategory("Boş / Yapılaşmamış Ada", QgsFillSymbol.createSimple({'color': '#94a3b8', 'outline_color': '#64748b'}), "Boş / Yapılaşmamış Ada")
        ]
        self.last_field_out_layer.setRenderer(QgsCategorizedSymbolRenderer("DOKU_TIPI", categories))
        self.last_field_out_layer.triggerRepaint()
        if self.iface and hasattr(self.iface, "layerTreeView") and self.iface.layerTreeView():
            self.iface.layerTreeView().refreshLayerSymbology(self.last_field_out_layer.id())

    # -----------------------------------------------------------------
    # SEKME 6: ULAŞIM AĞI, ÖN CEPHE, ERİŞİM ÇAPLARI VE OD MATRİSİ
    # -----------------------------------------------------------------
    def _create_tab_network(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        card_info = QFrame()
        card_info.setObjectName("nipAccentCard")
        info_lay = QVBoxLayout(card_info)
        info_lay.setContentsMargins(10, 8, 10, 8)
        info_lay.setSpacing(4)

        t_lbl = QLabel("🌐 Ulaşım, Ağ ve Erişim Analizleri")
        t_lbl.setToolTip("Kentsel ulaşım, ağ ve mekânsal erişim analizleri (PlanX motoru)")
        t_lbl.setStyleSheet(text_css("accent", "10pt", bold=True))
        info_lay.addWidget(t_lbl)

        d_lbl = QLabel(
            "Kentsel Ağ ve Mekânsal Erişim Analizleri Süiti:\n"
            "PlanX gömülü saf NumPy/SciPy motoru ile Space Syntax (NAIN/NACH), Primal Ağ Merkezilikleri, "
            "OD Matrisi & Detour Bariyerleri, 5-10-15 dk Yürüme İzokronları & Pedshed, 2SFCA Kapasite Yeterliliği "
            "ve Mevcut vs Meri Plan A/B Fark Haritası."
        )
        d_lbl.setWordWrap(True)
        d_lbl.setStyleSheet(text_css("subtle", "8.5pt"))
        info_lay.addWidget(d_lbl)
        layout.addWidget(card_info)

        sub_tabs = QTabWidget()
        sub_tabs.setObjectName("nipNetworkSubTabs")

        # -------------------------------------------------------------
        # Alt Sekme 1: Space Syntax (Açısal Segment Analizi)
        # -------------------------------------------------------------
        w_syntax = QWidget()
        l_syntax = QVBoxLayout(w_syntax)
        f_syntax = QFormLayout()

        self.cmb_syntax_roads = QgsMapLayerComboBox()
        self.cmb_syntax_roads.setFilters(QgsMapLayerProxyModel.Filter.LineLayer)
        f_syntax.addRow("Yol ağı katmanı:", self.cmb_syntax_roads)

        self.txt_syntax_radii = QLineEdit("400, 800, 1200, n")
        self.txt_syntax_radii.setToolTip("Metrik yarıçaplar (m): Yaya koridorları için 400/800, kent ölçeği için n")
        f_syntax.addRow("Yarıçaplar (m):", self.txt_syntax_radii)

        l_syntax.addLayout(f_syntax)
        lbl_syntax_hint = QLabel("💡 Çıktılar: NAIN (Varış/Yaya Canlılığı) ve NACH (Geçiş/Arter Yükü) metrikleri.")
        lbl_syntax_hint.setStyleSheet(text_css("subtle", "8pt", italic=True))
        l_syntax.addWidget(lbl_syntax_hint)

        self.btn_run_syntax = QPushButton("🚀 Space Syntax Çalıştır")
        self.btn_run_syntax.setToolTip("Space Syntax segment analizini çalıştır (NAIN & NACH)")
        self.btn_run_syntax.setObjectName("PrimaryButton")
        self.btn_run_syntax.setCursor(_POINTING_HAND)
        self.btn_run_syntax.clicked.connect(self._on_run_space_syntax)
        l_syntax.addWidget(self.btn_run_syntax)
        l_syntax.addStretch()
        sub_tabs.addTab(w_syntax, "1. Space Syntax")

        # -------------------------------------------------------------
        # Alt Sekme 2: Primal Ağ Merkeziliği (Betweenness, Closeness)
        # -------------------------------------------------------------
        w_cent = QWidget()
        l_cent = QVBoxLayout(w_cent)
        f_cent = QFormLayout()

        self.cmb_cent_roads = QgsMapLayerComboBox()
        self.cmb_cent_roads.setFilters(QgsMapLayerProxyModel.Filter.LineLayer)
        f_cent.addRow("Yol Ağı Katmanı:", self.cmb_cent_roads)

        self.txt_cent_radii = QLineEdit("800, 5000, n")
        self.txt_cent_radii.setToolTip("R=800m yaya/ticaret koridorları, R=5000m taşıt/lojistik koridorları")
        f_cent.addRow("Yarıçaplar (R metre):", self.txt_cent_radii)

        self.chk_cent_edges = QCheckBox("Aks merkezilikleri (Edges)")
        self.chk_cent_edges.setChecked(True)
        f_cent.addRow(self.chk_cent_edges)

        self.chk_cent_nodes = QCheckBox("Kavşak merkezilikleri (Nodes)")
        self.chk_cent_nodes.setChecked(True)
        f_cent.addRow(self.chk_cent_nodes)

        l_cent.addLayout(f_cent)
        lbl_cent_hint = QLabel("💡 Çıktılar: Betweenness (Aradalık), Closeness (Yakınlık) ve Straightness (Doğrusallık).")
        lbl_cent_hint.setStyleSheet(text_css("subtle", "8pt", italic=True))
        l_cent.addWidget(lbl_cent_hint)

        self.btn_run_cent = QPushButton("📊 Merkezilikleri Hesapla")
        self.btn_run_cent.setToolTip("Primal ağ merkeziliklerini hesapla")
        self.btn_run_cent.setObjectName("PrimaryButton")
        self.btn_run_cent.setCursor(_POINTING_HAND)
        self.btn_run_cent.clicked.connect(self._on_run_network_centrality)
        l_cent.addWidget(self.btn_run_cent)
        l_cent.addStretch()
        sub_tabs.addTab(w_cent, "2. Merkezilik")

        # -------------------------------------------------------------
        # Alt Sekme 3: OD Matrisi, Rotalama ve Bariyer Analizi
        # -------------------------------------------------------------
        w_od = QWidget()
        l_od = QVBoxLayout(w_od)
        f_od = QFormLayout()

        self.cmb_od_origins = QgsMapLayerComboBox()
        self.cmb_od_origins.setFilters(QgsMapLayerProxyModel.Filter.PointLayer)
        f_od.addRow("Menşe noktaları:", self.cmb_od_origins)

        self.cmb_od_destinations = QgsMapLayerComboBox()
        self.cmb_od_destinations.setFilters(QgsMapLayerProxyModel.Filter.PointLayer)
        f_od.addRow("Hedef noktaları:", self.cmb_od_destinations)

        self.cmb_od_road = QgsMapLayerComboBox()
        self.cmb_od_road.setFilters(QgsMapLayerProxyModel.Filter.LineLayer)
        f_od.addRow("Yol Ağı Katmanı:", self.cmb_od_road)

        self.chk_od_routes = QCheckBox("En kısa yol rotalarını üret")
        self.chk_od_routes.setToolTip("Ağ üzerindeki gerçek en kısa yol rotalarını çizgi olarak üret")
        self.chk_od_routes.setChecked(True)
        f_od.addRow(self.chk_od_routes)

        self.chk_od_desire = QCheckBox("Arzu hatları ve bariyer analizi")
        self.chk_od_desire.setToolTip("Kuş uçuşu arzu hatları ve Detour bariyer analizini üret (> 1.35)")
        self.chk_od_desire.setChecked(True)
        f_od.addRow(self.chk_od_desire)

        l_od.addLayout(f_od)
        lbl_od_hint = QLabel("💡 Detour Ratio = Ağ Mesafesi / Kuş Uçuşu. 1.35 üzerindeki akslar kopukluk/bariyer işaretidir.")
        lbl_od_hint.setStyleSheet(text_css("subtle", "8pt", italic=True))
        l_od.addWidget(lbl_od_hint)

        self.btn_run_od = QPushButton("📍 OD Rotalarını Üret")
        self.btn_run_od.setToolTip("OD rotalarını ve Detour bariyerlerini üret")
        self.btn_run_od.setObjectName("AccentButton")
        self.btn_run_od.setCursor(_POINTING_HAND)
        self.btn_run_od.clicked.connect(self._on_run_od_rotalama)
        l_od.addWidget(self.btn_run_od)
        l_od.addStretch()
        sub_tabs.addTab(w_od, "3. OD & Rota")

        # -------------------------------------------------------------
        # Alt Sekme 4: Hizmet Alanları ve Yürüme İzokronları (Pedshed)
        # -------------------------------------------------------------
        w_iso = QWidget()
        l_iso = QVBoxLayout(w_iso)
        f_iso = QFormLayout()

        self.cmb_iso_facilities = QgsMapLayerComboBox()
        self.cmb_iso_facilities.setFilters(QgsMapLayerProxyModel.Filter.PointLayer | QgsMapLayerProxyModel.Filter.PolygonLayer)
        f_iso.addRow("Donatı katmanı:", self.cmb_iso_facilities)

        self.cmb_iso_roads = QgsMapLayerComboBox()
        self.cmb_iso_roads.setFilters(QgsMapLayerProxyModel.Filter.LineLayer)
        f_iso.addRow("Yol Ağı Katmanı:", self.cmb_iso_roads)

        self.txt_iso_breaks = QLineEdit("400, 800, 1200")
        f_iso.addRow("Yürüme Eşikleri (metre):", self.txt_iso_breaks)

        self.cmb_iso_method = QComboBox()
        self.cmb_iso_method.addItems([
            "Yol Tamponu (Street Buffer - PlanX Hassas)",
            "İçbükey Gövde (Concave Hull - İzokron Blobu)",
            "Dışbükey Gövde (Convex Hull - Zarf)"
        ])
        f_iso.addRow("İzokron yöntemi:", self.cmb_iso_method)

        l_iso.addLayout(f_iso)
        lbl_iso_hint = QLabel("💡 Virgülle ayrılmış mesafeler girilebilir (örn: 200, 400, 600 veya 400, 800, 1200). Pedshed < 0.40 izoledir.")
        lbl_iso_hint.setStyleSheet(text_css("subtle", "8pt", italic=True))
        l_iso.addWidget(lbl_iso_hint)

        self.btn_run_iso = QPushButton("🚶 İzokronları Üret")
        self.btn_run_iso.setToolTip("Hizmet izokronları ve Pedshed karnesini üret")
        self.btn_run_iso.setObjectName("SecondaryButton")
        self.btn_run_iso.setCursor(_POINTING_HAND)
        self.btn_run_iso.clicked.connect(self._on_run_hizmet_izokron)
        l_iso.addWidget(self.btn_run_iso)
        l_iso.addStretch()
        sub_tabs.addTab(w_iso, "4. İzokron")

        # -------------------------------------------------------------
        # Alt Sekme 5: 2SFCA Donatı Yeterliliği (Kapasite + Mesafe)
        # -------------------------------------------------------------
        w_fca = QWidget()
        l_fca = QVBoxLayout(w_fca)
        f_fca = QFormLayout()

        self.cmb_fca_facilities = QgsMapLayerComboBox()
        self.cmb_fca_facilities.setFilters(QgsMapLayerProxyModel.Filter.PointLayer | QgsMapLayerProxyModel.Filter.PolygonLayer)
        f_fca.addRow("Donatı katmanı:", self.cmb_fca_facilities)

        self.cmb_fca_id_field = QgsFieldComboBox()
        self.cmb_fca_id_field.setAllowEmptyFieldName(True)
        f_fca.addRow("Ad / kimlik sütunu:", self.cmb_fca_id_field)

        self.cmb_fca_cap_field = QgsFieldComboBox()
        self.cmb_fca_cap_field.setAllowEmptyFieldName(True)
        f_fca.addRow("Kapasite sütunu:", self.cmb_fca_cap_field)

        self.spn_fca_default_cap = QDoubleSpinBox()
        self.spn_fca_default_cap.setRange(1.0, 1000000.0)
        self.spn_fca_default_cap.setValue(100.0)
        self.spn_fca_default_cap.setSuffix(" birim")
        f_fca.addRow("Varsayılan kapasite:", self.spn_fca_default_cap)

        self.cmb_fca_demand = QgsMapLayerComboBox()
        self.cmb_fca_demand.setFilters(QgsMapLayerProxyModel.Filter.PointLayer | QgsMapLayerProxyModel.Filter.PolygonLayer)
        f_fca.addRow("Talep (nüfus) katmanı:", self.cmb_fca_demand)

        self.cmb_fca_pop_field = QgsFieldComboBox()
        self.cmb_fca_pop_field.setAllowEmptyFieldName(True)
        f_fca.addRow("Nüfus sütunu:", self.cmb_fca_pop_field)

        self.cmb_fca_roads = QgsMapLayerComboBox()
        self.cmb_fca_roads.setFilters(QgsMapLayerProxyModel.Filter.LineLayer)
        f_fca.addRow("Yol Ağı Katmanı:", self.cmb_fca_roads)

        self.spn_fca_cost = QDoubleSpinBox()
        self.spn_fca_cost.setRange(50.0, 10000.0)
        self.spn_fca_cost.setValue(800.0)
        self.spn_fca_cost.setSuffix(" metre")
        f_fca.addRow("Azami servis mesafesi:", self.spn_fca_cost)

        self.cmb_fca_facilities.layerChanged.connect(self._fca_fac_combo_changed)
        self.cmb_fca_demand.layerChanged.connect(self._fca_dem_combo_changed)

        if self.cmb_fca_facilities.currentLayer():
            self._on_fca_fac_layer_changed(self.cmb_fca_facilities.currentLayer())
        if self.cmb_fca_demand.currentLayer():
            self._on_fca_dem_layer_changed(self.cmb_fca_demand.currentLayer())

        l_fca.addLayout(f_fca)
        lbl_fca_hint = QLabel("💡 E2SFCA yöntemiyle aşırı yüklü (Overloaded) ve hizmet alamayan (Uncovered) nüfus tespit edilir.")
        lbl_fca_hint.setStyleSheet(text_css("subtle", "8pt", italic=True))
        l_fca.addWidget(lbl_fca_hint)

        self.btn_run_fca = QPushButton("⚖️ 2SFCA Çalıştır")
        self.btn_run_fca.setToolTip("2SFCA kapasite ve aşırı yük analizini çalıştır")
        self.btn_run_fca.setObjectName("AccentButton")
        self.btn_run_fca.setCursor(_POINTING_HAND)
        self.btn_run_fca.clicked.connect(self._on_run_2sfca)
        l_fca.addWidget(self.btn_run_fca)
        l_fca.addStretch()
        sub_tabs.addTab(w_fca, "5. 2SFCA")

        # -------------------------------------------------------------
        # Alt Sekme 6: A/B Senaryosu (Mevcut vs Meri Plan Kıyası)
        # -------------------------------------------------------------
        w_scen = QWidget()
        l_scen = QVBoxLayout(w_scen)
        f_scen = QFormLayout()

        self.cmb_scen_road_a = QgsMapLayerComboBox()
        self.cmb_scen_road_a.setFilters(QgsMapLayerProxyModel.Filter.LineLayer)
        f_scen.addRow("A: Mevcut yol ağı:", self.cmb_scen_road_a)

        self.cmb_scen_road_b = QgsMapLayerComboBox()
        self.cmb_scen_road_b.setFilters(QgsMapLayerProxyModel.Filter.LineLayer)
        f_scen.addRow("B: Öneri yol ağı:", self.cmb_scen_road_b)

        self.spn_scen_radius = QDoubleSpinBox()
        self.spn_scen_radius.setRange(200.0, 5000.0)
        self.spn_scen_radius.setValue(800.0)
        self.spn_scen_radius.setSuffix(" metre")
        f_scen.addRow("Kıyas yarıçapı:", self.spn_scen_radius)

        l_scen.addLayout(f_scen)
        lbl_scen_hint = QLabel("💡 Delta NACH, Delta NAIN ve 4 Temel Plan Karar Başlığı (Kademelenme, Yayalaştırma vb.) otomatik üretilir.")
        lbl_scen_hint.setStyleSheet(text_css("subtle", "8pt", italic=True))
        l_scen.addWidget(lbl_scen_hint)

        self.btn_run_scen = QPushButton("🔄 A/B Fark Haritası")
        self.btn_run_scen.setToolTip("A/B fark haritası ve plan kararlarını üret")
        self.btn_run_scen.setObjectName("PrimaryButton")
        self.btn_run_scen.setCursor(_POINTING_HAND)
        self.btn_run_scen.clicked.connect(self._on_run_scenario_compare)
        l_scen.addWidget(self.btn_run_scen)
        l_scen.addStretch()
        sub_tabs.addTab(w_scen, "6. A/B")

        # -------------------------------------------------------------
        # Alt Sekme 7: Ada/Bina Ön Cephe ve Servis Noktası Bulucu
        # -------------------------------------------------------------
        w_cephe = QWidget()
        l_cephe = QVBoxLayout(w_cephe)
        f_cephe = QFormLayout()

        self.cmb_cephe_poly = QgsMapLayerComboBox()
        self.cmb_cephe_poly.setFilters(QgsMapLayerProxyModel.Filter.PolygonLayer)
        f_cephe.addRow("Ada / parsel / bina:", self.cmb_cephe_poly)

        self.cmb_cephe_road = QgsMapLayerComboBox()
        self.cmb_cephe_road.setFilters(QgsMapLayerProxyModel.Filter.LineLayer)
        f_cephe.addRow("Yol Ağı Katmanı:", self.cmb_cephe_road)

        self.spn_cephe_dist = QDoubleSpinBox()
        self.spn_cephe_dist.setRange(5.0, 500.0)
        self.spn_cephe_dist.setValue(100.0)
        self.spn_cephe_dist.setSuffix(" metre")
        f_cephe.addRow("Azami arama mesafesi:", self.spn_cephe_dist)

        l_cephe.addLayout(f_cephe)
        self.btn_run_cephe = QPushButton("🏢 Ön Cepheleri Üret")
        self.btn_run_cephe.setToolTip("Ön cephe segmentlerini ve servis noktalarını üret")
        self.btn_run_cephe.setObjectName("SecondaryButton")
        self.btn_run_cephe.setCursor(_POINTING_HAND)
        self.btn_run_cephe.clicked.connect(self._on_run_on_cephe)
        l_cephe.addWidget(self.btn_run_cephe)
        l_cephe.addStretch()
        sub_tabs.addTab(w_cephe, "7. Ön Cephe")

        layout.addWidget(sub_tabs)
        layout.addStretch()
        return tab

    # -----------------------------------------------------------------
    # NETWORK ANALİZ TETİKLEYİCİLERİ
    # -----------------------------------------------------------------
    def _on_run_space_syntax(self):
        road_layer = self.cmb_syntax_roads.currentLayer()
        if not road_layer or not isinstance(road_layer, QgsVectorLayer):
            QMessageBox.warning(self, "Uyarı", "Lütfen geçerli bir yol ağı katmanı seçin!")
            return

        radii = self.txt_syntax_radii.text().strip() or "400, 800, 1200, n"
        params = {
            'NETWORK': road_layer,
            'RADII': radii,
            'OUTPUT': 'TEMPORARY_OUTPUT'
        }
        try:
            self.btn_run_syntax.setEnabled(False)
            res = processing.run("pln3113:nip_space_syntax", params)
            out_id = res.get('OUTPUT')
            layer = self._to_vector_layer(out_id, f"Space Syntax ({road_layer.name()})")
            if layer and layer.isValid():
                layer.setName(f"Space Syntax - NAIN & NACH ({road_layer.name()})")
                style_space_syntax(layer, "NACH_R800")
                self._safe_add_map_layer(layer)
                QMessageBox.information(
                    self, "Başarılı",
                    f"Space Syntax (Açısal Segment Analizi) tamamlandı!\n"
                    f"Aks Sayısı: {layer.featureCount()}\n"
                    f"Hesaplanan Yarıçaplar: {radii}\n"
                    f"Katman haritaya eklendi ve spektral NACH/NAIN renk skalasıyla stillendirildi."
                )
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Space Syntax analizi sırasında hata:\n{str(e)}")
        finally:
            self.btn_run_syntax.setEnabled(True)

    def _on_run_network_centrality(self):
        road_layer = self.cmb_cent_roads.currentLayer()
        if not road_layer or not isinstance(road_layer, QgsVectorLayer):
            QMessageBox.warning(self, "Uyarı", "Lütfen geçerli bir yol ağı katmanı seçin!")
            return

        radii = self.txt_cent_radii.text().strip() or "800, 5000, n"
        params = {
            'NETWORK': road_layer,
            'RADIUS': 800.0,
            'EDGES': 'TEMPORARY_OUTPUT' if self.chk_cent_edges.isChecked() else None,
            'NODES': 'TEMPORARY_OUTPUT' if self.chk_cent_nodes.isChecked() else None,
        }
        try:
            self.btn_run_cent.setEnabled(False)
            res = processing.run("pln3113:nip_network_centrality", params)
            edges_out = res.get('EDGES')
            nodes_out = res.get('NODES')

            lyr = self._to_vector_layer(edges_out, f"Ağ Merkezilikleri - Akslar ({road_layer.name()})")
            if lyr and lyr.isValid():
                lyr.setName(f"Ağ Merkezilikleri - Akslar ({road_layer.name()})")
                style_od_and_centrality(centrality_layer=lyr)
                self._safe_add_map_layer(lyr)

            lyr_n = self._to_vector_layer(nodes_out, f"Kavşak Merkezilikleri - Düğümler ({road_layer.name()})")
            if lyr_n and lyr_n.isValid():
                lyr_n.setName(f"Kavşak Merkezilikleri - Düğümler ({road_layer.name()})")
                self._safe_add_map_layer(lyr_n)

            QMessageBox.information(
                self, "Başarılı",
                f"Primal Ağ Merkeziliği Analizi tamamlandı!\n"
                f"Hesaplanan Metrikler: Betweenness (Aradalık), Closeness (Yakınlık), Straightness (Doğrusallık)."
            )
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Ağ merkeziliği analizi sırasında hata:\n{str(e)}")
        finally:
            self.btn_run_cent.setEnabled(True)

    def _on_run_od_rotalama(self):
        orig_layer = self.cmb_od_origins.currentLayer()
        dest_layer = self.cmb_od_destinations.currentLayer()
        road_layer = self.cmb_od_road.currentLayer()

        if not orig_layer or not isinstance(orig_layer, QgsVectorLayer):
            QMessageBox.warning(self, "Uyarı", "Lütfen geçerli bir başlangıç (Origin) katmanı seçin!")
            return
        if not dest_layer or not isinstance(dest_layer, QgsVectorLayer):
            QMessageBox.warning(self, "Uyarı", "Lütfen geçerli bir hedef (Destination) katmanı seçin!")
            return
        if not road_layer or not isinstance(road_layer, QgsVectorLayer):
            QMessageBox.warning(self, "Uyarı", "Lütfen geçerli bir yol ağı katmanı seçin!")
            return

        params = {
            'NETWORK': road_layer,
            'ORIGINS': orig_layer,
            'DESTINATIONS': dest_layer,
            'OUTPUT_DESIRE': 'TEMPORARY_OUTPUT' if self.chk_od_desire.isChecked() else None,
            'OUTPUT_ROUTES': 'TEMPORARY_OUTPUT' if self.chk_od_routes.isChecked() else None,
            'OUTPUT_MATRIX': 'TEMPORARY_OUTPUT',
        }
        try:
            self.btn_run_od.setEnabled(False)
            res = processing.run("pln3113:nip_od_rotalama", params)
            routes_out = res.get('OUTPUT_ROUTES')
            desire_out = res.get('OUTPUT_DESIRE')
            matrix_out = res.get('OUTPUT_MATRIX')

            lyr_r = self._to_vector_layer(routes_out, "En Kısa Yol Ağ Rotaları")
            if lyr_r and lyr_r.isValid():
                lyr_r.setName(f"En Kısa Yol Ağ Rotaları ({orig_layer.name()} -> {dest_layer.name()})")
                style_od_and_centrality(routes_layer=lyr_r)
                self._safe_add_map_layer(lyr_r)

            lyr_d = self._to_vector_layer(desire_out, "Kuş Uçuşu Arzu Hatları ve Detour")
            if lyr_d and lyr_d.isValid():
                lyr_d.setName(f"Arzu Hatları ve Bariyerler (Detour > 1.35)")
                style_detour_barrier(lyr_d)
                self._safe_add_map_layer(lyr_d)

            lyr_m = self._to_vector_layer(matrix_out, "OD Mesafe Matrisi Tablosu")
            if lyr_m and lyr_m.isValid():
                lyr_m.setName("OD Mesafe Matrisi Tablosu")
                self._safe_add_map_layer(lyr_m)

            QMessageBox.information(
                self, "Başarılı",
                f"OD Matrisi ve Rotalama analizi başarıyla tamamlandı!\n"
                f"Detour Ratio > 1.35 olan kopuk/bariyerli koridorlar kırmızı kesikli çizgiyle stillendirildi."
            )
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"OD Rotalama analizi sırasında hata:\n{str(e)}")
        finally:
            self.btn_run_od.setEnabled(True)

    def _on_run_hizmet_izokron(self):
        fac_layer = self.cmb_iso_facilities.currentLayer()
        road_layer = self.cmb_iso_roads.currentLayer()
        if not fac_layer or not isinstance(fac_layer, QgsVectorLayer):
            QMessageBox.warning(self, "Uyarı", "Lütfen geçerli bir donatı katmanı seçin!")
            return
        if not road_layer or not isinstance(road_layer, QgsVectorLayer):
            QMessageBox.warning(self, "Uyarı", "Lütfen geçerli bir yol ağı katmanı seçin!")
            return

        breaks = self.txt_iso_breaks.text().strip() or "400, 800, 1200"
        method = self.cmb_iso_method.currentIndex()
        params = {
            'NETWORK': road_layer,
            'FACILITIES': fac_layer,
            'BREAKS': breaks,
            'METHOD': method,
            'AREAS': 'TEMPORARY_OUTPUT',
            'CIRCLES': 'TEMPORARY_OUTPUT',
            'EDGES': 'TEMPORARY_OUTPUT',
            'SUMMARY': 'TEMPORARY_OUTPUT'
        }
        try:
            self.btn_run_iso.setEnabled(False)
            res = processing.run("pln3113:nip_hizmet_izokron", params)
            areas_out = res.get('AREAS')
            circles_out = res.get('CIRCLES')
            edges_out = res.get('EDGES')
            summary_out = res.get('SUMMARY')

            lyr_c = self._to_vector_layer(circles_out, "Mevzuat Kuş Uçuşu Dairesel Tamponlar")
            if lyr_c and lyr_c.isValid():
                lyr_c.setName(f"Mevzuat Etki Daireleri ({fac_layer.name()})")
                style_service_area(buffer_layer=lyr_c)
                self._safe_add_map_layer(lyr_c)

            lyr_a = self._to_vector_layer(areas_out, "Yürüme İzokron Poligonları (Pedshed)")
            if lyr_a and lyr_a.isValid():
                lyr_a.setName(f"Yürüme İzokronları ({fac_layer.name()})")
                custom_brk_nums = []
                for b_tok in breaks.replace(";", ",").split(","):
                    with contextlib.suppress(ValueError, TypeError):
                        if b_tok.strip():
                            custom_brk_nums.append(float(b_tok.strip()))
                style_isochrone_bands(lyr_a, custom_breaks=custom_brk_nums)
                self._safe_add_map_layer(lyr_a)

            lyr_e = self._to_vector_layer(edges_out, "Erişilen Kırpılmış Yol Parçaları")
            if lyr_e and lyr_e.isValid():
                lyr_e.setName(f"Erişilen Yol Parçaları ({fac_layer.name()})")
                style_service_area(roads_layer=lyr_e)
                self._safe_add_map_layer(lyr_e)

            lyr_s = self._to_vector_layer(summary_out, "Pedshed Erişilebilirlik Karnesi")
            if lyr_s and lyr_s.isValid():
                lyr_s.setName("Pedshed Erişilebilirlik Karnesi (Tablo)")
                self._safe_add_map_layer(lyr_s)

            # Eşik sürelerini dinamik hesapla
            min_labels = []
            for b_tok in breaks.replace(";", ",").split(","):
                with contextlib.suppress(ValueError, TypeError):
                    if b_tok.strip():
                        b_val = float(b_tok.strip())
                        s_min = round(b_val / (4800.0 / 60.0), 1)
                        s_str = f"{int(s_min)}" if s_min.is_integer() else f"{s_min:.1f}"
                        min_labels.append(f"{s_str} dk")
            min_suffix = f" ({', '.join(min_labels)} @ 4.8 km/s)" if min_labels else ""

            QMessageBox.information(
                self, "Başarılı",
                f"Yürüme izokronları ve pedshed analizi tamamlandı!\n"
                f"Eşikler: {breaks} metre{min_suffix}\n"
                f"Pedshed Oranı < 0.40 çıkan donatılar 'İzole' olarak etiketlendi."
            )
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"İzokron analizi sırasında hata:\n{str(e)}")
        finally:
            self.btn_run_iso.setEnabled(True)

    @staticmethod
    def _to_vector_layer(out_val, default_name="Sonuc Katmani"):
        """processing.run çıktısını (QgsVectorLayer nesnesi, katman ID'si veya dosya yolu) güvenli bir QgsVectorLayer'a çevirir."""
        if isinstance(out_val, QgsVectorLayer):
            return out_val
        if isinstance(out_val, str):
            lyr = QgsProject.instance().mapLayer(out_val)
            if lyr and lyr.isValid():
                return lyr
            if os.path.exists(out_val) or "|" in out_val:
                lyr = QgsVectorLayer(out_val, default_name, "ogr")
                if lyr and lyr.isValid():
                    return lyr
        return None

    @staticmethod
    def _safe_add_map_layer(layer: QgsVectorLayer) -> None:
        """Adds a map layer to QgsProject only if valid and not already registered."""
        if layer and isinstance(layer, QgsVectorLayer) and layer.isValid():
            proj = QgsProject.instance()
            if layer.id() not in proj.mapLayers():
                proj.addMapLayer(layer)

    def _on_fca_fac_layer_changed(self, layer):
        if not layer or not isinstance(layer, QgsVectorLayer) or not layer.isValid():
            self.cmb_fca_id_field.setLayer(None)
            self.cmb_fca_cap_field.setLayer(None)
            return
        self.cmb_fca_id_field.setLayer(layer)
        self.cmb_fca_cap_field.setLayer(layer)

        field_names = [f.name() for f in layer.fields()]
        id_match = next((f for f in field_names if f.lower() in ("ad", "adi", "name", "id", "tesis_adi", "donati_adi")), None)
        if id_match:
            self.cmb_fca_id_field.setField(id_match)

        cap_match = next((f for f in field_names if any(k in f.lower() for k in ("kapasite", "capacity", "ogrenci", "yatak", "kontenjan", "alan"))), None)
        if cap_match:
            self.cmb_fca_cap_field.setField(cap_match)

    def _on_fca_dem_layer_changed(self, layer):
        if not layer or not isinstance(layer, QgsVectorLayer) or not layer.isValid():
            self.cmb_fca_pop_field.setLayer(None)
            return
        self.cmb_fca_pop_field.setLayer(layer)

        field_names = [f.name() for f in layer.fields()]
        pop_match = next((f for f in field_names if any(k in f.lower() for k in ("nufus", "pop", "population", "brut_nufus", "bagimsizbolumsayi", "hane"))), None)
        if pop_match:
            self.cmb_fca_pop_field.setField(pop_match)

    def _on_run_2sfca(self):
        fac_layer = self.cmb_fca_facilities.currentLayer()
        dem_layer = self.cmb_fca_demand.currentLayer()
        road_layer = self.cmb_fca_roads.currentLayer()

        if not fac_layer or not isinstance(fac_layer, QgsVectorLayer) or not fac_layer.isValid():
            QMessageBox.warning(self, "Uyarı", "Lütfen geçerli bir donatı katmanı seçin!")
            return
        if not dem_layer or not isinstance(dem_layer, QgsVectorLayer) or not dem_layer.isValid():
            QMessageBox.warning(self, "Uyarı", "Lütfen geçerli bir talep/nüfus katmanı seçin!")
            return
        if not road_layer or not isinstance(road_layer, QgsVectorLayer) or not road_layer.isValid():
            QMessageBox.warning(self, "Uyarı", "Lütfen geçerli bir yol ağı katmanı seçin!")
            return

        fac_id = self.cmb_fca_id_field.currentField().strip() or None
        cap_field = self.cmb_fca_cap_field.currentField().strip() or None
        pop_field = self.cmb_fca_pop_field.currentField().strip() or None
        default_cap = self.spn_fca_default_cap.value()

        is_dem_poly = (QgsWkbTypes.geometryType(dem_layer.wkbType()) == QgsWkbTypes.GeometryType.PolygonGeometry)
        is_fac_poly = (QgsWkbTypes.geometryType(fac_layer.wkbType()) == QgsWkbTypes.GeometryType.PolygonGeometry)

        params = {
            'NETWORK': road_layer,
            'FACILITIES': fac_layer,
            'FACILITY_ID': fac_id,
            'CAPACITY_FIELD': cap_field,
            'DEFAULT_CAPACITY': default_cap,
            'DEMAND': dem_layer,
            'POP_FIELD': pop_field,
            'MAX_COST': self.spn_fca_cost.value(),
            'FCA_DECAY': 1.0,
            'OUT_FACILITIES': 'TEMPORARY_OUTPUT',
            'OUT_DEMAND': 'TEMPORARY_OUTPUT',
            'OUT_DEMAND_POINTS': 'TEMPORARY_OUTPUT' if is_dem_poly else None,
            'OUT_FACILITY_POINTS': 'TEMPORARY_OUTPUT' if is_fac_poly else None,
        }
        try:
            self.btn_run_fca.setEnabled(False)
            res = processing.run("pln3113:nip_2sfca_yeterlilik", params)
            out_f = res.get('OUT_FACILITIES')
            out_d = res.get('OUT_DEMAND')
            out_d_pts = res.get('OUT_DEMAND_POINTS')
            out_f_pts = res.get('OUT_FACILITY_POINTS')

            lyr_f = self._to_vector_layer(out_f, "2SFCA Donatı Yeterlilik")
            if lyr_f and lyr_f.isValid():
                geom_f_desc = "Poligon" if is_fac_poly else "Noktalar"
                lyr_f.setName(f"2SFCA Donatı Yeterlilik ({fac_layer.name()}) [{geom_f_desc}]")
                style_facility_adequacy_points(lyr_f)
                self._safe_add_map_layer(lyr_f)

            if out_f_pts:
                lyr_f_pts = self._to_vector_layer(out_f_pts, "2SFCA Donatı Giriş Noktaları")
                if lyr_f_pts and lyr_f_pts.isValid():
                    lyr_f_pts.setName(f"2SFCA Donatı Giriş Noktaları ({fac_layer.name()})")
                    style_facility_adequacy_points(lyr_f_pts)
                    self._safe_add_map_layer(lyr_f_pts)

            lyr_d = self._to_vector_layer(out_d, "2SFCA Talep Kapsama")
            if lyr_d and lyr_d.isValid():
                geom_d_desc = "Adalar/Binalar Poligon" if is_dem_poly else "Noktalar"
                lyr_d.setName(f"2SFCA Talep Kapsama ({dem_layer.name()}) [{geom_d_desc}]")
                style_fca_demand_points(lyr_d)
                self._safe_add_map_layer(lyr_d)

            if out_d_pts:
                lyr_d_pts = self._to_vector_layer(out_d_pts, "2SFCA Talep Merkez Noktaları")
                if lyr_d_pts and lyr_d_pts.isValid():
                    lyr_d_pts.setName(f"2SFCA Talep Merkez Noktaları ({dem_layer.name()})")
                    style_fca_demand_points(lyr_d_pts)
                    self._safe_add_map_layer(lyr_d_pts)

            poly_info = "\n\n💡 Girdiğiniz ada/bina/parsel poligon geometrisi korunarak analiz skorlarıyla tematik olarak renklendirildi ve hesaplama merkez noktaları da haritanıza eklendi." if is_dem_poly else ""
            QMessageBox.information(
                self, "Başarılı",
                f"2SFCA Donatı Yeterliliği ve Kapasite Analizi tamamlandı!\n\n"
                f"✅ 1. Donatılar: Yeterli (Yeşil), Aşırı Yüklü (Kırmızı), Kullanılmayan (Gri).\n"
                f"✅ 2. Talep Alanları: Kapsanan (Yeşil) ve Kapsanamayan (Kırmızı) alanlar haritaya eklendi.{poly_info}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"2SFCA analizi sırasında hata:\n{str(e)}")
        finally:
            self.btn_run_fca.setEnabled(True)

    def _on_run_scenario_compare(self):
        road_a = self.cmb_scen_road_a.currentLayer()
        road_b = self.cmb_scen_road_b.currentLayer()
        if not road_a or not isinstance(road_a, QgsVectorLayer):
            QMessageBox.warning(self, "Uyarı", "Lütfen Senaryo A (Mevcut Yol Ağı) katmanını seçin!")
            return
        if not road_b or not isinstance(road_b, QgsVectorLayer):
            QMessageBox.warning(self, "Uyarı", "Lütfen Senaryo B (Meri / Öneri Plan Yol Ağı) katmanını seçin!")
            return

        radius = self.spn_scen_radius.value()
        params = {
            'NETWORK_A': road_a,
            'NETWORK_B': road_b,
            'RADIUS': radius,
            'DIFF_NETWORK': 'TEMPORARY_OUTPUT',
            'SUMMARY_TABLE': 'TEMPORARY_OUTPUT'
        }
        try:
            self.btn_run_scen.setEnabled(False)
            res = processing.run("pln3113:nip_scenario_compare", params)
            diff_out = res.get('DIFF_NETWORK')
            sum_out = res.get('SUMMARY_TABLE')

            lyr_diff = self._to_vector_layer(diff_out, "A/B Fark Haritası")
            if lyr_diff and lyr_diff.isValid():
                lyr_diff.setName(f"A/B Senaryo Fark Haritası (Mevcut vs Meri)")
                style_scenario_diff_network(lyr_diff)
                self._safe_add_map_layer(lyr_diff)

            lyr_sum = self._to_vector_layer(sum_out, "A/B Senaryo Karşılaştırma Karnesi")
            if lyr_sum and lyr_sum.isValid():
                lyr_sum.setName("A/B Senaryo Karşılaştırma Karnesi (Tablo)")
                self._safe_add_map_layer(lyr_sum)

            QMessageBox.information(
                self, "Başarılı",
                f"A/B Senaryo Karşılaştırması tamamlandı!\n"
                f"Fark haritası 4 plan karar başlığına (Kademelenme Revizyonu, Yayalaştırma vb.) göre stillendirildi."
            )
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Senaryo karşılaştırma analizi sırasında hata:\n{str(e)}")
        finally:
            self.btn_run_scen.setEnabled(True)

    def _on_run_on_cephe(self):
        poly_layer = self.cmb_cephe_poly.currentLayer()
        road_layer = self.cmb_cephe_road.currentLayer()
        if not poly_layer or not isinstance(poly_layer, QgsVectorLayer):
            QMessageBox.warning(self, "Uyarı", "Lütfen geçerli bir ada/parsel/bina poligon katmanı seçin!")
            return
        if not road_layer or not isinstance(road_layer, QgsVectorLayer):
            QMessageBox.warning(self, "Uyarı", "Lütfen geçerli bir yol ağı katmanı seçin!")
            return

        params = {
            'INPUT_POLYGONS': poly_layer,
            'INPUT_ROADS': road_layer,
            'MAX_DISTANCE': self.spn_cephe_dist.value(),
            'OUTPUT_LINES': 'TEMPORARY_OUTPUT',
            'OUTPUT_POINTS': 'TEMPORARY_OUTPUT'
        }

        try:
            self.btn_run_cephe.setEnabled(False)
            res = processing.run("pln3113:on_cephe_ve_servis_noktasi_bulucu", params)
            lines_layer = res.get('OUTPUT_LINES')
            pts_layer = res.get('OUTPUT_POINTS')

            lines_layer = self._to_vector_layer(lines_layer, f"Servis Bağlantı Çizgileri ({poly_layer.name()})")
            if lines_layer and lines_layer.isValid():
                lines_layer.setName(f"Servis Bağlantı Çizgileri ({poly_layer.name()})")
                style_front_facade(lines_layer=lines_layer)
                self._safe_add_map_layer(lines_layer)

            pts_layer = self._to_vector_layer(pts_layer, f"Ön Cephe Servis Noktaları - Origin ({poly_layer.name()})")
            if pts_layer and pts_layer.isValid():
                pts_layer.setName(f"Ön Cephe Servis Noktaları - Origin ({poly_layer.name()})")
                style_front_facade(points_layer=pts_layer)
                self._safe_add_map_layer(pts_layer)
                self.cmb_od_origins.setLayer(pts_layer)

            cnt_lines = lines_layer.featureCount() if lines_layer else 0
            cnt_pts = pts_layer.featureCount() if pts_layer else 0
            QMessageBox.information(
                self, "Başarılı",
                f"Ön cephe tespiti ve servis noktaları başarıyla üretildi!\n\n"
                f"1. Servis Bağlantı Çizgileri: {cnt_lines} adet\n"
                f"2. Servis Noktaları (Origin): {cnt_pts} adet\n\n"
                f"Noktalar OD Matrisi menşeler bölümüne otomatik aktarıldı."
            )
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Ön cephe analizi sırasında hata:\n{str(e)}")
        finally:
            self.btn_run_cephe.setEnabled(True)




