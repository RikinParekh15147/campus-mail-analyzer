"""Project location without importing optional application dependencies."""

from pathlib import Path
import sys

PROJECT = (
    Path(sys._MEIPASS)
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parents[2]
)
