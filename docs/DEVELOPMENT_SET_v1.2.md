# pln3113_nip 1.2.0 — development set

Written 2026-11-04 by the master engineer from an audit of 1.1.6 (NIP-AUDIT,
offscreen on QGIS 3.44.12 and 4.2.0) and an inventory of the student plugin
Kent Öngörü v1.0.0 by Berkay Memiş (KO-INV; GPL-2.0-or-later, compatible).
Evidence: `nip/nip-audit`, `nip/ko-inv` in the session scratchpad. The owner
asked to merge Kent Öngörü's features into this plugin "daha da güzelini
yaparak" — better than the original. The plugin stays Turkish-language.

## 1. Problems in 1.1.6
| # | Harm | Where |
|---|------|-------|
| N1 | Carries a pre-4.23.0 PlanX engine copy: NAIN `(NC+2)^1.2/(TD+2)` and undirected choice (dead end gets choice 1); scenario thresholds tuned to the old scale. | `core/planx_engine/syntax.py:55`, `graphs.py`, `alg_scenario_compare.py:183-201` |
| N2 | A boundary (or road) layer in another CRS: every block removed / road lengths in the wrong CRS, no warning. | `alg_nip_population.py:188-200` |
| N3 | Geographic input with project ellipsoid NONE: areas in square degrees, every block dropped, population 0, no warning. | `alg_nip_population.py:183-187`, `nip_calculator.py:131-136` |
| N4 | Tests check no numbers: DOP ×0.5, population ×0.5, NAIN formula, choice ×6, Ek-2 6.5→0.65 all survive. | `tests/` |
| N5 | Dark themes: inline dock colours 1.02–2.5:1; default #64748b 4.14:1. | `dock.py` |
| N6 | Without a boundary an invented 18 % road area decides the legal DOP verdict ("YASAL SINIRI AŞIYOR"). | `nip_calculator.py:326-329` |
| N7 | Ek-2 standards without a source; disagree with planx_mpyy_studio; SPOR ALANI counted as green, ÖZEL SAĞLIK counted toward the public standard. | `tire_constants.py:378-409` |
| N8 | Dock minimum width 603-622 px (half of a 1366 screen). | `dock.py` |
| N9 | Cancel writes partial space-syntax arrays; population tool never checks cancel. | `alg_space_syntax.py:101-111` |
| N10 | Tire hard-coded (+26,000 rural population, Tire-only benchmarks, "Tire NİP" titles) in a Turkey-wide tool. | `nip_calculator.py:443`, `dock.py:159`, `main_plugin.py:75` |
| N11 | Metadata claims "nüfus projeksiyonları" but there is only a manual target spinbox. | `dock.py:1300`, `alg_nip_population.py:112` |
| N12 | NULL population/capacity silently 1 or default; `require_projected` accepts feet; CHANGELOG gaps; README "Aksiyel"; 45 % ceiling labelled "Hedef". | |

## 2. Delivers
1. The corrected PlanX 4.23.0 engine (directed choice, NAIN = NC^1.2/(TD+2)),
   scenario thresholds re-derived; cancel never writes partial results.
2. Correct inputs: boundary and road layers transformed to the block CRS;
   a fixed ellipsoid for geographic data; dropped blocks counted and warned;
   the DOP verdict needs a real boundary (an estimate is labelled as such);
   NULLs counted; feet CRSs refused; Tire settings become parameters.
3. **Kent Öngörü features, done better** (rewritten, no copied code):
   - Nüfus projeksiyonu: aritmetik, geometrik, İller Bankası (warns when the
     rate is clamped), en küçük kareler, polinom, lojistik (warns at the K
     boundary; Pearl-Reed optional); R² and backtest; a Processing algorithm
     with a table output; the dock fills the target population from it.
     ("Üstel" is dropped — it equals geometric for two points.)
   - Kohort-bileşen projeksiyonu: 5-year steps, correct birth→0-4 survival,
     target years that are not multiples of 5 interpolated, Sx/ASFR as data
     files with their sources, migration as rate or persons with an age
     profile; dependency ratios, ageing index, median age; a pyramid.
   - Ekonomik taban göçü ("çalışan başına nüfus").
   - Mahalle dağıtımı: proportional / zone share / capacity-capped with
     redistribution, largest-remainder rounding, joined by key.
   - Kırılganlık endeksi (pay/payda) and a composite index: matching through
     the existing `norm_tr`, missing indicator = neutral (1) with a count,
     density-based thresholds, flood elevation/slope directions corrected,
     joined by key, escaped HTML; Jenks/quantile/equal/geometric breaks.
   - Not brought in: the student's facility standards table, its xlsx
     writer, its Qt charts, a second modal dialog.
