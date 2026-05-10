"""
Layer 5 - Rules Engine

Conflict detection rules:
- Minimum Separation (5 NM horizontal, 1000 ft vertical)
- Storm Avoidance (projected path into hazard zone)
- Wake Turbulence (heavy->light following distance)
"""

from .engine import run_all_rules
from .separation import check_minimum_separation
from .storm import check_storm_avoidance
from .wake_turbulence import check_wake_turbulence
from .wake_lookup import get_weight_class

__all__ = [
    "run_all_rules",
    "check_minimum_separation",
    "check_storm_avoidance", 
    "check_wake_turbulence",
    "get_weight_class",
]
