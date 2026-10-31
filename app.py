import argparse
import base64
import hashlib
import http.client
import io
import json
import mimetypes
import re
import secrets
import socket
import subprocess
import sys
import threading
import webbrowser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode
from finance.repository import Repository, Locked
from finance.security import Security, SESSION_COOKIE
from finance.service import FinanceService
from finance.domain import CATEGORIES, PAYMENT_CHANNELS, check_people
from finance.analytics import summarize, insights
from finance.insights import dashboard, suggest_budgets, competence, apply_basis, complete_until
from finance.pdfexport import render_pdf
from finance.vault import WrongSecret, wipe
from finance.paths import PROJECT, data_dir, frozen, resource_dir
from finance.__version__ import __version__

PORTS = range(8765, 8785)
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
       "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
# Endpoints reachable without a session when the app is password protected.
# Closing the app is always allowed (also from the lock screen); it locks the vault first.
PUBLIC = {('GET', '/api/security/status'), ('POST', '/api/security/unlock'), ('POST', '/api/shutdown')}
# Folders inside a source checkout that may hold unprotected copies of financial data.
PROJECT_FOLDERS = {
    'output': ('Relatórios e exportações', 'output'),
    'tmp': ('Arquivos temporários', 'tmp'),
    'faturas': ('Faturas e extratos originais', 'faturas'),
}


class LocalHTTPServer(ThreadingHTTPServer):
    # Threads: browsers open several parallel (and idle speculative) connections for the JS modules.
    allow_reuse_address = False
    daemon_threads = True

    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def open_server(handler, port=None):
    for candidate in ([port] if port is not None else PORTS):
        try:
            return LocalHTTPServer(('127.0.0.1', candidate), handler)
        except OSError as error:
            if error.errno not in (98, 48, 10048, 10013) and getattr(error, 'winerror', None) not in (10048, 10013):
                raise
            if port is not None:
                raise OSError(f'A porta {port} está ocupada. Execute sem --port para escolher uma porta livre.') from error
    raise OSError('Não há uma porta livre entre 8765 e 8784. Feche uma instância do aplicativo e tente novamente.')


def exposure_folders(workspace, security):
    """key -> (label, folder, name shown). Backups live next to the database; the
    other folders only exist when running from a source checkout (workspace)."""
    folders = {'backups': ('Cópias antigas do banco', security.db_path.parent / 'backups', 'backups')}
    if workspace:
        folders.update({key: (label, Path(workspace) / name, name) for key, (label, name) in PROJECT_FOLDERS.items()})
    return folders


def exposed_files(workspace, security):
    """Files outside the vault that may contain financial data in clear text."""
    groups = []
    for key, (label, folder, shown) in exposure_folders(workspace, security).items():
        base = folder.resolve()
        if not base.is_dir():
            continue
        files = [p for p in base.rglob('*') if p.is_file() and not p.is_symlink() and p.name != '.gitkeep']
        if files:
            groups.append(dict(key=key, label=label, folder=shown, count=len(files), bytes=sum(p.stat().st_size for p in files),
                               files=[shown + '/' + str(p.relative_to(base)).replace('\\', '/') for p in sorted(files)[:12]]))
    if security.protected and security.db_path.is_file():
        groups.insert(0, dict(key='plaintext_db', label='Banco antigo sem criptografia', folder=str(security.db_path.name),
                              count=1, bytes=security.db_path.stat().st_size, files=[security.db_path.name]))
    return groups


def protect_pdf(data, password):
    from pypdf import PdfReader, PdfWriter
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(data)))
    writer.encrypt(user_password=password, owner_password=secrets.token_urlsafe(24), algorithm='AES-256')
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def instance_id(db_path):
    """Tells two copies of the app apart without revealing the data path."""
    return hashlib.sha256(str(Path(db_path).resolve()).encode()).hexdigest()[:16]


def port_file(db_path):
    return Path(db_path).resolve().parent / 'meusgastos.port'