4. Legible, narrower dock (palette colours from `ui_theme`, ≥ 4.5:1 in the
   three themes, ≤ ~340 px minimum width) with the new tools reachable.
5. Value tests for every number above; honest Turkish docs with attribution:
   "Nüfus projeksiyonu, dağıtım ve kırılganlık özellikleri Kent Öngörü
   v1.0.0 (Berkay Memiş, GPL-2.0-or-later) temel alınarak yeniden yazıldı;
   pay/payda yöntemi PLN3113 stüdyosundan."

Owner follow-up (not decidable here): verify the Ek-2 values against the
official regulation text; confirm the full name of "Burcu hoca" for the
pay/payda attribution.

## 3. Contracts
- C1 (NIP-PROJ): `core/projection.py` `project_trend(years, populations,
  method, target_year) -> dict(value, series, r2, backtest_pct, warnings)`;
  methods `aritmetik, geometrik, iller_bankasi, regresyon, polinom, lojistik`;
  `core/cohort.py` `project_cohort(base, params, target_year) -> dict`.
  Processing ids: `pln3113_nip:nufus_projeksiyonu`,
  `pln3113_nip:kohort_projeksiyonu`, `pln3113_nip:mahalle_dagitimi`,
  `pln3113_nip:kirilganlik_endeksi`.
- C2 (NIP-UI): the dock calls C1 functions/algorithms only; no formulas in
  `dock.py`.

## 4. Implementers
| Agent | Owns |
|-------|------|
| NIP-ENG | `core/planx_engine/**`, `algorithms/alg_space_syntax.py`, `alg_scenario_compare.py`, `alg_network_centrality.py`, `alg_service_areas.py`, `alg_od_matrix.py`, `alg_erisme_havzasi.py`, new `tests/test_engine_values.py` |
| NIP-FIX | `algorithms/alg_nip_population.py`, `alg_facility_adequacy.py`, `alg_saha_bina_analysis.py`, `core/nip_calculator.py`, `core/tire_constants.py`, `core/field_estimator.py`, `core/nip_workspace.py`, `algorithms/alg_nip_workspace.py`, `tests/test_pure_logic.py`, new `tests/test_nip_values_qgis.py` |
| NIP-PROJ | new `core/projection.py`, `core/cohort.py`, `core/allocation.py`, `core/vulnerability.py`, new data files, new algorithms (`alg_nufus_projeksiyonu.py`, `alg_kohort_projeksiyonu.py`, `alg_mahalle_dagitimi.py`, `alg_kirilganlik_endeksi.py`), registration in `provider.py`, new `tests/test_projection.py`, `tests/test_new_algorithms_qgis.py` |
| NIP-UI | `dock.py`, `ui_theme.py`, `main_plugin.py`, `forms/**`, `core/nip_dashboard_builder.py`, `core/symbology_manager.py`, `tests/smoke_plugin.py`, new `tests/test_dock_qgis.py` |
| NIP-DOCS | `README.md`, `CHANGELOG.md`, `CITATION.cff`, `metadata.txt`, `docs/**` except this file |

## 5. Rules
Offscreen; every QGIS run with a fresh `QGIS_CUSTOM_CONFIG_PATH`; zero public
network; QGIS 3.28 / Python 3.9, both runtimes; Hub scan rules; red before
green; no git writes; no pf verify. Never copy code from Kent Öngörü; the
extracted source (read-only reference) is in the session scratchpad
`nip/ko-src/kent_ongoru`.

## 6. Status
- 2026-11-04: audit and inventory done; set written; implementers launched.
