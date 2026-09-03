"""DUT AI Club pull-request preview and review automation."""
import importlib.metadata

DIST_NAME = "dut-ai-pr-preview-system"

try:
    # Single source of truth is pyproject.toml, read through the installed
    # distribution. A hand-written literal here drifted to 1.0.6 while
    # pyproject said 1.1.0, and `--version` (which already read the metadata)
    # disagreed with `src.__version__` for several releases.
    __version__ = importlib.metadata.version(DIST_NAME)
except importlib.metadata.PackageNotFoundError:  # running from a plain checkout
    __version__ = "0+unknown"