def running_instance(db_path):
    """Port of an app already serving this database, if any.

    The running app writes its port next to the database, so only that port is
    probed (on Windows a refused localhost connection takes ~2 s, a full scan
    would delay every start). http.client talks to 127.0.0.1 directly: urllib
    would honour a system proxy."""
    try:
        port = int(port_file(db_path).read_text().strip())
    except (OSError, ValueError):
        return None
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
    try:
        connection.request('GET', '/api/security/status')
        status = json.loads(connection.getresponse().read())
    except (OSError, ValueError, http.client.HTTPException):
        return None
    finally:
        connection.close()
    return port if status.get('app') == 'meusgastos' and status.get('instance') == instance_id(db_path) else None


def make_handler(target, workspace=None if frozen() else PROJECT, on_shutdown=None):
    security = target if isinstance(target, Security) else Security(target.path, repository=target)
    repository = security.repository
    identity = dict(app='meusgastos', version=__version__, instance=instance_id(security.db_path))
    service = FinanceService(repository)
    printing = threading.Semaphore(1)  # one headless browser at a time

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Do not log personal information or passwords.

        def reply(self, value, status=200, content_type='application/json; charset=utf-8', download=None, cookie=None):
            data = json.dumps(value, ensure_ascii=False).encode() if isinstance(value, (dict, list)) else value
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
            self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
            self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=(), payment=(), usb=()')
            self.send_header('Content-Security-Policy', CSP)
            if download:
                self.send_header('Content-Disposition', f'attachment; filename="{download}"')
            if cookie is not None:
                # HttpOnly: invisible to scripts; SameSite=Strict: never sent by other sites.
                value_part = f'{SESSION_COOKIE}={cookie}' if cookie else f'{SESSION_COOKIE}=; Max-Age=0'
                self.send_header('Set-Cookie', f'{value_part}; HttpOnly; SameSite=Strict; Path=/')
            self.end_headers()
            self.wfile.write(data)

        def trusted(self):
            expected = f'127.0.0.1:{self.server.server_port}'
            if self.headers.get('Host') not in (expected, f'localhost:{self.server.server_port}'):
                return False  # DNS rebinding
            # Browsers mark cross-site requests; an <img> on a web page pointing here is refused.
            if self.headers.get('Sec-Fetch-Site') not in (None, 'same-origin', 'none'):
                return False
            origin = self.headers.get('Origin')
            return not origin or origin in (f'http://{expected}', f'http://localhost:{self.server.server_port}')

        def session(self):
            cookie = SimpleCookie(self.headers.get('Cookie', ''))
            return cookie[SESSION_COOKIE].value if SESSION_COOKIE in cookie else None

        def blocked(self, method, path):
            """False when allowed; True after sending the refusal."""
            if not path.startswith('/api/') or not security.protected or (method, path) in PUBLIC:
                return False
            if security.locked:
                self.reply({'error': 'App bloqueado.', 'locked': True}, 423)
                return True
            if security.valid_session(self.session()):
                security.touch()
                return False
            if method == 'GET' and security.valid_print_token(self.headers.get('X-Print-Token')):
                return False
            self.reply({'error': 'Sessão expirada. Entre novamente.', 'auth': True}, 401)
            return True

        def do_GET(self):
            if not self.trusted():
                return self.reply({'error':'Origem não permitida.'}, 403)
            parsed = urlparse(self.path)
            if self.blocked('GET', parsed.path):
                return
            try:
                return self.route_get(parsed)
            except Locked:
                return self.reply({'error': 'App bloqueado.', 'locked': True}, 423)

        def route_get(self, parsed):
            if parsed.path == '/api/security/status':
                return self.reply({**security.status(), **identity, 'session': security.valid_session(self.session())})
            if parsed.path == '/api/security/exposed':
                return self.reply({'groups': exposed_files(workspace, security)})
            if parsed.path == '/api/data':
                data = repository.list()
                for row in data['transactions']:
                    row['period'] = competence(row)  # Purchase month, used by default in the interface.
                purchase = apply_basis(data['transactions'])
                default_months = {'purchase': complete_until(purchase) or max((r['month'] for r in purchase), default=''),
                                  'invoice': max((r['month'] for r in data['transactions']), default='')}
                house = repository.household()
                return self.reply({**data, 'categories':CATEGORIES, 'people':repository.people(), 'household':house, 'app_version':12, 'default_months':default_months,
                                   'protected': security.protected})
            if parsed.path == '/api/dashboard':
                params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                try:
                    return self.reply(dashboard(repository.list()['transactions'], repository.budgets(),
                                                params.get('month', ''), params.get('person', ''), params.get('channel', ''),
                                                'invoice' if params.get('basis') == 'invoice' else 'purchase', repository.people()))
                except ValueError as error:
                    return self.reply({'error':str(error)},400)
            if parsed.path == '/api/budgets':
                query = parse_qs(parsed.query)
                basis = 'invoice' if query.get('basis', [''])[0] == 'invoice' else 'purchase'
                return self.reply({'budgets':repository.budgets(), 'suggested':suggest_budgets(repository.list()['transactions'], query.get('month', [''])[0] or None, basis=basis)})
            if parsed.path == '/api/settings':
                rules = repository.rules()
                return self.reply({'category_rules':[{'key':k, 'category':v} for k, v in sorted(rules['categories'].items())],
                                   'holder_rules':rules['holders'], 'own_accounts':sorted(rules['own_accounts'])})
            if parsed.path == '/api/category-review':
                return self.reply({'rows':service.review_categories()})
            if parsed.path in ('/api/summary', '/api/insights'):
                params = parse_qs(parsed.query)
                aggregate = summarize if parsed.path == '/api/summary' else insights
                try:
                    return self.reply(aggregate(repository.list()['transactions'], *[params.get(k,[''])[0] for k in ('month','person','channel','start','end')]))
                except ValueError as error:
                    return self.reply({'error':str(error)},400)
            if parsed.path == '/api/backup':
                data, name = security.backup()
                return self.reply(data, content_type='application/octet-stream', download=name)
            if parsed.path.startswith('/api/'):
                return self.reply({'error':'Não encontrado.'},404)
            web = (resource_dir()/'web').resolve()
            file = (web/parsed.path.lstrip('/')).resolve() if parsed.path != '/' else web/'index.html'
            if '.' not in Path(parsed.path).name:
                file = web/'index.html'  # Client-side routes.
            if web not in file.parents or not file.is_file():
                return self.reply({'error':'Não encontrado.'},404)
            types = {'.js':'text/javascript', '.css':'text/css', '.html':'text/html', '.svg':'image/svg+xml'}
            self.reply(file.read_bytes(), content_type=(types.get(file.suffix) or mimetypes.guess_type(file)[0] or 'text/plain')+'; charset=utf-8')

        def report_pdf(self, body):
            params = {k: body.get(k, '') for k in ('m', 'p', 'c', 'b')}
            if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', params['m'] or ''):
                raise ValueError('Informe o mês no formato AAAA-MM.')
            if params['p'] not in ('', *repository.people()) or params['c'] not in ('', *PAYMENT_CHANNELS) or params['b'] not in ('', 'invoice'):
                raise ValueError('Filtro inválido.')
            password = body.get('password') or ''
            if password and not (4 <= len(password) <= 128):
                raise ValueError('A senha do PDF deve ter de 4 a 128 caracteres.')
            query = {k: v for k, v in params.items() if v}
            token = security.new_print_token() if security.protected else None
            if token:
                query['pt'] = token
            if not printing.acquire(timeout=120):
                return self.reply({'error': 'Outro PDF está sendo gerado. Tente de novo.'}, 429)
            try:
                data = render_pdf(f'http://127.0.0.1:{self.server.server_port}/relatorio?{urlencode({**query, "print": "1"})}')
            except (RuntimeError, OSError, subprocess.SubprocessError) as error:
                return self.reply({'error':str(error) if isinstance(error, RuntimeError) else 'Não foi possível gerar o PDF.'},503)
            finally:
                printing.release()
                if token:
                    security.drop_print_token(token)
            if password:
                data = protect_pdf(data, password)
            return self.reply(data, content_type='application/pdf', download=f"relatorio-{params['m']}.pdf")

        def security_post(self, path, body):
            if path == '/api/security/unlock':
                try:
                    sid = security.unlock(password=body.get('password'), recovery=body.get('recovery'))
                except PermissionError as error:
                    return self.reply({'error': str(error), **security.status()}, 429)
                return self.reply({'ok': True}, cookie=sid)
            if path == '/api/security/lock':
                security.lock()
                return self.reply({'ok': True}, cookie='')
            if path == '/api/security/enable':
                sid, recovery = security.enable(body.get('password', ''))
                return self.reply({'recovery': recovery}, cookie=sid)
            if path == '/api/security/password':
                return self.reply({'ok': True}, cookie=security.change_password(body.get('current', ''), body.get('new', '')))
            if path == '/api/security/recovery':
                return self.reply({'recovery': security.new_recovery(body.get('password', ''))})
            if path == '/api/security/auto-lock':
                security.set_auto_lock(int(body.get('minutes', -1)))
                return self.reply({'ok': True})
            if path == '/api/security/disable':
                security.disable(body.get('password', ''))
                return self.reply({'ok': True}, cookie='')
            if path == '/api/security/wipe':
                key = body.get('group')
                group = next((g for g in exposed_files(workspace, security) if g['key'] == key), None)
                if not group:
                    raise ValueError('Nada para apagar neste grupo.')
                if key == 'plaintext_db':
                    removed = sum(wipe(Path(str(security.db_path) + s)) for s in ('', '-wal', '-shm', '-journal'))
                else:
                    base = exposure_folders(workspace, security)[key][1].resolve()
                    removed = sum(wipe(p) for p in base.rglob('*') if p.is_file() and not p.is_symlink() and p.name != '.gitkeep')
                return self.reply({'removed': removed})
            return self.reply({'error':'Não encontrado.'},404)

        def do_POST(self):
            if not self.trusted() or self.headers.get('Content-Type') != 'application/json':
                return self.reply({'error':'Origem ou formato não permitido.'},403)
            path = urlparse(self.path).path
            try:
                size = int(self.headers.get('Content-Length',0))
                if not 0 < size <= 28*1024*1024:
                    raise ValueError('Arquivo muito grande. Limite de 20 MB.')
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError('Requisição inválida.')
                if self.blocked('POST', path):
                    return
                if path.startswith('/api/security/'):
                    return self.security_post(path, body)
                if path == '/api/shutdown':
                    security.lock()
                    self.reply({'ok': True}, cookie='' if security.protected else None)
                    # Stop from another thread: shutdown() waits for this request to finish.
                    threading.Thread(target=on_shutdown or self.server.shutdown, daemon=True).start()
                    return
                if path == '/api/report.pdf':
                    return self.report_pdf(body)
                if path == '/api/preview':
                    content = base64.b64decode(body['content'],validate=True)
                    if len(content) > 20*1024*1024:
                        raise ValueError('Limite de 20 MB.')
                    return self.reply(service.preview(content,body['filename'],body.get('provider','auto'),body['month'],body.get('password','')))
                if path == '/api/confirm':
                    service.confirm(body['token'],body['rows'],body.get('holder_mapping'))
                elif path == '/api/save':
                    service.save_manual(body['row'],int(body['id']) if body.get('id') else None,body.get('remember',False))
                elif path == '/api/classify':
                    return self.reply(service.classify(body['description'], body.get('kind','expense'), int(body['id']) if body.get('id') else None))
                elif path == '/api/classify-group':
                    service.classify_group(body['ids'], body['category'], body['kind'], body.get('remember',False))
                elif path == '/api/category-review':
                    identifiers = set(body['ids'])
                    changes = [r for r in service.review_categories() if r['id'] in identifiers]
                    repository.apply_suggestions(changes)
                elif path == '/api/budgets':
                    values = body['budgets']
                    if not isinstance(values, dict) or any(k not in CATEGORIES or type(v) is not int or not 0 <= v <= 10**10 for k, v in values.items()):
                        raise ValueError('Orçamento inválido.')
                    repository.set_budgets(values, bool(body.get('replace')))
                elif path == '/api/bulk-update':
                    return self.reply({'updated':service.bulk_update(body['ids'], body['changes'])})
                elif path == '/api/own-account':
                    if body.get('remove'):
                        repository.forget_own_account(body['name'])
                    else:
                        return self.reply({'updated':len(repository.remember_own_account(body['name']))})
                elif path == '/api/people':
                    members, shared = check_people(body.get('members'), body.get('shared', ''))
                    repository.set_household(members, shared, body.get('renames') or {})
                elif path == '/api/forget-rule':
                    repository.forget_rule(body['key'])
                elif path == '/api/delete':
                    if body['kind'] not in ('imports','transactions'):
                        raise ValueError('Tipo inválido.')
                    repository.delete(body['kind'],int(body['id']))
                else:
                    return self.reply({'error':'Não encontrado.'},404)
                self.reply({'ok':True})
            except WrongSecret as error:
                self.reply({'error':str(error), **security.status()},401)
            except Locked:
                self.reply({'error':'App bloqueado.', 'locked':True},423)
            except PermissionError as error:
                self.reply({'error':str(error)},403)
            except (ValueError, KeyError, TypeError) as error:
                self.reply({'error':str(error)},400)
            except Exception:
                self.reply({'error':'Não foi possível processar. Confira o arquivo, a senha e o formato.'},400)
    return Handler

