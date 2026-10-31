"""Monthly report as PDF, printed by a locally installed Chrome or Edge.

The report page itself is the layout (same charts as the app); the browser runs
headless against this local server only. Nothing is downloaded or sent anywhere.
"""
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

CANDIDATES = (
    r'%ProgramFiles%\Google\Chrome\Application\chrome.exe',
    r'%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe',
    r'%LocalAppData%\Google\Chrome\Application\chrome.exe',
    r'%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe',
    r'%ProgramFiles%\Microsoft\Edge\Application\msedge.exe',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
)


def find_browser():
    override = os.environ.get('MEUSGASTOS_BROWSER')
    if override and Path(override).is_file():
        return override
    for candidate in CANDIDATES:
        path = Path(os.path.expandvars(candidate))
        if path.is_file():
            return str(path)
    for name in ('google-chrome', 'chromium', 'chromium-browser', 'microsoft-edge', 'msedge', 'chrome'):
        found = shutil.which(name)
        if found:
            return found
    return None


def render_pdf(url, timeout=90):
    browser = find_browser()
    if not browser:
        raise RuntimeError('Chrome ou Edge não encontrado para gerar o PDF.')
    with tempfile.TemporaryDirectory() as folder:
        output = Path(folder) / 'relatorio.pdf'
        command = [browser, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
                   '--disable-extensions', '--hide-scrollbars', f'--user-data-dir={Path(folder) / "profile"}',
                   # No background traffic: updates, sync, crash reports or field trials while it prints.
                   '--disable-background-networking', '--disable-component-update', '--disable-sync',
                   '--disable-default-apps', '--disable-breakpad', '--disable-domain-reliability',
                   '--no-pings', '--metrics-recording-only', '--disable-features=MediaRouter,OptimizationHints',
                   '--no-pdf-header-footer', '--print-to-pdf-no-header', '--run-all-compositor-stages-before-draw',
                   '--virtual-time-budget=20000', f'--print-to-pdf={output}', url]
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout, creationflags=flags)
        # Some Windows launchers hand off to another process: wait for the finished file.
        deadline, size = time.time() + timeout, -1
        while time.time() < deadline:
            if output.is_file() and output.stat().st_size == size and size > 0:
                break
            size = output.stat().st_size if output.is_file() else -1
            time.sleep(0.4)
        data = output.read_bytes() if output.is_file() else b''
        if not data.startswith(b'%PDF'):
            raise RuntimeError('O navegador não conseguiu gerar o PDF.')
        return data
