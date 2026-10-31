"""Where the app finds its files, from source or packaged as a single binary."""
import os
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent


def frozen():
    return bool(getattr(sys, 'frozen', False))


def resource_dir():
    """Read-only files shipped with the app (the web interface)."""
    return Path(getattr(sys, '_MEIPASS', PROJECT))


def data_dir():
    """User data. MEUSGASTOS_DATA wins; from source it stays in ./data as always."""
    custom = os.environ.get('MEUSGASTOS_DATA')
    if custom:
        path = Path(custom)
    elif not frozen():
        path = PROJECT / 'data'
    elif sys.platform == 'win32':
        path = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local') / 'MeusGastos'
    elif sys.platform == 'darwin':
        path = Path.home() / 'Library' / 'Application Support' / 'MeusGastos'
    else:
        path = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share') / 'meusgastos'
    path.mkdir(parents=True, exist_ok=True)
    if os.name == 'posix':
        path.chmod(0o700)  # only this user can list or read the data folder
    return path