def main():
    parser = argparse.ArgumentParser(description='Meus Gastos: finanças pessoais e da família, 100% locais.')
    parser.add_argument('--port', type=int, default=None)
    parser.add_argument('--db', default=None, help='arquivo do banco (padrão: pasta de dados do usuário)')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--version', action='version', version=f'Meus Gastos {__version__}')
    args = parser.parse_args()
    folder = Path(args.db).resolve().parent if args.db else data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    if sys.stdout is None:  # packaged without a console window
        log = open(folder / 'meusgastos.log', 'w', encoding='utf-8', buffering=1)
        sys.stdout = sys.stderr = log
    db = args.db or str(folder / 'financas.sqlite3')
    existing = running_instance(db) if args.port is None else None
    if existing:
        print(f'O app já está aberto na porta {existing}.', flush=True)
        if not args.no_browser:
            webbrowser.open(f'http://127.0.0.1:{existing}/')
        return
    security = Security(db)
    server = open_server(make_handler(security), args.port)
    try:
        port_file(db).write_text(str(server.server_port))
    except OSError:
        pass  # only used to reopen the tab on a second launch
    url = f'http://127.0.0.1:{server.server_port}/'
    print(f'Meus Gastos {__version__} em {url} | dados em {folder} | Ctrl+C ou o botão Encerrar para fechar', flush=True)
    if security.protected:
        print('Banco criptografado: desbloqueie com sua senha no navegador.', flush=True)
    if not args.no_browser:
        try:
            if not webbrowser.open(url):
                print('Não foi possível abrir o navegador automaticamente. Use o endereço acima.', flush=True)
        except OSError:
            print('Não foi possível abrir o navegador automaticamente. Use o endereço acima.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        security.lock()
        security.close()
        server.server_close()
        port_file(db).unlink(missing_ok=True)


if __name__ == '__main__':
    main()
