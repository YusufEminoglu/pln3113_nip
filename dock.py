# -*- coding: utf-8 -*-
"""Tire NİP ve Kentsel Analiz DockWidget Arayüzü.

DEÜ Mimarlık Fakültesi Şehir ve Bölge Planlama Bölümü
PLN3113 - tire_nip
"""
from __future__ import annotations

import contextlib
import csv
import os
try:
    import processing
except ImportError:
    processing = None
from qgis.PyQt.QtCore import QSize, Qt, QUrl, QVariant
from qgis.PyQt.QtGui import QColor, QDesktopServices, QFont, QIcon
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
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
    QgsDistanceArea,
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
from .core.nip_calculator import NipCalculatorEngine
from .core.nip_dashboard_builder import open_nip_dashboard, build_nip_dashboard_html
from .core.nip_workspace import (
    create_nip_workspace,
    load_nip_layers,
    SCHEMA_MPYY_117,
    SCHEMA_YEREL_NIP,
    create_nip_drawing_workspace,
    load_nip_drawing_layers,
)
from .core.symbology_manager import (
    apply_mpyy_qml_style,
    style_detour_barrier,
    style_facility_adequacy_points,
    style_fca_demand_points,
    style_front_facade,
    style_isochrone_bands,
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
from .ui_theme import studio_stylesheet

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
    """Tire NİP ve Kentsel Analiz Stüdyosu Ana Dock Paneli."""

    def __init__(self, iface, parent=None):
        super().__init__("Tire NİP Analiz Stüdyosu (PLN3113)", parent)
        self.iface = iface
        self.setObjectName("TireNipDockWidget")
        self.setStyleSheet(studio_stylesheet())

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
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        # 1. HEADER BANNER
        header_frame = QFrame()
        header_frame.setObjectName("nipHeaderFrame")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(8, 6, 8, 6)
        header_layout.setSpacing(10)

        icon_label = QLabel()
        icon_label.setObjectName("nipAvatarLabel")
        avatar_path = os.path.join(PLUGIN_DIR, "icons", "avatar.png")
        if not os.path.exists(avatar_path):
            avatar_path = os.path.join(PLUGIN_DIR, "icons", "icon.png")
        if os.path.exists(avatar_path):
            icon_label.setPixmap(QIcon(avatar_path).pixmap(46, 46))
        icon_label.setToolTip("Stüdyo Koordinatörü & PlanX Studio")
        header_layout.addWidget(icon_label)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        lbl_title = QLabel("PLN3113 NİP Analiz Stüdyosu")
        lbl_title.setObjectName("nipHeroTitle")
        title_row.addWidget(lbl_title)

        badge_version = QLabel("v1.0.0")
        badge_version.setObjectName("nipVersionBadge")
        title_row.addWidget(badge_version)
        title_row.addStretch()
        title_box.addLayout(title_row)

        lbl_sub = QLabel("Dokuz Eylül Üniversitesi | PLN3113 Şehir Planlama Projesi III")
        lbl_sub.setObjectName("nipHeaderSubtitle")
        title_box.addWidget(lbl_sub)
        header_layout.addLayout(title_box)
        header_layout.addStretch()

        main_layout.addWidget(header_frame)

        # 2. BODY SPLIT: VERTICAL NAV RAIL + CONTENT STACK
        body_widget = QWidget()
        body_layout = QHBoxLayout(body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(6)

        # Vertical Navigation Rail
        self.nav_list = QListWidget()
        self.nav_list.setObjectName("nipNavRail")
        self.nav_list.setFixedWidth(78)
        self.nav_list.setViewMode(_VIEW_MODE_ICON)
        self.nav_list.setIconSize(QSize(28, 28))
        self.nav_list.setMovement(_MOVEMENT_STATIC)
        self.nav_list.setHorizontalScrollBarPolicy(_SCROLL_OFF)
        self.nav_list.setVerticalScrollBarPolicy(_SCROLL_OFF)
        self.nav_list.setSpacing(4)

        nav_items = [
            ("clean.png", "Geometri", "1. Geometri Onarımı ve Duplike Ayıklama"),
            ("database.png", "Veritabanı", "2. NİP Çizim Veritabanı ve Şablonu (GeoPackage)"),
            ("road.png", "Yol/Kavşak", "3. Yol Platformu, Bordür ve Kavşak Geometrisi"),
            ("plan.png", "NİP & DOP", "4. NİP Nüfus, Donatı (Ek-2) ve DOP Analizi"),
            ("field.png", "Saha/Yapı", "5. Saha ve Bina Fiili Nüfus Kestirimi"),
            ("network.png", "Network", "6. Ulaşım Ağı, Ön Cephe, Erişim Çapları ve OD Matrisi"),
            ("report.png", "Rehber", "7. NİP Metodolojisi, Standartlar ve El Kitabı"),
        ]

        for icon_file, text, tip in nav_items:
            icon_p = os.path.join(PLUGIN_DIR, "icons", icon_file)
            item = QListWidgetItem(QIcon(icon_p) if os.path.exists(icon_p) else QIcon(), text)
            item.setToolTip(tip)
            item.setTextAlignment(_ALIGN_CENTER)
            item.setSizeHint(QSize(70, 52))
            self.nav_list.addItem(item)

        body_layout.addWidget(self.nav_list)

        # Right-side Content Stack wrapped in ScrollArea
        self.main_stack = QStackedWidget()
        self.main_stack.setObjectName("nipMainStack")
        self.main_stack.addWidget(self._create_tab_cleaner())
        self.main_stack.addWidget(self._create_tab_database())
        self.main_stack.addWidget(self._create_tab_roads())
        self.main_stack.addWidget(self._create_tab_nip())
        self.main_stack.addWidget(self._create_tab_field())
        self.main_stack.addWidget(self._create_tab_network())
        self.main_stack.addWidget(self._create_tab_guide())

        stack_scroll = QScrollArea()
        stack_scroll.setWidgetResizable(True)
        stack_scroll.setFrameShape(_NO_FRAME)
        stack_scroll.setWidget(self.main_stack)
        body_layout.addWidget(stack_scroll, 1)

        main_layout.addWidget(body_widget, 1)

        self.nav_list.currentRowChanged.connect(self.main_stack.setCurrentIndex)
        self.nav_list.setCurrentRow(3)  # Default to NİP & DOP tab

        self.tabs = _TabsAdapter(self)

        self.setWidget(container)

    def _open_theoretical_guide(self):
        """A'dan Z'ye teorik metodoloji el kitabını kullanıcının varsayılan tarayıcısında açar."""
        guide_path = os.path.join(PLUGIN_DIR, "docs", "teorik_rehber.html")
        if os.path.exists(guide_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(guide_path))
        else:
            QMessageBox.warning(self, "Uyarı", f"Metodoloji rehberi dosyası bulunamadı:\n{guide_path}")

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

        t_lbl = QLabel("📚 DEÜ ŞBP PLN3113 NİP Metodoloji El Kitabı")
        t_lbl.setStyleSheet("font-weight: 700; font-size: 10pt;")
        intro_lay.addWidget(t_lbl)

        d_lbl = QLabel(
            "Mekânsal Planlar Yapım Yönetmeliği (MPYY), 3194 sayılı İmar Kanunu Madde 18 (DOP) "
            "ve DEÜ Şehir ve Bölge Planlama Bölümü PLN3113 Stüdyo standartlarını içeren "
            "kapsamlı referans ve teorik hesap kütüphanesi."
        )
        d_lbl.setWordWrap(True)
        intro_lay.addWidget(d_lbl)

        btn_launch = QPushButton("  📖 Metodoloji El Kitabını Tarayıcıda Aç (Tam Rehber)")
        btn_launch.setObjectName("PrimaryButton")
        btn_launch.setCursor(_POINTING_HAND)
        btn_launch.clicked.connect(self._open_theoretical_guide)
        intro_lay.addWidget(btn_launch)
        layout.addWidget(card_intro)

        # Resmî Mevzuat ve Bakanlık Standartları Bağlantıları Kartı
        box_links = QGroupBox("Resmî Mevzuat, Yönetmelik ve Bakanlık Standartları")
        links_lay = QVBoxLayout(box_links)
        links_lay.setSpacing(6)

        links_data = [
            (
                "📜 Mekânsal Planlar Yapım Yönetmeliği (MPYY)",
                "https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=19788&MevzuatTur=7&MevzuatTertip=5",
                "Asgari kişi başı kentsel donatı standartları (Ek-2 tablosu) ve plan yapım ilkeleri."
            ),
            (
                "🏢 Planlı Alanlar İmar Yönetmeliği (PAİY)",
                "https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=23722&MevzuatTur=7&MevzuatTertip=5",
                "Yapılaşma şartları, TAKS, KAKS, emsal hesabı, kat yükseklikleri ve bina çekme mesafesi kuralları."
            ),
            (
                "⚖️ 3194 Sayılı İmar Kanunu (Madde 18 - DOP)",
                "https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=3194&MevzuatTur=1&MevzuatTertip=5",
                "Arazi ve arsa düzenlemesi, Düzenleme Ortaklık Payı (%45 yasal tavan) ve kamuya terk edilecek donatılar."
            ),
            (
                "🎨 Bakanlık Resmî Plan Gösterimleri (MPGM)",
                "https://mpgm.csb.gov.tr/plan-gosterimleri-4926",
                "Çevre, Şehircilik ve İklim Değişikliği Bakanlığı resmî gösterim (lejant) standartları ve renk kodları."
            )
        ]

        for title, url, desc in links_data:
            btn_link = QPushButton(f"  {title}")
            btn_link.setCursor(_POINTING_HAND)
            btn_link.setToolTip(f"{desc}\n\nResmî bağlantıyı tarayıcıda aç: {url}")
            btn_link.clicked.connect(lambda checked=False, target_url=url: QDesktopServices.openUrl(QUrl(target_url)))
            links_lay.addWidget(btn_link)

        layout.addWidget(box_links)

        # Quick reference cards
        box_ek2 = QGroupBox("1. MPYY Ek-2 Kentsel Donatı Standartları (Kişi Başı m²)")
        ek2_lay = QVBoxLayout(box_ek2)
        ek2_info = QLabel(
            "• <b>Eğitim Alanları (Toplam 7.0 m²/kişi):</b><br>"
            "  - Anaokulu + İlkokul: 2.5 m²/kişi (Yürüme yarıçapı: 500 m)<br>"
            "  - Ortaokul: 2.0 m²/kişi (Yürüme yarıçapı: 1000 m)<br>"
            "  - Ortaöğretim / Lise: 2.5 m²/kişi (Yürüme yarıçapı: 2500 m)<br>"
            "• <b>Sağlık Tesisleri:</b> 1.5 m²/kişi (Aile Sağlığı, TSM vb.)<br>"
            "• <b>Sosyal ve Kültürel Tesis:</b> 1.5 m²/kişi (Kültür merkezi, gençlik merk.)<br>"
            "• <b>İbadet Alanları:</b> 0.5 m²/kişi (Küçük cami, mescit, orta ibadet)<br>"
            "• <b>Açık ve Yeşil Alanlar:</b> 10.0 m²/kişi (Park, çocuk bahçesi, rekreasyon)<br>"
            "• <b>Teknik Altyapı:</b> 1.0 m²/kişi (Trafo, arıtma, terfi merkezi vb.)<br>"
            "➡️ <i>Toplam Asgari Sosyal ve Teknik Altyapı: <b>21.5 m²/kişi</b></i>"
        )
        ek2_info.setWordWrap(True)
        ek2_lay.addWidget(ek2_info)
        layout.addWidget(box_ek2)

        box_dop = QGroupBox("2. 3194 Sayılı İmar Kanunu Madde 18 & DOP İlkeleri")
        dop_lay = QVBoxLayout(box_dop)
        dop_info = QLabel(
            "• <b>DOP Oranı Formülü:</b> <code>DOP = (Toplam DOP İçi Donatı) / (Toplam Parsel Alanı)</code><br>"
            "• <b>Yasal Tavan:</b> 3194 sayılı Kanun uyarınca azami DOP oranı <b>%45.0</b>'dir.<br>"
            "• <b>Kamu - Özel Ayrımı:</b><br>"
            "  - <i>DOP İçi (Kamusal):</i> Yol, Meydan, Park, Temel Eğitim, İbadet, vb.<br>"
            "  - <i>DOP Dışı (Özel / Tahsis):</i> Konut, Ticaret, Sanayi, Özel Okul, Özel Hastane, Tarım vb."
        )
        dop_info.setWordWrap(True)
        dop_lay.addWidget(dop_info)
        layout.addWidget(box_dop)

        box_field = QGroupBox("3. Fiili Yapı & Saha Nüfusu Kestirim Metodu")
        field_lay = QVBoxLayout(box_field)
        field_info = QLabel(
            "• <b>Formül:</b> <code>Nüfus = (Taban Alanı × Kat Adedi × Konut Payı) ÷ (Ortalama Konut m²) × (Ortalama Hanehalkı)</code><br>"
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
        box_input = QGroupBox("Girdi Poligon Katmanı Seçimi")
        box_layout = QVBoxLayout(box_input)

        lbl = QLabel("Temizlenecek ve Denetlenecek Poligon Katmanı (Örn: nipt_test.gpkg):")
        box_layout.addWidget(lbl)

        self.cmb_clean_layer = QgsMapLayerComboBox()
        self.cmb_clean_layer.setFilters(QgsMapLayerProxyModel.Filter.PolygonLayer)
        box_layout.addWidget(self.cmb_clean_layer)
        layout.addWidget(box_input)

        # 1. Aşama: Topoloji ve Hata Denetimi (Check Validity)
        box_check = QGroupBox("1. Aşama: Topoloji ve Hata Denetimi (Check Validity)")
        check_layout = QVBoxLayout(box_check)

        info_check = QLabel(
            "Orijinal katmana müdahale etmeden QGIS Core geometri geçerlilik algoritmasını çalıştırır; "
            "kendini kesen halkaları (self-intersection), hatalı düğüm noktalarını ve mükerrer poligonları tespit eder."
        )
        info_check.setWordWrap(True)
        info_check.setStyleSheet("color: #475569; font-size: 8pt;")
        check_layout.addWidget(info_check)

        self.btn_run_check_validity = QPushButton("  🔍 Geometri Geçerliliğini ve Hataları Denetle")
        self.btn_run_check_validity.setObjectName("CleanButton")
        self.btn_run_check_validity.setCursor(_POINTING_HAND)
        self.btn_run_check_validity.clicked.connect(self._run_geometry_check_validity)
        check_layout.addWidget(self.btn_run_check_validity)

        # 4 Mini Dashboard Kartı (Grid)
        grid_metrics = QGridLayout()
        grid_metrics.setSpacing(6)

        self.lbl_metric_total = QLabel("Toplam: -")
        self.lbl_metric_total.setStyleSheet("background: #f1f5f9; padding: 6px; border-radius: 6px; font-weight: 600;")
        self.lbl_metric_total.setAlignment(_ALIGN_CENTER)

        self.lbl_metric_invalid = QLabel("Geçersiz: -")
        self.lbl_metric_invalid.setStyleSheet("background: #fee2e2; color: #b91c1c; padding: 6px; border-radius: 6px; font-weight: 700;")
        self.lbl_metric_invalid.setAlignment(_ALIGN_CENTER)

        self.lbl_metric_duplicate = QLabel("Mükerrer: -")
        self.lbl_metric_duplicate.setStyleSheet("background: #fef3c7; color: #b45309; padding: 6px; border-radius: 6px; font-weight: 700;")
        self.lbl_metric_duplicate.setAlignment(_ALIGN_CENTER)

        self.lbl_metric_valid = QLabel("Geçerli: -")
        self.lbl_metric_valid.setStyleSheet("background: #dcfce7; color: #15803d; padding: 6px; border-radius: 6px; font-weight: 700;")
        self.lbl_metric_valid.setAlignment(_ALIGN_CENTER)

        grid_metrics.addWidget(self.lbl_metric_total, 0, 0)
        grid_metrics.addWidget(self.lbl_metric_invalid, 0, 1)
        grid_metrics.addWidget(self.lbl_metric_duplicate, 0, 2)
        grid_metrics.addWidget(self.lbl_metric_valid, 0, 3)
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

        lbl_zoom_hint = QLabel("💡 <i>Tablodaki herhangi bir hata satırına tıklayarak harita tuvalinde doğrudan o geometriye odaklanabilirsiniz.</i>")
        lbl_zoom_hint.setStyleSheet("color: #64748b; font-size: 7.5pt;")
        check_layout.addWidget(lbl_zoom_hint)

        self.btn_add_error_points = QPushButton("  📍 Hata Noktalarını Haritaya Ekle (Point Layer)")
        self.btn_add_error_points.setCursor(_POINTING_HAND)
        self.btn_add_error_points.setEnabled(False)
        self.btn_add_error_points.clicked.connect(self._add_error_points_to_map)
        check_layout.addWidget(self.btn_add_error_points)

        layout.addWidget(box_check)

        # 2. Aşama: Akıllı Onarım ve Tekilleştirme (Fix & Deduplicate)
        box_fix = QGroupBox("2. Aşama: Akıllı Onarım ve Tekilleştirme (Fix & Deduplicate)")
        fix_layout = QVBoxLayout(box_fix)

        info_fix = QLabel(
            "Bozuk geometrileri <code>makeValid()</code> ve sıfır-tampon motoruyla onarır, "
            "aynı alanı kaplayan mükerrer poligonları tekilleştirir. Temiz katman üretilerek "
            "2. Sekme (NİP Analizi) için otomatik atanır."
        )
        info_fix.setWordWrap(True)
        info_fix.setStyleSheet("color: #475569; font-size: 8pt;")
        fix_layout.addWidget(info_fix)

        self.btn_run_clean = QPushButton("  ⚡ Geometriyi Otomatik Onar ve Duplikeleri Ayıkla")
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
                    item_tur.setForeground(QColor("#dc2626"))
                elif "Mükerrer" in h["hata_turu"]:
                    item_tur.setForeground(QColor("#d97706"))

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
                f"• Ayıklanan Mükerrer (Duplike) Poligon: <b style='color:#dc2626;'>{stats['duplike_elenen']:,}</b> (%{dup_oran})<br>"
                f"• Onarılan Geçersiz Geometri: <b>{stats['gecersiz_onarilan']:,}</b><br>"
                f"• Temiz Çıktı Obje Sayısı: <b style='color:#16a34a;'>{stats['temiz_cikan']:,}</b><br>"
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
            self.txt_clean_log.append(f"<span style='color:red;'>Hata: {str(e)}</span>")
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

        t_lbl = QLabel("🗄️ 1/5000 Nazım İmar Planı (NİP) Çizim Veritabanı ve Şablonu")
        t_lbl.setStyleSheet("font-weight: 700; font-size: 10pt; color: #0f766e;")
        info_lay.addWidget(t_lbl)

        d_lbl = QLabel(
            "Mekânsal Planlar Yapım Yönetmeliği (MPYY) standartlarına birebir uygun, "
            "resmi çizgi/alan lejant stilleri, hiyerarşik öznitelik formları, açılır menü (Value Map) "
            "kodlamaları ve 1-N ilişkileri (Relations) içeren hazır GeoPackage (.gpkg) çalışma alanı üretir."
        )
        d_lbl.setWordWrap(True)
        d_lbl.setStyleSheet("color: #475569; font-size: 8.5pt;")
        info_lay.addWidget(d_lbl)
        layout.addWidget(card_info)

        # Hedef Veritabanı Konumu ve CRS
        box_db = QGroupBox("Veritabanı Şeması ve Dosya Konumu")
        form_db = QFormLayout(box_db)
        form_db.setSpacing(8)

        # Şema Seçici (MPYY 1.1.7 vs Yerel NİP)
        self.cmb_db_schema = QComboBox()
        self.cmb_db_schema.addItem("🏛️ Resmî MPYY 1.1.7 XSD Şeması (Bakanlık e-Plan & Ek-1e - 87 Katman)", SCHEMA_MPYY_117)
        self.cmb_db_schema.addItem("📐 PLN3113 Yerel NİP Şablonu (MpyyNipDB 1/5000 - 5 Katman + Tablo + QML)", SCHEMA_YEREL_NIP)
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
        box_opts = QGroupBox("Otomasyon ve Proje Entegrasyon Seçenekleri")
        opts_lay = QVBoxLayout(box_opts)
        opts_lay.setSpacing(6)

        self.chk_db_load_layers = QCheckBox("Üretilen katmanları mevcut QGIS projesine otomatik ekle")
        self.chk_db_load_layers.setChecked(True)
        opts_lay.addWidget(self.chk_db_load_layers)

        self.chk_db_apply_styles = QCheckBox("MPYY resmî lejant stillerini (.qml / SLD) otomatik bağla")
        self.chk_db_apply_styles.setChecked(True)
        opts_lay.addWidget(self.chk_db_apply_styles)

        self.chk_db_setup_forms = QCheckBox("Hiyerarşik öznitelik formlarını ve açılır menü (Value Map) kurallarını kur")
        self.chk_db_setup_forms.setChecked(True)
        opts_lay.addWidget(self.chk_db_setup_forms)

        self.chk_db_setup_relations = QCheckBox("Çoklu fonksiyon ilişkilerini (Relations: alanlar-5000 <-> fonksiyonlar) aktifleştir")
        self.chk_db_setup_relations.setChecked(True)
        opts_lay.addWidget(self.chk_db_setup_relations)

        layout.addWidget(box_opts)

        # Buton
        self.btn_create_db = QPushButton("  🚀 MPYY 1.1.7 NİP Çizim Veritabanını Oluştur ve Katmanları Yükle")
        self.btn_create_db.setObjectName("PrimaryButton")
        self.btn_create_db.setCursor(_POINTING_HAND)
        self.btn_create_db.clicked.connect(self._on_create_database)
        layout.addWidget(self.btn_create_db)

        # Bilgilendirme Kartı: Üretilecek Katman Şeması
        self.box_schema = QGroupBox("Oluşturulacak Resmî MPYY 1.1.7 NİP Katmanları ve Hiyerarşisi")
        schema_lay = QVBoxLayout(self.box_schema)
        self.schema_html = QLabel(
            "<div style='font-size:8.5pt; color:#334155; line-height:1.45;'>"
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
            self.btn_create_db.setText("  🚀 PLN3113 Yerel NİP Veritabanını Oluştur ve Katmanları Yükle")
            self.box_schema.setTitle("Oluşturulacak PLN3113 Yerel NİP (MpyyNipDB) Katmanları")
            self.schema_html.setText(
                "<div style='font-size:8.5pt; color:#334155; line-height:1.45;'>"
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
            self.btn_create_db.setText("  🚀 MPYY 1.1.7 NİP Çizim Veritabanını Oluştur ve Katmanları Yükle")
            self.box_schema.setTitle("Oluşturulacak Resmî MPYY 1.1.7 NİP Katmanları ve Hiyerarşisi")
            self.schema_html.setText(
                "<div style='font-size:8.5pt; color:#334155; line-height:1.45;'>"
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

        t_lbl = QLabel("🛣️ Yol Platformu, Bordür ve Kavşak Geometrisi Modülü")
        t_lbl.setStyleSheet("font-weight: 700; font-size: 10pt; color: #0f766e;")
        info_lay.addWidget(t_lbl)

        d_lbl = QLabel(
            "Ulaşım aksı orta çizgilerinden yasal yol genişliklerine göre platform sınırları, "
            "orta refüj ve kaldırım/bordür hatları üretir; kavşak yaklaşımlarını kırpar ve "
            "dış sınırları otomatik poligonlaştırarak NİP imar adalarıyla eşleştirir."
        )
        d_lbl.setWordWrap(True)
        d_lbl.setStyleSheet("color: #475569; font-size: 8.5pt;")
        info_lay.addWidget(d_lbl)
        layout.addWidget(card_info)

        # 1. Bölüm: Yol Platformu & Bordür Üretici
        box_plat = QGroupBox("1. Aşama: Yol Platformu, Refüj ve Bordür/Kaldırım Üretimi")
        lay_plat = QVBoxLayout(box_plat)
        lay_plat.setSpacing(6)

        form_plat = QFormLayout()
        form_plat.setSpacing(6)

        self.cmb_road_layer = QgsMapLayerComboBox()
        self.cmb_road_layer.setFilters(QgsMapLayerProxyModel.Filter.LineLayer)
        form_plat.addRow("Yol Orta Çizgisi Katmanı:", self.cmb_road_layer)

        self.cmb_road_width_field = QComboBox()
        self.cmb_road_layer.layerChanged.connect(self._on_road_layer_changed)
        form_plat.addRow("Yol Genişliği Alanı (Örn: GENISLIK):", self.cmb_road_width_field)

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

        self.btn_run_platform = QPushButton("  📐 Yol Platformu ve Kaldırım Çizgilerini Üret")
        self.btn_run_platform.setObjectName("PrimaryButton")
        self.btn_run_platform.setCursor(_POINTING_HAND)
        self.btn_run_platform.clicked.connect(self._on_run_road_platform)
        lay_plat.addWidget(self.btn_run_platform)
        layout.addWidget(box_plat)

        # 2. Bölüm: Kavşak Geometrisi & Yaklaşım Kırpma
        box_kavsak = QGroupBox("2. Aşama: Kavşak Geometrisi ve Yaklaşım Kırpma (5m Trim)")
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

        self.btn_run_kavsak = QPushButton("  ✂️ Kavşak Hatlarını Kırp ve Yaklaşımları Ayır")
        self.btn_run_kavsak.setObjectName("SecondaryButton")
        self.btn_run_kavsak.setCursor(_POINTING_HAND)
        self.btn_run_kavsak.clicked.connect(self._on_run_kavsak_trim)
        lay_kavsak.addWidget(self.btn_run_kavsak)
        layout.addWidget(box_kavsak)

        # 3. Bölüm: Yol Poligonlaştırma ve Plan Alanı Eşleştirme
        box_poly = QGroupBox("3. Aşama: Yol Dış Çizgilerini Poligonlaştırma ve Fonksiyon Eşleştirme")
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

        self.btn_run_poly = QPushButton("  🔄 Yolları Poligonlaştır ve Plan Fonksiyonlarına Bağla")
        self.btn_run_poly.setObjectName("AccentButton")
        self.btn_run_poly.setCursor(_POINTING_HAND)
        self.btn_run_poly.clicked.connect(self._on_run_road_polygonize)
        lay_poly.addWidget(self.btn_run_poly)
        layout.addWidget(box_poly)

        layout.addStretch()

        # Trigger initial field population
        self._on_road_layer_changed()

        return tab

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
    def _create_tab_nip(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Bilgi Barı
        info_banner = QWidget()
        info_banner.setStyleSheet("background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 6px; padding: 4px;")
        info_l = QHBoxLayout(info_banner)
        info_l.setContentsMargins(6, 4, 6, 4)
        lbl_hint = QLabel("💡 <b>Tire NİP Metodolojisi:</b> Nüfus aralıkları, MPYY Ek-2 standartları, DOP ve yol formülleri.")
        lbl_hint.setStyleSheet("color: #1e40af; font-size: 11px;")
        btn_hint_guide = QPushButton("📖 Metodoloji El Kitabı")
        btn_hint_guide.setCursor(_POINTING_HAND)
        btn_hint_guide.setStyleSheet("background: #2563eb; color: white; border-radius: 4px; padding: 3px 8px; font-size: 11px; font-weight: bold;")
        btn_hint_guide.clicked.connect(self._open_theoretical_guide)
        info_l.addWidget(lbl_hint)
        info_l.addStretch()
        info_l.addWidget(btn_hint_guide)
        layout.addWidget(info_banner)

        # 1. Girdi Kutusu
        box_nip = QGroupBox("NİP & Fiziki Mevcut Durum Katmanı ve Parametreler")
        f_layout = QFormLayout(box_nip)

        self.cmb_analysis_mode = QComboBox()
        self.cmb_analysis_mode.addItem("Nazım İmar Planı (NİP - Öneri / Revizyon)")
        self.cmb_analysis_mode.addItem("Fiziki Mevcut Durum (TUCBS / Arazi Kullanımı)")
        self.cmb_analysis_mode.currentIndexChanged.connect(self._on_analysis_mode_changed)
        f_layout.addRow("Analiz Modu / Kapsam:", self.cmb_analysis_mode)

        self.cmb_nip_layer = QgsMapLayerComboBox()
        self.cmb_nip_layer.setFilters(QgsMapLayerProxyModel.Filter.PolygonLayer)
        self.cmb_nip_layer.layerChanged.connect(self._on_nip_layer_changed)
        f_layout.addRow("Analiz Katmanı (Poligon):", self.cmb_nip_layer)

        self.cmb_fonk_field = QComboBox()
        self.cmb_fonk_field.currentTextChanged.connect(self._on_fonk_col_changed)
        f_layout.addRow("Birincil Fonksiyon / TUCBS Sütunu:", self.cmb_fonk_field)

        self.cmb_secondary_fonk_field = QComboBox()
        self.cmb_secondary_fonk_field.currentTextChanged.connect(self._on_fonk_col_changed)
        f_layout.addRow("Tamamlayıcı / İkincil Sütun (Opsiyonel):", self.cmb_secondary_fonk_field)

        self.cmb_sinir_layer = QgsMapLayerComboBox()
        self.cmb_sinir_layer.setFilters(QgsMapLayerProxyModel.Filter.PolygonLayer)
        self.cmb_sinir_layer.setAllowEmptyLayer(True)
        self.cmb_sinir_layer.layerChanged.connect(self._on_sinir_layer_changed)
        f_layout.addRow("Plan Onama Sınırı (Opsiyonel):", self.cmb_sinir_layer)

        self.cmb_sinir_modu = QComboBox()
        self.cmb_sinir_modu.addItem("✂️ Sınırla Kırp / Kes (Clip - Önerilen)", "clip")
        self.cmb_sinir_modu.addItem("➕ Sınıra Değenleri Dahil Et (Intersect - Bütün Al)", "intersect")
        self.cmb_sinir_modu.addItem("⛔ Kesişenleri Hariç Tut (Within - Sadece %100 İçeridekiler)", "within")
        self.cmb_sinir_modu.addItem("🎯 Ağırlık Merkezine Göre (Centroid - Merkezi İçerideyse Al)", "centroid")
        f_layout.addRow("Sınır Kırpma / Kesişim Modu:", self.cmb_sinir_modu)

        self.lbl_sinir_foolproof = QLabel(
            "<b>💡 Öğrenci Kılavuzu — Plan Onama Sınırı & Kesişim Mantığı:</b><br>"
            "• <b>Sınır Dışındaki Adalar:</b> Belirlediğiniz Plan Onama Sınırının <u>tamamen dışında</u> kalan "
            "tüm ada ve poligonlar analize KESİNLİKLE dahil edilmez (otomatik filtrelenip elenir).<br>"
            "• <b>Sınırı Aşan / Kısmen Dışarı Taşan Adalar İçin Seçenekler:</b><br>"
            "&nbsp;&nbsp;<b>1. Sınırla Kırp / Kes (Clip - Önerilen):</b> Taşan kısmı tam sınır çizgisinden keser, "
            "sadece sınır içinde kalan net parçayı ve nüfusu hesaba katar.<br>"
            "&nbsp;&nbsp;<b>2. Sınıra Değenleri Dahil Et (Intersect):</b> Adanın ucu dahi sınıra giriyorsa adayı bölmeden tamamını analize katar.<br>"
            "&nbsp;&nbsp;<b>3. Kesişenleri Hariç Tut (Within):</b> Dışarıya 1 mm bile taşan adaları tamamen eler; sadece %100 içeride kalanları alır.<br>"
            "&nbsp;&nbsp;<b>4. Ağırlık Merkezine Göre (Centroid):</b> Adanın ağırlık merkezi sınır içindeyse tamamını alır, dışındaysa eler."
        )
        self.lbl_sinir_foolproof.setWordWrap(True)
        self.lbl_sinir_foolproof.setStyleSheet(
            "background: #fffbeb; border: 1px solid #fde047; border-radius: 6px; "
            "padding: 8px; font-size: 11px; color: #854d0e; line-height: 140%;"
        )
        f_layout.addRow(self.lbl_sinir_foolproof)

        self.cmb_yol_layer = QgsMapLayerComboBox()
        self.cmb_yol_layer.setFilters(QgsMapLayerProxyModel.Filter.LineLayer)
        self.cmb_yol_layer.setAllowEmptyLayer(True)
        f_layout.addRow("Yol Aksları Katmanı (Opsiyonel):", self.cmb_yol_layer)

        self.spn_proj_nufus = QSpinBox()
        self.spn_proj_nufus.setRange(1000, 500000)
        self.spn_proj_nufus.setValue(65000)
        self.spn_proj_nufus.setSingleStep(1000)
        self.spn_proj_nufus.setSuffix(" Kişi")
        f_layout.addRow("Projeksiyon Hedef Nüfusu:", self.spn_proj_nufus)

        layout.addWidget(box_nip)

        # 2. Planlama, DOP, İstihdam & Yolculuk Kuralları (Dahil / Hariç) - Açılır Kutu
        self.box_rules = QGroupBox("⚙️ İstihdam, Yolculuk & DOP Kuralları (Dahil / Hariç ve Katsayılar)")
        self.box_rules.setCheckable(True)
        self.box_rules.setChecked(False)  # Başlangıçta derli toplu dursun
        rules_layout = QVBoxLayout(self.box_rules)

        lbl_rules_info = QLabel(
            "<b>Dahil / Hariç Düzeni:</b> Varsayılan planlama katsayıları ve DOP kapsamı aktiftir. "
            "İstediğiniz fonksiyonu DOP içi (düzenlemeye dahil) veya nDOP / DOP Dışı (harice ayrılan) olarak seçebilir; "
            "istihdam veya yolculuktan hariç tutabilir ya da katsayılarını değiştirebilirsiniz."
        )
        lbl_rules_info.setWordWrap(True)
        lbl_rules_info.setStyleSheet("color: #0f766e; font-size: 11px; background: #f0fdfa; padding: 6px; border-radius: 4px;")
        rules_layout.addWidget(lbl_rules_info)

        btn_rules_bar = QHBoxLayout()
        self.btn_load_fonks = QPushButton("🔄 Katmandan Fonksiyonları Oku")
        self.btn_load_fonks.clicked.connect(self._load_rules_table_from_layer)
        self.btn_reset_rules = QPushButton("Varsayılanlara Sıfırla")
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

        # 3. Nüfus Gösterge & Kıyaslama Tablosu
        box_bench = QGroupBox("Tire Tarihsel Nüfus ve Projeksiyon Gösterge Paneli")
        bench_layout = QVBoxLayout(box_bench)

        self.tbl_benchmark = QTableWidget(5, 4)
        self.tbl_benchmark.setHorizontalHeaderLabels([
            "Nüfus Niteliği / Kapsam", "Kentsel Merkez", "Kırsal Nüfus", "İlçe Toplamı"
        ])
        self.tbl_benchmark.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_benchmark.verticalHeader().setVisible(False)
        self.tbl_benchmark.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_benchmark.setMaximumHeight(140)

        bench_rows = [
            ("1997 Plan Raporu (1990 DİE)", "37.855", "39.459 (65 Köy)", "77.314"),
            ("2015 Plan Projeksiyonu (Hedef)", "53.629", "46.711 (Model)", "100.340"),
            ("2015 TÜİK ADNKS (Gerçekleşen)", "~57.069", "~25.033", "82.102"),
            ("Güncel TÜİK ADNKS (2025/2026)", "~61.738", "~25.833", "87.571"),
            ("Hesaplanan 1/5000 NİP Kapasitesi", "Hesaplanmadı", "-", "Hesaplanmadı")
        ]
        for r_idx, (k, m, r, i) in enumerate(bench_rows):
            self.tbl_benchmark.setItem(r_idx, 0, QTableWidgetItem(k))
            self.tbl_benchmark.setItem(r_idx, 1, QTableWidgetItem(m))
            self.tbl_benchmark.setItem(r_idx, 2, QTableWidgetItem(r))
            self.tbl_benchmark.setItem(r_idx, 3, QTableWidgetItem(i))

        font = QFont()
        font.setBold(True)
        for c in range(4):
            item = self.tbl_benchmark.item(4, c)
            if item:
                item.setFont(font)
                item.setForeground(QColor("#0f766e"))

        bench_layout.addWidget(self.tbl_benchmark)

        lbl_bench_note = QLabel(
            "<small style='color:#64748b;'>📌 <i>6360 sayılı yasa sonrası köyler mahalleye dönüştüğünden 2015 ve güncel kentsel merkez, "
            "yerleşik leke içindeki mahalleler toplamıdır. Kırsal nüfus farktan elde edilmiştir. "
            "Güncel resmi veri 31 Aralık 2025 referanslı kütüktür (87.571 kişi).</i></small>"
        )
        lbl_bench_note.setWordWrap(True)
        bench_layout.addWidget(lbl_bench_note)
        layout.addWidget(box_bench)

        # 4. Çalıştır Butonu
        self.btn_run_nip = QPushButton("  PLN3113 NİP Nüfus, Donatı, Kamu-Özel ve DOP Analizini Başlat")
        self.btn_run_nip.setObjectName("PrimaryButton")
        plan_icon_path = os.path.join(PLUGIN_DIR, "icons", "plan.png")
        if os.path.exists(plan_icon_path):
            self.btn_run_nip.setIcon(QIcon(plan_icon_path))
        self.btn_run_nip.clicked.connect(self._run_nip_analysis)
        layout.addWidget(self.btn_run_nip)

        # 5. Dışa Aktarma Buton Çubuğu
        export_bar = QHBoxLayout()
        self.btn_export_csv = QPushButton("  Tabloları CSV (Excel) Kaydet")
        self.btn_export_csv.clicked.connect(self._export_nip_tables_csv)
        self.btn_export_csv.setEnabled(False)

        self.btn_export_html = QPushButton("  Raporu HTML Kaydet")
        self.btn_export_html.clicked.connect(self._export_nip_report_html)
        self.btn_export_html.setEnabled(False)

        export_bar.addWidget(self.btn_export_csv)
        export_bar.addWidget(self.btn_export_html)
        layout.addLayout(export_bar)

        # Canlı Görsel Göstergeler (Mikro-Barlar)
        box_kpi_gauges = QGroupBox("Canlı Yasal Oran Göstergeleri")
        lay_kpi = QVBoxLayout(box_kpi_gauges)
        lay_kpi.setSpacing(6)

        row_dop_bar = QHBoxLayout()
        lbl_dop_bar = QLabel("DOP Oranı (Hedef %45.0):")
        lbl_dop_bar.setStyleSheet("font-weight: 600; font-size: 8.5pt;")
        self.bar_dop = QProgressBar()
        self.bar_dop.setRange(0, 80)
        self.bar_dop.setValue(0)
        self.bar_dop.setTextVisible(True)
        self.bar_dop.setFormat("%v.0% / %45.0")
        self.bar_dop.setStyleSheet("QProgressBar::chunk { background-color: #10b981; }")
        self.lbl_dop_badge = QLabel("-")
        self.lbl_dop_badge.setStyleSheet("font-size: 8pt; font-weight: 700; padding: 2px 6px; border-radius: 4px; background: #e2e8f0;")
        row_dop_bar.addWidget(lbl_dop_bar)
        row_dop_bar.addWidget(self.bar_dop, 1)
        row_dop_bar.addWidget(self.lbl_dop_badge)
        lay_kpi.addLayout(row_dop_bar)

        row_yesil_bar = QHBoxLayout()
        lbl_yesil_bar = QLabel("PAİY Md.9 Açık-Yeşil (Hedef %75):")
        lbl_yesil_bar.setStyleSheet("font-weight: 600; font-size: 8.5pt;")
        self.bar_yesil = QProgressBar()
        self.bar_yesil.setRange(0, 100)
        self.bar_yesil.setValue(0)
        self.bar_yesil.setTextVisible(True)
        self.bar_yesil.setFormat("%v.0% / %75.0")
        self.bar_yesil.setStyleSheet("QProgressBar::chunk { background-color: #22c55e; }")
        self.lbl_yesil_badge = QLabel("-")
        self.lbl_yesil_badge.setStyleSheet("font-size: 8pt; font-weight: 700; padding: 2px 6px; border-radius: 4px; background: #e2e8f0;")
        row_yesil_bar.addWidget(lbl_yesil_bar)
        row_yesil_bar.addWidget(self.bar_yesil, 1)
        row_yesil_bar.addWidget(self.lbl_yesil_badge)
        lay_kpi.addLayout(row_yesil_bar)

        layout.addWidget(box_kpi_gauges)

        # İnteraktif Dashboard Butonu
        self.btn_open_dashboard = QPushButton("  📊 İnteraktif NİP & DOP Dashboard Raporunu Aç (Plotly + Leaflet)")
        self.btn_open_dashboard.setObjectName("AccentButton")
        self.btn_open_dashboard.setCursor(_POINTING_HAND)
        self.btn_open_dashboard.setEnabled(False)
        self.btn_open_dashboard.clicked.connect(self._open_nip_dashboard)
        layout.addWidget(self.btn_open_dashboard)

        # Katman Lejantı ve Stil Değiştirme Çubuğu
        style_nip_bar = QHBoxLayout()
        self.btn_style_density = QPushButton("  📊 Yoğunluk (UST_SNR)")
        self.btn_style_density.setCursor(_POINTING_HAND)
        self.btn_style_density.setEnabled(False)
        self.btn_style_density.clicked.connect(self._apply_density_style_nip)

        self.btn_style_mpyy = QPushButton("  🎨 Resmî MPYY Lejantı")
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
        self.cmb_fonk_field.clear()
        self.cmb_secondary_fonk_field.clear()
        self.cmb_secondary_fonk_field.addItem("<Yok / İkincil Sütun Yok>")
        if not layer or not isinstance(layer, QgsVectorLayer):
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
            # Fiziki Mevcut Durum Modu (TUCBS)
            self.cmb_analysis_mode.setCurrentIndex(1)
            if "tucbs_sinifi" in fields_lower:
                self.cmb_fonk_field.setCurrentText(fields_lower["tucbs_sinifi"])
            elif "arazi_kullanim_tanimi" in fields_lower:
                self.cmb_fonk_field.setCurrentText(fields_lower["arazi_kullanim_tanimi"])

            if "arazi_kullanim_tanimi" in fields_lower and self.cmb_fonk_field.currentText() != fields_lower["arazi_kullanim_tanimi"]:
                self.cmb_secondary_fonk_field.setCurrentText(fields_lower["arazi_kullanim_tanimi"])
        else:
            # Standart NİP Modu
            self.cmb_analysis_mode.setCurrentIndex(0)
            priority = ["Ort__Detay", "Ort_Detay", "nipfonksiyon", "plan_fonksiyon", "fonksiyon", "Kullan__m_"]
            for p in priority:
                if p in fields:
                    self.cmb_fonk_field.setCurrentText(p)
                    break
            self.cmb_secondary_fonk_field.setCurrentIndex(0)

        # Fonksiyon tablosunu katmandan otomatik doldur
        self._load_rules_table_from_layer()

    def _on_fonk_col_changed(self, col_name: str = ""):
        self._load_rules_table_from_layer(preserve_custom=False)

    def _on_sinir_layer_changed(self):
        has_sinir = (self.cmb_sinir_layer.currentLayer() is not None)
        self.cmb_sinir_modu.setEnabled(has_sinir)
        if hasattr(self, 'lbl_sinir_foolproof'):
            if has_sinir:
                self.lbl_sinir_foolproof.setStyleSheet(
                    "background: #fffbeb; border: 1px solid #fde047; border-radius: 6px; "
                    "padding: 8px; font-size: 11px; color: #854d0e; line-height: 140%;"
                )
            else:
                self.lbl_sinir_foolproof.setStyleSheet(
                    "background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; "
                    "padding: 8px; font-size: 11px; color: #64748b; line-height: 140%;"
                )

    def _load_rules_table_from_layer(self, preserve_custom: bool = True):
        """Seçili katmandaki fonksiyonları okuyup kurallar tablosuna doldurur.
        Daha önce yapılmış kullanıcı özelleştirmeleri varsa korur, yeni fonksiyonlar için varsayılanları atar.
        """
        layer = self.cmb_nip_layer.currentLayer()
        col = self.cmb_fonk_field.currentText()
        if not layer or not isinstance(layer, QgsVectorLayer) or not col:
            return

        idx = layer.fields().indexOf(col)
        if idx == -1:
            return

        sec_col = self.cmb_secondary_fonk_field.currentText() if hasattr(self, 'cmb_secondary_fonk_field') else ""
        sec_idx = layer.fields().indexOf(sec_col) if sec_col and not sec_col.startswith("<") else -1

        unique_fonks_set = set()
        for feat in layer.getFeatures():
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

        unique_fonks = sorted(list(unique_fonks_set))
        if not unique_fonks:
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

    def _populate_dop_table(self, dop: dict):
        """DOP ve Kamu-Özel Dengesi Tablosunu oluşturur ve biçimlendirir."""
        headers = ["Parametre", "Alan (m²)", "Alan (ha)", "Oran (%)", "Açıklama / Yasal Durum"]
        p_m2 = dop["toplam_plan_alani_m2"]
        e_m2 = dop["dop_esas_alan_m2"]
        sinir_aciklama = "Plan Onama Sınırına Göre Kesin" if dop.get("sinir_katmani_kullanildi") else "İmar Adaları Toplamı Esas Alındı"

        rows = [
            ["Plan Onama Sınırı / Toplam Alan", f"{p_m2:,.0f} m²", f"{dop['toplam_plan_alani_ha']:.2f} ha", "100.0 %", sinir_aciklama],
            ["İmar Adaları (Kullanım Poligonları)", f"{dop['adalar_toplam_m2']:,.0f} m²", f"{dop['adalar_toplam_ha']:.2f} ha", f"{(dop['adalar_toplam_m2']/max(1, p_m2)*100.0):.2f} %", "Plan Fonksiyon Blokları"],
            ["Net Yol ve Ulaşım Ağı Alanı", f"{dop['hesaplanan_yol_m2']:,.0f} m²", f"{dop['hesaplanan_yol_ha']:.2f} ha", f"% {dop['yol_orani_yuzde']:.2f}", "Plan Sınırı - İmar Adaları Boşluğu"],
            ["Kişi Başına Düşen Yol Standardı", "-", "-", f"{dop['kisi_basi_yol_m2']:.2f} m²/k", "Üst Plan Nüfusuna Göre Yol Standardı"],
            ["DOP Dışı Alanlar (Harice Ayrılan)", f"{dop['dop_disi_alan_m2']:,.0f} m²", f"{(dop['dop_disi_alan_m2']/10000.0):.2f} ha", f"{(dop['dop_disi_alan_m2']/max(1, p_m2)*100.0):.2f} %", "Orman, Tarım, Su vb."],
            ["Düzenleme Sahası (DOP Esas Alan)", f"{e_m2:,.0f} m²", f"{(e_m2/10000.0):.2f} ha", f"{(e_m2/max(1, p_m2)*100.0):.2f} %", "Düzenlemeye Giren Net Saha"],
            ["Toplam Özel Mülkiyet (Tahsis)", f"{dop['toplam_ozel_tahsis_m2']:,.0f} m²", f"{(dop['toplam_ozel_tahsis_m2']/10000.0):.2f} ha", f"{(dop['toplam_ozel_tahsis_m2']/max(1, e_m2)*100.0):.2f} %", "Konut, Ticaret, Sanayi vb."],
            ["Kamu Poligon Donatıları", f"{dop['kamu_poligonlar_m2']:,.0f} m²", f"{(dop['kamu_poligonlar_m2']/10000.0):.2f} ha", f"{(dop['kamu_poligonlar_m2']/max(1, e_m2)*100.0):.2f} %", "Eğitim, Sağlık, Yeşil vb."],
            ["Toplam Kamu Kesintisi (DOP)", f"{dop['toplam_kamu_kesinti_m2']:,.0f} m²", f"{(dop['toplam_kamu_kesinti_m2']/10000.0):.2f} ha", f"% {dop['dop_orani']:.2f}", "Donatılar + Gerçek Yol Ağı"],
            ["Kamu / Özel Mülkiyet Oranı", "-", "-", f"% {dop['kamu_ozel_orani']:.2f}", "Kamu Kesintisi / Özel Tahsis Oranı"],
            ["HESAPLANAN DOP ORANI (%)", "-", "-", f"% {dop['dop_orani']:.2f}", dop['dop_uygunluk']]
        ]
        if dop.get("ortalama_yol_genisligi_m"):
            rows.insert(4, ["Ortalama Fiili Yol Genişliği", "-", f"{dop['yol_agi_uzunlugu_km']:.2f} km Yol", f"{dop['ortalama_yol_genisligi_m']:.2f} m", "Yol Alanı / Hat Uzunluğu"])

        self._populate_table(self.tbl_dop, headers, rows)
        bold_font = QFont()
        bold_font.setBold(True)
        color = QColor("#16a34a") if dop["dop_orani"] <= 45.0 else QColor("#dc2626")
        last_idx = len(rows) - 1
        for col in range(5):
            it = self.tbl_dop.item(last_idx, col)
            if it:
                it.setFont(bold_font)
                it.setForeground(color)

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
                it.setForeground(QColor("#16a34a") if ek["durum_ust"] == "YETERLİ" else QColor("#dc2626"))
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
            da = QgsDistanceArea()
            da.setSourceCrs(layer.sourceCrs(), QgsProject.instance().transformContext())
            da.setEllipsoid(QgsProject.instance().ellipsoid() or 'WGS84')

            # 1. Plan Onama Sınırı Geometrisi
            sinir_layer = self.cmb_sinir_layer.currentLayer()
            sinir_geom = None
            if sinir_layer and isinstance(sinir_layer, QgsVectorLayer):
                geoms = [f.geometry() for f in sinir_layer.getFeatures() if f.geometry() and not f.geometry().isEmpty()]
                if geoms:
                    sinir_geom = QgsGeometry.unaryUnion(geoms)

            sinir_modu = "clip"
            if hasattr(self, 'cmb_sinir_modu'):
                cur_data = self.cmb_sinir_modu.currentData()
                if cur_data:
                    sinir_modu = str(cur_data)

            # 2. Yol Aksları Uzunluğu
            yol_layer = self.cmb_yol_layer.currentLayer()
            yol_uzunlugu_m = 0.0
            if yol_layer and isinstance(yol_layer, QgsVectorLayer):
                for yf in yol_layer.getFeatures():
                    yg = yf.geometry()
                    if yg and not yg.isEmpty():
                        yol_uzunlugu_m += da.measureLength(yg)

            # 3. Özel İstihdam ve Yolculuk Kuralları
            rules_config = self._get_rules_config()

            # Otomatik duplike kontrolü ve geometri temizliği
            cleaned_feats, clean_stats = GeometryCleanerEngine.clean_layer(layer)
            if clean_stats["duplike_elenen"] > 0:
                feats = cleaned_feats
                self.txt_nip_results.append(
                    f"<p style='color:#b45309;'>ℹ️ <i>Katmanda tespit edilen <b>{clean_stats['duplike_elenen']:,} adet mükerrer poligon</b> otomatik olarak ayıklandı; hesaplama <b>{clean_stats['temiz_cikan']:,} tekil ada</b> üzerinden yapıldı.</i></p>"
                )
            else:
                feats = cleaned_feats

            parsed_items, summary = NipCalculatorEngine.calculate(
                feats, layer.fields(), fonk_col, proj_nufus, da,
                sinir_geom=sinir_geom,
                sinir_modu=sinir_modu,
                yol_uzunlugu_m=yol_uzunlugu_m,
                rules_config=rules_config,
                secondary_fonk_col=secondary_fonk_col,
                analysis_mode=analysis_mode
            )

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
            tbl_dop_fields = [
                QgsField('parametre', QVariant.String),
                QgsField('alan_m2', QVariant.Double),
                QgsField('alan_ha', QVariant.Double),
                QgsField('oran_yuzde', QVariant.Double),
                QgsField('aciklama', QVariant.String)
            ]
            tbl_dop_pr.addAttributes(tbl_dop_fields)
            tbl_dop_layer.updateFields()

            dop = summary["dop_ozet"]
            p_m2 = dop["toplam_plan_alani_m2"]
            e_m2 = dop["dop_esas_alan_m2"]
            sinir_aciklama = "Plan Onama Sınırına Göre Kesin" if dop.get("sinir_katmani_kullanildi") else "İmar Adaları Toplamı Esas Alındı"

            dop_raw_rows = [
                ("Plan Onama Sınırı / Toplam Alan", p_m2, dop["toplam_plan_alani_ha"], 100.0, sinir_aciklama),
                ("İmar Adaları (Kullanım Poligonları)", dop["adalar_toplam_m2"], dop["adalar_toplam_ha"], round(dop["adalar_toplam_m2"]/max(1, p_m2)*100.0, 2), "Plan Fonksiyon Blokları"),
                ("Net Yol ve Ulaşım Ağı Alanı", dop["hesaplanan_yol_m2"], dop["hesaplanan_yol_ha"], dop["yol_orani_yuzde"], "Plan Sınırı - İmar Adaları Boşluğu"),
                ("DOP Dışı Alanlar (Harice Ayrılan)", dop["dop_disi_alan_m2"], round(dop["dop_disi_alan_m2"]/10000.0, 2), round(dop["dop_disi_alan_m2"]/max(1, p_m2)*100.0, 2), "Orman, Tarım, Su, Sit vb."),
                ("Düzenleme Sahası (DOP Esas Alan)", e_m2, round(e_m2/10000.0, 2), round(e_m2/max(1, p_m2)*100.0, 2), "Düzenlemeye Giren Net Saha"),
                ("Toplam Özel Mülkiyet (Tahsis)", dop["toplam_ozel_tahsis_m2"], round(dop["toplam_ozel_tahsis_m2"]/10000.0, 2), round(dop["toplam_ozel_tahsis_m2"]/max(1, e_m2)*100.0, 2), "Konut, Ticaret, Sanayi vb."),
                ("Kamu Poligon Donatıları", dop["kamu_poligonlar_m2"], round(dop["kamu_poligonlar_m2"]/10000.0, 2), round(dop["kamu_poligonlar_m2"]/max(1, e_m2)*100.0, 2), "Eğitim, Sağlık, Yeşil vb."),
                ("Toplam Kamu Kesintisi (DOP)", dop["toplam_kamu_kesinti_m2"], round(dop["toplam_kamu_kesinti_m2"]/10000.0, 2), dop["dop_orani"], "Donatılar + Gerçek Yol Ağı"),
                ("Kamu / Özel Mülkiyet Oranı", 0.0, 0.0, dop["kamu_ozel_orani"], "Kamu Kesintisi / Özel Tahsis Oranı"),
                ("HESAPLANAN DOP ORANI (%)", 0.0, 0.0, dop["dop_orani"], dop["dop_uygunluk"])
            ]
            if dop.get("ortalama_yol_genisligi_m"):
                dop_raw_rows.insert(3, ("Ortalama Fiili Yol Genişliği (m)", 0.0, 0.0, dop["ortalama_yol_genisligi_m"], f"{dop['yol_agi_uzunlugu_km']} km Yol Ağı / Yol Alanı"))

            dop_feats = []
            for r in dop_raw_rows:
                df = QgsFeature(tbl_dop_layer.fields())
                df.setAttributes(list(r))
                dop_feats.append(df)
            tbl_dop_pr.addFeatures(dop_feats)

            # 6. Kent Karakteri Tablosu Katmanı (NoGeometry)
            tbl_kk_layer = QgsVectorLayer("None", f"PLN3113_{analysis_mode}_3_Kent_Karakter_Tablosu", "memory")
            tbl_kk_pr = tbl_kk_layer.dataProvider()
            tbl_kk_fields = [
                QgsField('nip_fonksiyon', QVariant.String),
                QgsField('toplam_m2', QVariant.Double),
                QgsField('alt_nufus_m2_kisi', QVariant.Double),
                QgsField('ust_nufus_m2_kisi', QVariant.Double),
                QgsField('proj_nufus_m2_kisi', QVariant.Double)
            ]
            tbl_kk_pr.addAttributes(tbl_kk_fields)
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
            tbl_ek2_fields = [
                QgsField('donati_turu', QVariant.String),
                QgsField('toplam_m2', QVariant.Double),
                QgsField('mpyy_standart_m2', QVariant.Double),
                QgsField('mevcut_m2_alt_nufus', QVariant.Double),
                QgsField('mevcut_m2_ust_nufus', QVariant.Double),
                QgsField('durum_ust_nufus', QVariant.String)
            ]
            tbl_ek2_pr.addAttributes(tbl_ek2_fields)
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
            tbl_fd_fields = [
                QgsField('nip_fonksiyon', QVariant.String),
                QgsField('dop_durumu', QVariant.String),
                QgsField('alan_turu', QVariant.String),
                QgsField('adet', QVariant.Int),
                QgsField('alan_m2', QVariant.Double),
                QgsField('alan_ha', QVariant.Double),
                QgsField('kisi_basi_m2', QVariant.Double),
                QgsField('tum_plan_yuzdesi', QVariant.Double),
                QgsField('dop_ici_yuzde', QVariant.Double)
            ]
            tbl_fd_pr.addAttributes(tbl_fd_fields)
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
            root = QgsProject.instance().layerTreeRoot()
            grp_name = f"PLN3113 {mode_title} Analiz Çıktıları ({layer.name()})"
            grp = root.findGroup(grp_name)
            if not grp:
                grp = root.insertGroup(0, grp_name)

            for lyr in [out_layer, tbl_dop_layer, tbl_kk_layer, tbl_ek2_layer, tbl_fd_layer]:
                QgsProject.instance().addMapLayer(lyr, False)
                grp.addLayer(lyr)

            # DockWidget Tablolarını Doldur
            self._populate_dop_table(summary["dop_ozet"])
            self._populate_kk_table(summary["kent_karakter"])
            self._populate_ek2_table(summary["ek2_rapor"])
            self._populate_fd_table(summary["fonksiyon_dagilim"])

            # Gösterge Tablosunu Güncelle (Son Satır)
            alt_str = f"{summary['toplam_alt_nufus']:,}".replace(",", ".")
            ust_str = f"{summary['toplam_ust_nufus']:,}".replace(",", ".")
            kirsal_sabit = 25833
            ilce_alt_str = f"{(summary['toplam_alt_nufus'] + kirsal_sabit):,}".replace(",", ".")
            ilce_ust_str = f"{(summary['toplam_ust_nufus'] + kirsal_sabit):,}".replace(",", ".")

            self.tbl_benchmark.setItem(4, 0, QTableWidgetItem(f"Hesaplanan {mode_title} Kapasitesi"))
            self.tbl_benchmark.setItem(4, 1, QTableWidgetItem(f"{alt_str} - {ust_str}"))
            self.tbl_benchmark.setItem(4, 2, QTableWidgetItem(f"~{kirsal_sabit:,}".replace(",", ".")))
            self.tbl_benchmark.setItem(4, 3, QTableWidgetItem(f"{ilce_alt_str} - {ilce_ust_str}"))

            font = QFont()
            font.setBold(True)
            for c in range(4):
                item = self.tbl_benchmark.item(4, c)
                if item:
                    item.setFont(font)
                    item.setForeground(QColor("#0f766e"))

            # HTML Rapor Hazırla
            dop_durum_color = "#16a34a" if dop["dop_orani"] <= 45.0 else "#dc2626"
            yol_genislik_tr = f"<tr><td><b>Ortalama Fiili Yol Genişliği</b></td><td colspan='2'><b>{dop['ortalama_yol_genisligi_m']} m</b> ({dop['yol_agi_uzunlugu_km']} km Yol Ağı)</td></tr>" if dop.get("ortalama_yol_genisligi_m") else ""

            # Plan Onama Sınırı Bilgi Özeti
            s_stats = summary.get("sinir_filtre_ozet")
            sinir_info_html = ""
            sinir_msg_extra = ""
            if s_stats and s_stats.get("aktif"):
                mod_names = {
                    "clip": "Sınırla Kırp / Kes (Sınır Dışını At, Net İç Alanı Al)",
                    "intersect": "Sınıra Değenleri Dahil Et (Bütünsel Korunur)",
                    "within": "Sınırı Aşanları Hariç Tut (Yalnızca Tamamı İçte Olanlar)",
                    "centroid": "Ağırlık Merkezine Göre (Merkezi İçte Olanlar)"
                }
                mod_label = mod_names.get(s_stats.get("mod"), s_stats.get("mod"))
                elenen_style = "color:#b91c1c; font-weight:bold;" if s_stats['sinir_disi_elenen'] > 0 else "color:#15803d; font-weight:bold;"
                sinir_info_html = f"""
                <h4>🌐 Plan Onama Sınırı Mekânsal Kapsam Raporu</h4>
                <div style="font-size:11px; color:#1e3a8a; margin-bottom:12px; background:#eff6ff; padding:10px; border-left:4px solid #3b82f6; border-radius:4px;">
                    <b>Uygulanan Sınır İşlem Modu:</b> {mod_label}<br>
                    • <b>Toplam Girdi Ada Sayısı:</b> {s_stats['toplam_girdi_ada']} adet<br>
                    • <b>Hesaplamaya Alınan Ada Sayısı:</b> {s_stats['islenen_ada_sayisi']} adet<br>
                    • <b>Tamamı Sınır İçinde Kalanlar:</b> {s_stats['tamamen_icinde']} adet<br>
                    • <b>Sınırı Kesen / İşlenen Adalar:</b> {s_stats['kesisen_islenen']} adet<br>
                    • <b>Sınır Dışında Kaldığı İçin Elenenler:</b> <span style="{elenen_style}">{s_stats['sinir_disi_elenen']} adet ada</span> (Kesinlikle hesaba katılmadı)
                </div>
                """
                if s_stats.get("sinir_disi_elenen", 0) > 0:
                    sinir_msg_extra = f"\n\n⚠️ Plan Onama Sınırı dışında kalan {s_stats['sinir_disi_elenen']} adet ada otomatik olarak elendi ve hesaba dahil edilmedi."

            report_html = f"""
            <h3>🏙️ TİRE {mode_title.upper()} ANALİZ VE KAPASİTE RAPORU</h3>
            
            <h4>0. 👥 Demografik Göstergeler ve Tarihsel Kıyaslama</h4>
            <table border="1" cellpadding="4" style="border-collapse:collapse; width:100%; margin-bottom:12px;">
                <tr style="background:#0f766e; color:white;">
                    <th>Nüfus Niteliği / Kapsam</th><th>Kentsel Merkez</th><th>Kırsal Nüfus</th><th>İlçe Toplamı</th>
                </tr>
                <tr><td><b>1997 Plan Raporu (1990 DİE)</b></td><td>37.855</td><td>39.459 (65 Köy)</td><td>77.314</td></tr>
                <tr><td><b>2015 Plan Projeksiyonu (Hedef)</b></td><td>53.629</td><td>46.711 (Model)</td><td>100.340</td></tr>
                <tr><td><b>2015 TÜİK ADNKS (Gerçekleşen)</b></td><td>~57.069 (Merkez Mahalleler)</td><td>~25.033</td><td>82.102</td></tr>
                <tr><td><b>Güncel TÜİK ADNKS (2025/2026)</b></td><td>~61.738 (Merkez Mahalleler)</td><td>~25.833</td><td>87.571</td></tr>
                <tr style="background:#ecfdf5; font-weight:bold; color:#0f766e;">
                    <td><b>Hesaplanan {mode_title} Kapasitesi</b></td><td>{alt_str} - {ust_str}</td><td>~25.833 (Kırsal Sabit)</td><td>{ilce_alt_str} - {ilce_ust_str}</td>
                </tr>
            </table>
            <div style="font-size:11px; color:#475569; margin-bottom:14px; background:#f1f5f9; padding:8px; border-left:3px solid #0f766e; border-radius:3px;">
                <b>Metodolojik Açıklamalar ve Veri Kısıtları:</b><br>
                • <b>1997 Plan Raporu (1990 DİE Sayımı):</b> Raporda kırsal nüfus 65 köyün tek tek dökümüyle (39.459 kişi) verilmiş; kentsel merkez nüfusu 37.855 kişi aktarılmıştır.<br>
                • <b>2015 Plan Projeksiyonu:</b> Üst Değerli Model (Regresyon) projeksiyonuna göre kentsel nüfus 53.629, toplam ilçe 100.340 kişidir. Kırsal nüfus farktan türetilmiştir (46.711).<br>
                • <b>6360 Sayılı Kanun Etkisi:</b> 2012'de kabul edilen yasa uyarınca İzmir genelinde tüm köyler ve beldeler mahalleye dönüştüğünden resmi ADNKS bültenlerinde idari kır/kent ayrımı bulunmamaktadır.<br>
                • <b>Merkez / Kırsal Ayrıştırması:</b> Kentsel merkez, kentsel makroform ve yerleşik leke içindeki mahalleler toplamıdır; kırsal nüfus ilçe toplamından bu değer düşülerek elde edilmiştir.<br>
                • <b>Güncel TÜİK Verisi:</b> En güncel resmi sayım 31 Aralık 2025 referanslı (Şubat 2026'da ilan edilen) ADNKS kütüğüdür (87.571 kişi).<br>
                • <b>Planlama Uyumu:</b> Hesaplanan kentsel üst sınır nüfusu ({ust_str} kişi), 1997 planının 2015 hedefi (53.629 kişi) ile %99.6 oranında birebir örtüşmektedir.
            </div>

            {sinir_info_html}

            <h4>1. Genel Nüfus, Alan ve Ulaşım Göstergeleri</h4>
            <table border="1" cellpadding="4" style="border-collapse:collapse; width:100%;">
                <tr style="background:#0f766e; color:white;">
                    <th>Metrik</th><th>Alt Sınır (Kişi/Birim)</th><th>Üst Sınır (Kişi/Birim)</th>
                </tr>
                <tr><td><b>Toplam Plan Nüfusu</b></td><td style="color:#0f766e; font-weight:bold;">{alt_str} Kişi</td><td style="color:#0f766e; font-weight:bold;">{ust_str} Kişi</td></tr>
                <tr><td><b>Toplam Konut & Karma Alanı</b></td><td colspan="2">{summary['toplam_konut_alani_ha']:.2f} Hektar</td></tr>
                <tr><td><b>Toplam İmar Adaları Alanı</b></td><td colspan="2">{dop['adalar_toplam_ha']:.2f} Hektar ({dop['adalar_toplam_m2']:,.0f} m²)</td></tr>
                <tr><td><b>Net Yol ve Ulaşım Alanı</b></td><td colspan="2"><b>{dop['hesaplanan_yol_ha']:.2f} Hektar</b> (% {dop['yol_orani_yuzde']:.2f} - {dop['kisi_basi_yol_m2']:.2f} m²/kişi)</td></tr>
                {yol_genislik_tr}
                <tr><td><b>Toplam Plan Alanı ({sinir_aciklama})</b></td><td colspan="2"><b>{dop['toplam_plan_alani_ha']:.2f} Hektar</b> ({p_m2:,.0f} m²)</td></tr>
                <tr><td><b>Tahmini İstihdam Kapasitesi</b></td><td colspan="2"><b>{summary['toplam_istihdam']:,}</b> Çalışan</td></tr>
                <tr><td><b>Günlük Araç Yolculuk Yükü</b></td><td colspan="2"><b>{summary['toplam_gunluk_arac']:,}</b> Araç (PAU)</td></tr>
                <tr><td><b>Günlük Yaya Yolculuk Yükü</b></td><td colspan="2"><b>{summary['toplam_gunluk_yaya']:,}</b> Yaya</td></tr>
            </table>

            <h4>2. ⚖️ Kamu - Özel Mülkiyet Dengesi ve DOP Hesabı</h4>
            <table border="1" cellpadding="4" style="border-collapse:collapse; width:100%;">
                <tr style="background:#0f766e; color:white;">
                    <th>Parametre</th><th>Alan (m²)</th><th>Alan (ha)</th><th>Oran (%)</th><th>Açıklama</th>
                </tr>
                <tr><td><b>Plan Onama Sınırı / Toplam Alan</b></td><td>{p_m2:,.0f} m²</td><td>{dop['toplam_plan_alani_ha']:.2f} ha</td><td>100.0 %</td><td>{sinir_aciklama}</td></tr>
                <tr><td><b>İmar Adaları (Kullanım Poligonları)</b></td><td>{dop['adalar_toplam_m2']:,.0f} m²</td><td>{dop['adalar_toplam_ha']:.2f} ha</td><td>{(dop['adalar_toplam_m2']/max(1, p_m2)*100.0):.2f} %</td><td>Plan Fonksiyon Blokları</td></tr>
                <tr><td><b>Net Yol ve Ulaşım Alanı</b></td><td>{dop['hesaplanan_yol_m2']:,.0f} m²</td><td>{dop['hesaplanan_yol_ha']:.2f} ha</td><td>% {dop['yol_orani_yuzde']:.2f}</td><td>Plan Sınırı - İmar Adaları Farkı</td></tr>
                <tr><td><b>DOP Dışı Alanlar</b></td><td>{dop['dop_disi_alan_m2']:,.0f} m²</td><td>{(dop['dop_disi_alan_m2']/10000.0):.2f} ha</td><td>{(dop['dop_disi_alan_m2']/max(1, p_m2)*100.0):.2f} %</td><td>Orman, Tarım, Su vb.</td></tr>
                <tr><td><b>Düzenleme Sahası (DOP Esas)</b></td><td>{e_m2:,.0f} m²</td><td>{(e_m2/10000.0):.2f} ha</td><td>{(e_m2/max(1, p_m2)*100.0):.2f} %</td><td>Düzenlemeye Giren Net Saha</td></tr>
                <tr><td><b>Toplam Özel Mülkiyet (Tahsis)</b></td><td>{dop['toplam_ozel_tahsis_m2']:,.0f} m²</td><td>{(dop['toplam_ozel_tahsis_m2']/10000.0):.2f} ha</td><td>{(dop['toplam_ozel_tahsis_m2']/max(1, e_m2)*100.0):.2f} %</td><td>Konut, Ticaret vb.</td></tr>
                <tr><td><b>Toplam Kamu Kesintisi (DOP)</b></td><td>{dop['toplam_kamu_kesinti_m2']:,.0f} m²</td><td>{(dop['toplam_kamu_kesinti_m2']/10000.0):.2f} ha</td><td>% {dop['dop_orani']:.2f}</td><td>Donatılar + Gerçek Yol Ağı</td></tr>
                <tr><td><b>Kamu Poligon Donatıları</b></td><td>{dop['kamu_poligonlar_m2']:,.0f} m²</td><td>{(dop['kamu_poligonlar_m2']/10000.0):.2f} ha</td><td>{(dop['kamu_poligonlar_m2']/max(1, e_m2)*100.0):.2f} %</td><td>Eğitim, Sağlık, Yeşil vb.</td></tr>
                <tr style="background:#fef08a;">
                    <td><b>HESAPLANAN DOP ORANI (%)</b></td><td>-</td><td>-</td>
                    <td style="color:{dop_durum_color}; font-weight:bold; font-size:14px;">% {dop['dop_orani']:.2f}</td>
                    <td style="color:{dop_durum_color}; font-weight:bold;">{dop['dop_uygunluk']}</td>
                </tr>
            </table>

            <h4>3. 📋 MPYY Ek-2 Donatı Yeterlilik Dengesi:</h4>
            <table border="1" cellpadding="3" style="border-collapse:collapse; width:100%;">
                <tr style="background:#e2e8f0; font-size:11px;">
                    <th>Donatı Grubu</th><th>Mevcut Alan</th><th>Ek-2 Std</th><th>Mevcut (Üst Nüfus)</th><th>Durum</th>
                </tr>
            """
            for ek in summary["ek2_rapor"]:
                durum_color = "#16a34a" if ek["durum_ust"] == "YETERLİ" else "#dc2626"
                report_html += f"""
                <tr>
                    <td>{ek['kategori_adi']}</td>
                    <td>{ek['toplam_m2']:,.0f} m²</td>
                    <td>{ek['standart_m2']} m²/k</td>
                    <td>{ek['kb_ust']:.2f} m²/k</td>
                    <td style="color:{durum_color}; font-weight:bold;">{ek['durum_ust']}</td>
                </tr>
                """
            report_html += "</table>"

            self.txt_nip_results.setHtml(report_html)

            # Durumu Sakla ve Dışa Aktarmayı Etkinleştir
            self._last_nip_summary = summary
            self._last_nip_items = parsed_items
            self._last_nip_sinir_geom = sinir_geom
            self._last_nip_crs = layer.crs()
            self._last_nip_html = report_html
            self._last_nip_out_layer = out_layer
            self.btn_export_csv.setEnabled(True)
            self.btn_export_html.setEnabled(True)
            self.btn_open_dashboard.setEnabled(True)
            self.btn_style_density.setEnabled(True)
            self.btn_style_mpyy.setEnabled(True)

            # Canlı Görsel Göstergeleri Güncelle
            dop_val = dop.get('dop_orani', 0.0)
            self.bar_dop.setValue(min(80, max(0, int(round(dop_val)))))
            if dop_val <= 45.0:
                self.bar_dop.setStyleSheet("QProgressBar::chunk { background-color: #10b981; }")
                self.lbl_dop_badge.setText(f"%{dop_val:.2f} YASAL UYGUN")
                self.lbl_dop_badge.setStyleSheet("font-size: 8pt; font-weight: 700; padding: 2px 6px; border-radius: 4px; background: #dcfce7; color: #15803d;")
            else:
                self.bar_dop.setStyleSheet("QProgressBar::chunk { background-color: #ef4444; }")
                self.lbl_dop_badge.setText(f"%{dop_val:.2f} AŞIM (+%{dop_val - 45.0:.2f})")
                self.lbl_dop_badge.setStyleSheet("font-size: 8pt; font-weight: 700; padding: 2px 6px; border-radius: 4px; background: #fee2e2; color: #b91c1c;")

            toplam_kamu_donati_m2 = dop.get("kamu_poligonlar_m2", 0.0)
            yesil_alan_m2 = sum(it.get("alan_m2", 0.0) for it in parsed_items if any(k in it.get("fonk_raw", "").upper() for k in ["PARK", "YEŞİL", "YESIL", "ÇOCUK", "COCUK", "MEYDAN", "REKREASYON", "SPOR"]) and it.get("dop_durumu") == "DOP İÇİ")
            acik_yesil_pct = round((yesil_alan_m2 / max(1.0, toplam_kamu_donati_m2)) * 100.0, 1)
            self.bar_yesil.setValue(min(100, max(0, int(round(acik_yesil_pct)))))
            if acik_yesil_pct >= 75.0:
                self.bar_yesil.setStyleSheet("QProgressBar::chunk { background-color: #16a34a; }")
                self.lbl_yesil_badge.setText(f"%{acik_yesil_pct:.1f} YETERLİ")
                self.lbl_yesil_badge.setStyleSheet("font-size: 8pt; font-weight: 700; padding: 2px 6px; border-radius: 4px; background: #dcfce7; color: #15803d;")
            else:
                self.bar_yesil.setStyleSheet("QProgressBar::chunk { background-color: #f59e0b; }")
                self.lbl_yesil_badge.setText(f"%{acik_yesil_pct:.1f} EKSİK")
                self.lbl_yesil_badge.setStyleSheet("font-size: 8pt; font-weight: 700; padding: 2px 6px; border-radius: 4px; background: #fef3c7; color: #b45309;")

            QMessageBox.information(
                self, f"{mode_title} Analizi Tamamlandı",
                f"Hesaplanan {mode_title} Nüfusu:\nAlt Sınır: {alt_str} Kişi\nÜst Sınır: {ust_str} Kişi\n\n"
                f"Hesaplanan DOP Oranı: %{dop['dop_orani']:.2f} ({dop['dop_uygunluk']})\n"
                f"Net Yol Ağı Alanı: {dop['hesaplanan_yol_ha']:.2f} ha (%{dop['yol_orani_yuzde']:.2f})\n\n"
                f"Analiz katmanı ve 4 adet detaylı tablo (DOP, Kent Karakteri, Ek-2 ve Fonksiyon Dağılımı) "
                f"harita projenize 'PLN3113 {mode_title} Analiz Çıktıları' grubu altında eklendi.{sinir_msg_extra}"
            )

        except Exception as e:
            QMessageBox.critical(self, "Hata", f"NİP Analizi sırasında hata: {str(e)}")
            self.txt_nip_results.append(f"<span style='color:red;'>Hata: {str(e)}</span>")
        finally:
            self.btn_run_nip.setEnabled(True)

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
        p_m2 = dop["toplam_plan_alani_m2"]
        e_m2 = dop["dop_esas_alan_m2"]
        sinir_aciklama = "Plan Onama Sınırına Göre Kesin" if dop.get("sinir_katmani_kullanildi") else "İmar Adaları Toplamı Esas Alındı"

        try:
            # 1. DOP CSV
            dop_csv = os.path.join(folder, "pln3113_nip_dop_kamu_ozel_dengesi.csv")
            with open(dop_csv, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["Parametre", "Alan (m²)", "Alan (ha)", "Oran (%)", "Açıklama / Değerlendirme"])
                dop_rows = [
                    ["Plan Onama Sınırı / Toplam Alan", dop["toplam_plan_alani_m2"], dop["toplam_plan_alani_ha"], 100.0, sinir_aciklama],
                    ["İmar Adaları (Kullanım Poligonları)", dop["adalar_toplam_m2"], dop["adalar_toplam_ha"], round(dop["adalar_toplam_m2"]/max(1, p_m2)*100.0, 2), "Plan Fonksiyon Blokları"],
                    ["Net Yol ve Ulaşım Ağı Alanı", dop["hesaplanan_yol_m2"], dop["hesaplanan_yol_ha"], dop["yol_orani_yuzde"], "Plan Sınırı - İmar Adaları Boşluğu"],
                    ["Kişi Başına Düşen Yol Standardı", "-", "-", f"{dop['kisi_basi_yol_m2']:.2f} m²/k", "Üst Nüfusa Göre Yol Alanı"],
                    ["DOP Dışı Alanlar", dop["dop_disi_alan_m2"], round(dop["dop_disi_alan_m2"]/10000.0, 2), round(dop["dop_disi_alan_m2"]/max(1, p_m2)*100.0, 2), "Orman, Tarım, Su, Sit vb."],
                    ["Düzenleme Sahası (DOP Esas Alan)", dop["dop_esas_alan_m2"], round(dop["dop_esas_alan_m2"]/10000.0, 2), round(dop["dop_esas_alan_m2"]/max(1, p_m2)*100.0, 2), "Düzenlemeye Giren Net Saha"],
                    ["Toplam Özel Mülkiyet (Tahsis)", dop["toplam_ozel_tahsis_m2"], round(dop["toplam_ozel_tahsis_m2"]/10000.0, 2), round(dop["toplam_ozel_tahsis_m2"]/max(1, e_m2)*100.0, 2), "Konut, Ticaret, Sanayi vb."],
                    ["Toplam Kamu Alanı (Kesinti + Yol)", dop["toplam_kamu_kesinti_m2"], round(dop["toplam_kamu_kesinti_m2"]/10000.0, 2), dop["dop_orani"], "Donatılar + Hesaplanan Yol Payı"],
                    ["Kamu Poligon Donatıları", dop["kamu_poligonlar_m2"], round(dop["kamu_poligonlar_m2"]/10000.0, 2), round(dop["kamu_poligonlar_m2"]/max(1, e_m2)*100.0, 2), "Eğitim, Sağlık, Yeşil vb."],
                    ["Kamu / Özel Mülkiyet Oranı", "-", "-", dop["kamu_ozel_orani"], "Kamu Kesintisi / Özel Tahsis Oranı"],
                    ["HESAPLANAN DOP ORANI (%)", "-", "-", dop["dop_orani"], dop["dop_uygunluk"]]
                ]
                if dop.get("ortalama_yol_genisligi_m"):
                    dop_rows.insert(4, ["Ortalama Fiili Yol Genişliği (m)", "-", f"{dop['yol_agi_uzunlugu_km']} km Yol", dop["ortalama_yol_genisligi_m"], "Yol Alanı / Hat Uzunluğu"])
                w.writerows(dop_rows)

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

        # Bilgi Barı
        info_banner = QWidget()
        info_banner.setStyleSheet("background: #fefce8; border: 1px solid #fef08a; border-radius: 6px; padding: 4px;")
        info_l = QHBoxLayout(info_banner)
        info_l.setContentsMargins(6, 4, 6, 4)
        lbl_hint = QLabel("💡 <b>Mevcut Durum Fiili Nüfus Metodolojisi:</b> Bina kat, taban alanı, TÜİK hanehalkı ve fiili istihdam hesabı.")
        lbl_hint.setStyleSheet("color: #854d0e; font-size: 11px;")
        btn_hint_guide = QPushButton("📖 Rehberde İncele")
        btn_hint_guide.setCursor(_POINTING_HAND)
        btn_hint_guide.setStyleSheet("background: #d97706; color: white; border-radius: 4px; padding: 3px 8px; font-size: 11px; font-weight: bold;")
        btn_hint_guide.clicked.connect(self._open_theoretical_guide)
        info_l.addWidget(lbl_hint)
        info_l.addStretch()
        info_l.addWidget(btn_hint_guide)
        layout.addWidget(info_banner)

        box_field = QGroupBox("Mevcut Durum Katmanları")
        f_layout = QFormLayout(box_field)

        self.cmb_ada_layer = QgsMapLayerComboBox()
        self.cmb_ada_layer.setFilters(QgsMapLayerProxyModel.Filter.PolygonLayer)
        f_layout.addRow("Kadastro / Saha Adaları:", self.cmb_ada_layer)

        self.cmb_bina_layer = QgsMapLayerComboBox()
        self.cmb_bina_layer.setFilters(QgsMapLayerProxyModel.Filter.PolygonLayer)
        f_layout.addRow("Bina Katmanı (tire_bina):", self.cmb_bina_layer)

        self.spn_hh = QDoubleSpinBox()
        self.spn_hh.setRange(1.0, 8.0)
        self.spn_hh.setValue(2.85)
        self.spn_hh.setSingleStep(0.05)
        f_layout.addRow("Ortalama Hanehalkı Büyüklüğü:", self.spn_hh)

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
        lbl_kural.setStyleSheet("color: #0369a1; font-size: 11px; background: #e0f2fe; padding: 8px; border-radius: 4px;")
        layout.addWidget(lbl_kural)

        self.btn_run_field = QPushButton("  Saha ve Bina Bazlı Fiili Nüfus ve Morfolojiyi Hesapla")
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
        self.box_field_styles = QGroupBox("🎨 1-Tıkla Tematik Harita ve Morfoloji Stilleri")
        self.box_field_styles.setStyleSheet("QGroupBox { font-weight: bold; color: #0f766e; }")
        self.box_field_styles.setVisible(False)
        st_layout = QVBoxLayout(self.box_field_styles)
        st_layout.setSpacing(4)

        lbl_style_desc = QLabel("Hesaplanan ada katmanını tek tıkla mekânsal ve tematik olarak renklendirin:")
        lbl_style_desc.setStyleSheet("font-size: 11px; color: #64748b;")
        st_layout.addWidget(lbl_style_desc)

        btn_row1 = QHBoxLayout()
        self.btn_style_pop = QPushButton("👥 Nüfus (k/ha)")
        self.btn_style_pop.setToolTip("Brüt nüfus yoğunluğu kademeleri (0, 1-50, 51-150, 151-300, 301-600, 600+)")
        self.btn_style_pop.clicked.connect(self._apply_style_pop)
        btn_row1.addWidget(self.btn_style_pop)

        self.btn_style_taks = QPushButton("🏗️ TAKS (GSI)")
        self.btn_style_taks.setToolTip("Taban Alanı Katsayısı / Zemin Doluluk Oranı (GSI: <0.20, 0.20-0.40, 0.40-0.60, >0.60)")
        self.btn_style_taks.clicked.connect(self._apply_style_taks)
        btn_row1.addWidget(self.btn_style_taks)

        self.btn_style_kaks = QPushButton("🏢 KAKS (FSI / Emsal)")
        self.btn_style_kaks.setToolTip("Kat Alanı Katsayısı / Emsal (FSI: <0.60, 0.60-1.20, 1.20-2.0, 2.0-3.5, >3.5)")
        self.btn_style_kaks.clicked.connect(self._apply_style_kaks)
        btn_row1.addWidget(self.btn_style_kaks)
        st_layout.addLayout(btn_row1)

        btn_row2 = QHBoxLayout()
        self.btn_style_kat = QPushButton("📏 Kat Sayısı (L)")
        self.btn_style_kat.setToolTip("Ağırlıklı Ortalama Kat Adedi (L = İnşaat Alanı / Taban Alanı)")
        self.btn_style_kat.clicked.connect(self._apply_style_ort_kat)
        btn_row2.addWidget(self.btn_style_kat)

        self.btn_style_open = QPushButton("🌳 Açık Alan (%)")
        self.btn_style_open.setToolTip("Ada Zeminindeki Açık / Boş Alan Yüzdesi (100 - TAKS*100)")
        self.btn_style_open.clicked.connect(self._apply_style_open)
        btn_row2.addWidget(self.btn_style_open)

        self.btn_style_nizam = QPushButton("🏘️ Yapı Nizamı (A4)")
        self.btn_style_nizam.setToolTip("PlanX Morfoloji Motoru (A4): Ayrık, Bitişik / Blok, Karma, Boş Ada")
        self.btn_style_nizam.clicked.connect(self._apply_style_nizam)
        btn_row2.addWidget(self.btn_style_nizam)

        self.btn_style_doku = QPushButton("📐 Doku / Spacematrix")
        self.btn_style_doku.setToolTip("Spacematrix Morfolojik Tipolojisi: Seyrek Bahçeli, Orta Yoğunluk, Kompakt Blok, Kule Blok, Geleneksel Doku")
        self.btn_style_doku.clicked.connect(self._apply_style_doku)
        btn_row2.addWidget(self.btn_style_doku)
        st_layout.addLayout(btn_row2)

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
                <tr style="background:#d97706; color:white;"><th colspan="2">1. Demografi & Yapılaşma Kapasitesi</th></tr>
                <tr><td><b>Toplam İncelenen Kadastro Adası</b></td><td>{stats['toplam_ada_sayisi']:,} Adet</td></tr>
                <tr><td><b>Eşleşen Toplam Bina Sayısı</b></td><td>{stats['toplam_eslesen_bina']:,} Adet</td></tr>
                <tr><td><b>Tahmini Konut Birim Sayısı</b></td><td>{stats['toplam_konut_birimi']:,} Bağımsız Bölüm</td></tr>
                <tr><td><b>Tahmini Fiili Yaşayan Nüfus</b></td><td style="color:#b45309; font-weight:bold; font-size:13px;">{stats['toplam_fiili_nufus']:,} Kişi</td></tr>
                <tr><td><b>Tahmini Fiili İstihdam</b></td><td><b>{stats['toplam_fiili_istihdam']:,}</b> Çalışan</td></tr>
                <tr><td><b>Ortalama Hanehalkı Büyüklüğü</b></td><td>{stats['ortalama_hanehalki']} Kişi/Hane (Daire: {stats['ortalama_daire_m2']} m²)</td></tr>
            </table>

            <table border="1" cellpadding="4" style="border-collapse:collapse; width:100%;">
                <tr style="background:#0f766e; color:white;"><th colspan="2">2. Kentsel Morfoloji, TAKS / KAKS ve Spacematrix Göstergeleri</th></tr>
                <tr><td><b>Toplam Bina Taban Alanı (m²)</b></td><td>{stats['toplam_taban_m2']:,.1f} m²</td></tr>
                <tr><td><b>Toplam İnşaat Alanı (m²)</b></td><td>{stats['toplam_insaat_m2']:,.1f} m²</td></tr>
                <tr style="background:#fefce8;"><td><b>Ortalama Fiili TAKS (GSI)</b></td><td style="font-weight:bold; color:#0f766e;">{stats['ortalama_taks']:.3f}</td></tr>
                <tr style="background:#fefce8;"><td><b>Ortalama Fiili KAKS (Emsal / FSI)</b></td><td style="font-weight:bold; color:#0f766e;">{stats['ortalama_kaks']:.3f}</td></tr>
                <tr><td><b>Ortalama Kat Adedi (L)</b></td><td><b>{stats['ortalama_kat']:.1f}</b> Kat</td></tr>
                <tr><td><b>Ortalama Açık Alan Oranı (%)</b></td><td><b>%{stats['ortalama_acik_alan_yuzde']:.1f}</b></td></tr>
            </table>
            <div style="font-size:10px; color:#475569; margin-top:6px; background:#f1f5f9; padding:6px; border-radius:3px;">
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
            self.txt_field_results.append(f"<span style='color:red;'>Hata: {str(e)}</span>")
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

        t_lbl = QLabel("🌐 Ödev 13: Ulaşım, Ağ ve Erişim Analizleri (PlanX Motoru)")
        t_lbl.setStyleSheet("font-weight: 700; font-size: 10pt; color: #0f766e;")
        info_lay.addWidget(t_lbl)

        d_lbl = QLabel(
            "PLN3113 1. Ara Jüri (AJ1) Ödev 13 Ağ ve Erişim Analizleri Süiti:\n"
            "PlanX gömülü saf NumPy/SciPy motoru ile Space Syntax (NAIN/NACH), Primal Ağ Merkezilikleri, "
            "OD Matrisi & Detour Bariyerleri, 5-10-15 dk Yürüme İzokronları & Pedshed, 2SFCA Kapasite Yeterliliği "
            "ve Mevcut vs Meri Plan A/B Fark Haritası."
        )
        d_lbl.setWordWrap(True)
        d_lbl.setStyleSheet("color: #475569; font-size: 8.5pt;")
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
        f_syntax.addRow("Yol Ağı Katmanı (Mevcut / Meri):", self.cmb_syntax_roads)

        self.txt_syntax_radii = QLineEdit("400, 800, 1200, n")
        self.txt_syntax_radii.setToolTip("Metrik yarıçaplar (m): Yaya koridorları için 400/800, kent ölçeği için n")
        f_syntax.addRow("Analiz Yarıçapları (R metre):", self.txt_syntax_radii)

        l_syntax.addLayout(f_syntax)
        lbl_syntax_hint = QLabel("💡 Çıktılar: NAIN (Varış/Yaya Canlılığı) ve NACH (Geçiş/Arter Yükü) metrikleri.")
        lbl_syntax_hint.setStyleSheet("color: #64748b; font-size: 8pt; font-style: italic;")
        l_syntax.addWidget(lbl_syntax_hint)

        self.btn_run_syntax = QPushButton("  🚀 Space Syntax Segment Analizini Çalıştır (NAIN & NACH)")
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

        self.chk_cent_edges = QCheckBox("Aks Çizgileri Merkezilikleri (Edges)")
        self.chk_cent_edges.setChecked(True)
        f_cent.addRow(self.chk_cent_edges)

        self.chk_cent_nodes = QCheckBox("Kavşak Düğüm Merkezilikleri (Nodes)")
        self.chk_cent_nodes.setChecked(True)
        f_cent.addRow(self.chk_cent_nodes)

        l_cent.addLayout(f_cent)
        lbl_cent_hint = QLabel("💡 Çıktılar: Betweenness (Aradalık), Closeness (Yakınlık) ve Straightness (Doğrusallık).")
        lbl_cent_hint.setStyleSheet("color: #64748b; font-size: 8pt; font-style: italic;")
        l_cent.addWidget(lbl_cent_hint)

        self.btn_run_cent = QPushButton("  📊 Primal Ağ Merkeziliklerini Hesapla")
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
        f_od.addRow("Menşe (Origins / Mahalle-Ada Merkezleri):", self.cmb_od_origins)

        self.cmb_od_destinations = QgsMapLayerComboBox()
        self.cmb_od_destinations.setFilters(QgsMapLayerProxyModel.Filter.PointLayer)
        f_od.addRow("Hedef (Destinations / MİA, Sanayi, Donatı):", self.cmb_od_destinations)

        self.cmb_od_road = QgsMapLayerComboBox()
        self.cmb_od_road.setFilters(QgsMapLayerProxyModel.Filter.LineLayer)
        f_od.addRow("Yol Ağı Katmanı:", self.cmb_od_road)

        self.chk_od_routes = QCheckBox("Ağ üzerindeki gerçek en kısa yol rotalarını çizgi olarak üret")
        self.chk_od_routes.setChecked(True)
        f_od.addRow(self.chk_od_routes)

        self.chk_od_desire = QCheckBox("Kuş uçuşu arzu hatları ve Detour Bariyer Analizini üret (> 1.35)")
        self.chk_od_desire.setChecked(True)
        f_od.addRow(self.chk_od_desire)

        l_od.addLayout(f_od)
        lbl_od_hint = QLabel("💡 Detour Ratio = Ağ Mesafesi / Kuş Uçuşu. 1.35 üzerindeki akslar kopukluk/bariyer işaretidir.")
        lbl_od_hint.setStyleSheet("color: #64748b; font-size: 8pt; font-style: italic;")
        l_od.addWidget(lbl_od_hint)

        self.btn_run_od = QPushButton("  📍 OD Rotalarını ve Detour Bariyerlerini Üret")
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
        f_iso.addRow("Donatı Katmanı (Okul, Sağlık, Park):", self.cmb_iso_facilities)

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
        f_iso.addRow("İzokron Geometri Yöntemi:", self.cmb_iso_method)

        l_iso.addLayout(f_iso)
        lbl_iso_hint = QLabel("💡 400m (5 dk), 800m (10 dk), 1200m (15 dk). Pedshed < 0.40 olan donatılar izole sayılır.")
        lbl_iso_hint.setStyleSheet("color: #64748b; font-size: 8pt; font-style: italic;")
        l_iso.addWidget(lbl_iso_hint)

        self.btn_run_iso = QPushButton("  🚶 Hizmet İzokronları ve Pedshed Karnesini Üret")
        self.btn_run_iso.setObjectName("SecondaryButton")
        self.btn_run_iso.setCursor(_POINTING_HAND)
        self.btn_run_iso.clicked.connect(self._on_run_hizmet_izokron)
        l_iso.addWidget(self.btn_run_iso)
        l_iso.addStretch()
        sub_tabs.addTab(w_iso, "4. Hizmet İzokronları")

        # -------------------------------------------------------------
        # Alt Sekme 5: 2SFCA Donatı Yeterliliği (Kapasite + Mesafe)
        # -------------------------------------------------------------
        w_fca = QWidget()
        l_fca = QVBoxLayout(w_fca)
        f_fca = QFormLayout()

        self.cmb_fca_facilities = QgsMapLayerComboBox()
        self.cmb_fca_facilities.setFilters(QgsMapLayerProxyModel.Filter.PointLayer | QgsMapLayerProxyModel.Filter.PolygonLayer)
        f_fca.addRow("Donatı Katmanı (Okul, Sağlık):", self.cmb_fca_facilities)

        self.cmb_fca_id_field = QgsFieldComboBox()
        self.cmb_fca_id_field.setAllowEmptyFieldName(True)
        f_fca.addRow("Donatı Ad / Kimlik Sütunu:", self.cmb_fca_id_field)

        self.cmb_fca_cap_field = QgsFieldComboBox()
        self.cmb_fca_cap_field.setAllowEmptyFieldName(True)
        f_fca.addRow("Kapasite Sütunu (Boşsa Sabit):", self.cmb_fca_cap_field)

        self.spn_fca_default_cap = QDoubleSpinBox()
        self.spn_fca_default_cap.setRange(1.0, 1000000.0)
        self.spn_fca_default_cap.setValue(100.0)
        self.spn_fca_default_cap.setSuffix(" birim/öğrenci")
        f_fca.addRow("Varsayılan Kapasite (Sütun Boşsa):", self.spn_fca_default_cap)

        self.cmb_fca_demand = QgsMapLayerComboBox()
        self.cmb_fca_demand.setFilters(QgsMapLayerProxyModel.Filter.PointLayer | QgsMapLayerProxyModel.Filter.PolygonLayer)
        f_fca.addRow("Talep / Ada Nüfus Katmanı:", self.cmb_fca_demand)

        self.cmb_fca_pop_field = QgsFieldComboBox()
        self.cmb_fca_pop_field.setAllowEmptyFieldName(True)
        f_fca.addRow("Nüfus Sütunu (Boşsa 1 Kişi):", self.cmb_fca_pop_field)

        self.cmb_fca_roads = QgsMapLayerComboBox()
        self.cmb_fca_roads.setFilters(QgsMapLayerProxyModel.Filter.LineLayer)
        f_fca.addRow("Yol Ağı Katmanı:", self.cmb_fca_roads)

        self.spn_fca_cost = QDoubleSpinBox()
        self.spn_fca_cost.setRange(50.0, 10000.0)
        self.spn_fca_cost.setValue(800.0)
        self.spn_fca_cost.setSuffix(" metre")
        f_fca.addRow("Maksimum Servis Mesafesi:", self.spn_fca_cost)

        self.cmb_fca_facilities.layerChanged.connect(self._on_fca_fac_layer_changed)
        self.cmb_fca_demand.layerChanged.connect(self._on_fca_dem_layer_changed)

        if self.cmb_fca_facilities.currentLayer():
            self._on_fca_fac_layer_changed(self.cmb_fca_facilities.currentLayer())
        if self.cmb_fca_demand.currentLayer():
            self._on_fca_dem_layer_changed(self.cmb_fca_demand.currentLayer())

        l_fca.addLayout(f_fca)
        lbl_fca_hint = QLabel("💡 E2SFCA yöntemiyle aşırı yüklü (Overloaded) ve hizmet alamayan (Uncovered) nüfus tespit edilir.")
        lbl_fca_hint.setStyleSheet("color: #64748b; font-size: 8pt; font-style: italic;")
        l_fca.addWidget(lbl_fca_hint)

        self.btn_run_fca = QPushButton("  ⚖️ 2SFCA Kapasite ve Aşırı Yük Analizini Çalıştır")
        self.btn_run_fca.setObjectName("AccentButton")
        self.btn_run_fca.setCursor(_POINTING_HAND)
        self.btn_run_fca.clicked.connect(self._on_run_2sfca)
        l_fca.addWidget(self.btn_run_fca)
        l_fca.addStretch()
        sub_tabs.addTab(w_fca, "5. 2SFCA Yeterlilik")

        # -------------------------------------------------------------
        # Alt Sekme 6: A/B Senaryosu (Mevcut vs Meri Plan Kıyası)
        # -------------------------------------------------------------
        w_scen = QWidget()
        l_scen = QVBoxLayout(w_scen)
        f_scen = QFormLayout()

        self.cmb_scen_road_a = QgsMapLayerComboBox()
        self.cmb_scen_road_a.setFilters(QgsMapLayerProxyModel.Filter.LineLayer)
        f_scen.addRow("Senaryo A: Mevcut Yol Ağı:", self.cmb_scen_road_a)

        self.cmb_scen_road_b = QgsMapLayerComboBox()
        self.cmb_scen_road_b.setFilters(QgsMapLayerProxyModel.Filter.LineLayer)
        f_scen.addRow("Senaryo B: Meri / Öneri Plan Yol Ağı:", self.cmb_scen_road_b)

        self.spn_scen_radius = QDoubleSpinBox()
        self.spn_scen_radius.setRange(200.0, 5000.0)
        self.spn_scen_radius.setValue(800.0)
        self.spn_scen_radius.setSuffix(" metre")
        f_scen.addRow("Space Syntax Karşılaştırma Yarıçapı:", self.spn_scen_radius)

        l_scen.addLayout(f_scen)
        lbl_scen_hint = QLabel("💡 Delta NACH, Delta NAIN ve 4 Temel Plan Karar Başlığı (Kademelenme, Yayalaştırma vb.) otomatik üretilir.")
        lbl_scen_hint.setStyleSheet("color: #64748b; font-size: 8pt; font-style: italic;")
        l_scen.addWidget(lbl_scen_hint)

        self.btn_run_scen = QPushButton("  🔄 A/B Fark Haritası ve Plan Kararlarını Üret")
        self.btn_run_scen.setObjectName("PrimaryButton")
        self.btn_run_scen.setCursor(_POINTING_HAND)
        self.btn_run_scen.clicked.connect(self._on_run_scenario_compare)
        l_scen.addWidget(self.btn_run_scen)
        l_scen.addStretch()
        sub_tabs.addTab(w_scen, "6. A/B Senaryo")

        # -------------------------------------------------------------
        # Alt Sekme 7: Ada/Bina Ön Cephe ve Servis Noktası Bulucu
        # -------------------------------------------------------------
        w_cephe = QWidget()
        l_cephe = QVBoxLayout(w_cephe)
        f_cephe = QFormLayout()

        self.cmb_cephe_poly = QgsMapLayerComboBox()
        self.cmb_cephe_poly.setFilters(QgsMapLayerProxyModel.Filter.PolygonLayer)
        f_cephe.addRow("Ada / Parsel / Bina Katmanı:", self.cmb_cephe_poly)

        self.cmb_cephe_road = QgsMapLayerComboBox()
        self.cmb_cephe_road.setFilters(QgsMapLayerProxyModel.Filter.LineLayer)
        f_cephe.addRow("Yol Ağı Katmanı:", self.cmb_cephe_road)

        self.spn_cephe_dist = QDoubleSpinBox()
        self.spn_cephe_dist.setRange(5.0, 500.0)
        self.spn_cephe_dist.setValue(100.0)
        self.spn_cephe_dist.setSuffix(" metre")
        f_cephe.addRow("Maksimum Arama Mesafesi:", self.spn_cephe_dist)

        l_cephe.addLayout(f_cephe)
        self.btn_run_cephe = QPushButton("  🏢 Ön Cephe Segmentlerini ve Servis Noktalarını Üret")
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
    # NETWORK ANALİZ TETİKLEYİCİLERİ (ÖDEV 13)
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
                QgsProject.instance().addMapLayer(layer)
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
                QgsProject.instance().addMapLayer(lyr)

            lyr_n = self._to_vector_layer(nodes_out, f"Kavşak Merkezilikleri - Düğümler ({road_layer.name()})")
            if lyr_n and lyr_n.isValid():
                lyr_n.setName(f"Kavşak Merkezilikleri - Düğümler ({road_layer.name()})")
                QgsProject.instance().addMapLayer(lyr_n)

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
                QgsProject.instance().addMapLayer(lyr_r)

            lyr_d = self._to_vector_layer(desire_out, "Kuş Uçuşu Arzu Hatları ve Detour")
            if lyr_d and lyr_d.isValid():
                lyr_d.setName(f"Arzu Hatları ve Bariyerler (Detour > 1.35)")
                style_detour_barrier(lyr_d)
                QgsProject.instance().addMapLayer(lyr_d)

            lyr_m = self._to_vector_layer(matrix_out, "OD Mesafe Matrisi Tablosu")
            if lyr_m and lyr_m.isValid():
                lyr_m.setName("OD Mesafe Matrisi Tablosu")
                QgsProject.instance().addMapLayer(lyr_m)

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
                QgsProject.instance().addMapLayer(lyr_c)

            lyr_a = self._to_vector_layer(areas_out, "Yürüme İzokron Poligonları (Pedshed)")
            if lyr_a and lyr_a.isValid():
                lyr_a.setName(f"Yürüme İzokronları ({fac_layer.name()})")
                style_isochrone_bands(lyr_a)
                QgsProject.instance().addMapLayer(lyr_a)

            lyr_e = self._to_vector_layer(edges_out, "Erişilen Kırpılmış Yol Parçaları")
            if lyr_e and lyr_e.isValid():
                lyr_e.setName(f"Erişilen Yol Parçaları ({fac_layer.name()})")
                style_service_area(roads_layer=lyr_e)
                QgsProject.instance().addMapLayer(lyr_e)

            lyr_s = self._to_vector_layer(summary_out, "Pedshed Erişilebilirlik Karnesi")
            if lyr_s and lyr_s.isValid():
                lyr_s.setName("Pedshed Erişilebilirlik Karnesi (Tablo)")
                QgsProject.instance().addMapLayer(lyr_s)

            QMessageBox.information(
                self, "Başarılı",
                f"Yürüme izokronları ve pedshed analizi tamamlandı!\n"
                f"Eşikler: {breaks} metre (5, 10, 15 dk @ 4.8 km/s)\n"
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
                QgsProject.instance().addMapLayer(lyr_f)

            if out_f_pts:
                lyr_f_pts = self._to_vector_layer(out_f_pts, "2SFCA Donatı Giriş Noktaları")
                if lyr_f_pts and lyr_f_pts.isValid():
                    lyr_f_pts.setName(f"2SFCA Donatı Giriş Noktaları ({fac_layer.name()})")
                    style_facility_adequacy_points(lyr_f_pts)
                    QgsProject.instance().addMapLayer(lyr_f_pts)

            lyr_d = self._to_vector_layer(out_d, "2SFCA Talep Kapsama")
            if lyr_d and lyr_d.isValid():
                geom_d_desc = "Adalar/Binalar Poligon" if is_dem_poly else "Noktalar"
                lyr_d.setName(f"2SFCA Talep Kapsama ({dem_layer.name()}) [{geom_d_desc}]")
                style_fca_demand_points(lyr_d)
                QgsProject.instance().addMapLayer(lyr_d)

            if out_d_pts:
                lyr_d_pts = self._to_vector_layer(out_d_pts, "2SFCA Talep Merkez Noktaları")
                if lyr_d_pts and lyr_d_pts.isValid():
                    lyr_d_pts.setName(f"2SFCA Talep Merkez Noktaları ({dem_layer.name()})")
                    style_fca_demand_points(lyr_d_pts)
                    QgsProject.instance().addMapLayer(lyr_d_pts)

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
                QgsProject.instance().addMapLayer(lyr_diff)

            lyr_sum = self._to_vector_layer(sum_out, "A/B Senaryo Karşılaştırma Karnesi")
            if lyr_sum and lyr_sum.isValid():
                lyr_sum.setName("A/B Senaryo Karşılaştırma Karnesi (Tablo)")
                QgsProject.instance().addMapLayer(lyr_sum)

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

            if lines_layer:
                if isinstance(lines_layer, str):
                    lines_layer = QgsVectorLayer(lines_layer, f"Servis Bağlantı Çizgileri ({poly_layer.name()})", "ogr")
                else:
                    lines_layer.setName(f"Servis Bağlantı Çizgileri ({poly_layer.name()})")
                style_front_facade(lines_layer=lines_layer)
                QgsProject.instance().addMapLayer(lines_layer)

            if pts_layer:
                if isinstance(pts_layer, str):
                    pts_layer = QgsVectorLayer(pts_layer, f"Ön Cephe Servis Noktaları - Origin ({poly_layer.name()})", "ogr")
                else:
                    pts_layer.setName(f"Ön Cephe Servis Noktaları - Origin ({poly_layer.name()})")
                style_front_facade(points_layer=pts_layer)
                QgsProject.instance().addMapLayer(pts_layer)
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




