"""From Alert to Action — frozen proof-of-concept package."""
from .config import CONFIG, build_config
from .pipeline import run

__version__ = "4.0.0-poc"
__all__ = ["CONFIG", "build_config", "run", "__version__"]
