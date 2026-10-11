# -*- coding: utf-8 -*-
"""nip_eklenti_01 core package."""
from .tire_constants import (
    TIRE_POPULATION_BENCHMARKS,
    resolve_nip_density,
    identify_facility_category,
    MPYY_DONATI_STANDARTLARI,
    get_employment_for_function,
    get_trips_for_function
)
try:
    from .cleaner import GeometryCleanerEngine
    from .nip_calculator import NipCalculatorEngine
    from .field_estimator import FieldEstimatorEngine
except ImportError:
    GeometryCleanerEngine = None  # type: ignore[assignment,misc]
    NipCalculatorEngine = None    # type: ignore[assignment,misc]
    FieldEstimatorEngine = None   # type: ignore[assignment,misc]

__all__ = [
    "TIRE_POPULATION_BENCHMARKS",
    "resolve_nip_density",
    "identify_facility_category",
    "MPYY_DONATI_STANDARTLARI",
    "get_employment_for_function",
    "get_trips_for_function",
    "GeometryCleanerEngine",
    "NipCalculatorEngine",
    "FieldEstimatorEngine"
]
