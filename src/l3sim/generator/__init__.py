"""Synthetic, reproducible L3 input-event generation."""

from .config import GeneratorConfig
from .generator import Generator, SyntheticEventGenerator

__all__ = ["Generator", "GeneratorConfig", "SyntheticEventGenerator"]
