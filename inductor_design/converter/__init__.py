"""Converter-level sizing: translate a converter spec into inductor
requirements (required L, I_rms, I_pk, ripple, volt-seconds, duty range).
"""
from .buck import BuckSpec, BuckOperatingPoint, size_buck
from .boost import BoostSpec, BoostOperatingPoint, size_boost

__all__ = [
    "BuckSpec",
    "BuckOperatingPoint",
    "size_buck",
    "BoostSpec",
    "BoostOperatingPoint",
    "size_boost",
]
