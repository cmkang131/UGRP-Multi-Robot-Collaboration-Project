"""Use the packaged handover hooks with the common modules in the enclosing repository."""
from pathlib import Path

__path__.append(str(Path(__file__).resolve().parents[4] / __name__))
