"""Open inductor design tool for power converters.

Start with :func:`inductor_design.design_buck` or
:func:`inductor_design.design_boost`.
"""
from __future__ import annotations

from .converter.buck import BuckSpec, size_buck
from .converter.boost import BoostSpec, size_boost
from .optimizer.search import design_buck, design_boost, DesignResult

__all__ = [
    "BuckSpec",
    "BoostSpec",
    "size_buck",
    "size_boost",
    "design_buck",
    "design_boost",
    "DesignResult",
]

__version__ = "0.1.0"
