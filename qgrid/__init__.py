from .grid import (
    enable,
    disable,
    set_defaults,
    on,
    off,
    set_grid_option,
    show_grid,
    QgridWidget,
    QGridWidget,
)
from ._version import get_versions


def _jupyter_nbextension_paths():
    return [
        {
            "section": "notebook",
            "src": "static",
            "dest": "qgrid",
            "require": "qgrid/extension",
        }
    ]


__all__ = [
    "enable",
    "disable",
    "set_defaults",
    "on",
    "off",
    "set_grid_option",
    "show_grid",
    "QgridWidget",
    "QGridWidget",
]

__version__ = get_versions()["version"]
del get_versions
