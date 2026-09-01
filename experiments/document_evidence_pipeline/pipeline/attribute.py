"""Moved to src/evidence/attribute.py (FINAL_REPORT.md sec O). Re-exported here so the
experiment harness + tests keep working against the single production copy."""
from src.evidence.attribute import *  # noqa: F401,F403
from src.evidence import attribute as _m
__all__ = [n for n in dir(_m) if not n.startswith("_")]
