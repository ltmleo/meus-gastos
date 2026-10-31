# PyInstaller recipe: one self-contained executable per platform.
#   Windows -> dist/MeusGastos.exe        (single file, no console window)
#   macOS   -> dist/MeusGastos.app        (app bundle, zipped by the release workflow)
#   Linux   -> dist/MeusGastos            (single file)
# Build: pyinstaller meusgastos.spec
import sys
from PyInstaller.utils.hooks import collect_submodules

version = {}
exec(open('finance/__version__.py', encoding='utf-8').read(), version)
block_cipher = None
datas = [('web', 'web'), ('LICENSE', '.'), ('THIRD_PARTY_NOTICES.md', '.')]

a = Analysis(
    ['app.py'],
    pathex=[],
    datas=datas,
    hiddenimports=collect_submodules('finance'),
    excludes=['tkinter', '_tkinter', 'pydoc_data', 'lib2to3', 'idlelib'],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

if sys.platform == 'darwin':
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='MeusGastos', console=False,
              upx=False, icon='packaging/icon.icns', target_arch=None)
    coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name='MeusGastos', upx=False)
    app = BUNDLE(coll, name='MeusGastos.app', icon='packaging/icon.icns', bundle_identifier='io.github.meusgastos',
                 info_plist={'CFBundleDisplayName': 'Meus Gastos', 'CFBundleShortVersionString': version['__version__'],
                             'NSHighResolutionCapable': True, 'LSMinimumSystemVersion': '11.0'})
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [], name='MeusGastos',
              console=sys.platform != 'win32',  # Linux: runs fine from a terminal or file manager
              upx=False,  # UPX-packed binaries trigger antivirus false positives
              icon='packaging/icon.ico' if sys.platform == 'win32' else None,
              runtime_tmpdir=None)
