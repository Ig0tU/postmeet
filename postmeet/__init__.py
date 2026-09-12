"""PostMeet: evidence-bound post-meeting extraction and YOOtheme hydration."""

__version__ = "1.0.0"

from .validation import validate
from .hydration import hydrate
from .pipeline import run
from .inject import inject_youtube_embed

__all__ = ["__version__", "validate", "hydrate", "run", "inject_youtube_embed"]
