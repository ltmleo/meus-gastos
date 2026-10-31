// The headless browser that prints the PDF has no session cookie: the server hands it
// a short-lived, read-only token in the URL instead.
const printToken = new URLSearchParams(location.search).get('pt');
let onLocked = () => {};
export const whenLocked = handler => { onLocked = handler; };

export async function api(path, body) {
  const headers = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (printToken) headers['X-Print-Token'] = printToken;
  const options = body === undefined ? { headers } : { method: 'POST', headers, body: JSON.stringify(body) };
  let response;
  try {
    response = await fetch('/api/' + path, options);
  } catch {
    throw new Error('Servidor local não respondeu. Confira se a janela do aplicativo está aberta.');
  }
  const data = await response.json().catch(() => ({}));
  if ((response.status === 423 || (response.status === 401 && data.auth)) && !path.startsWith('security/')) {
    onLocked(data);
    throw new Error(data.error || 'App bloqueado.');
  }
  if (!response.ok) throw Object.assign(new Error(data.error || 'Não foi possível concluir a operação.'), { data, status: response.status });
  return data;
}

/** POST that returns a file (e.g. the PDF report). */
export async function apiFile(path, body) {
  const headers = { 'Content-Type': 'application/json' };
  const response = await fetch('/api/' + path, { method: 'POST', headers, body: JSON.stringify(body) });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    if (response.status === 423 || response.status === 401) onLocked(data);
    throw new Error(data.error || 'Falha ao gerar o arquivo.');
  }
  return response.blob();
}

export const query = params => new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
