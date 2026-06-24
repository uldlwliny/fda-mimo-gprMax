"""FDA-MIMO-GPR compatibility layer for gprMax."""

from .config import ScenarioConfig, ValidationError, load_scenario

__version__ = "0.1.0"

__all__ = ["ScenarioConfig", "ValidationError", "load_scenario", "__version__"]
