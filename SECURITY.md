# Segurança

## Reportar uma vulnerabilidade

Não abra uma issue pública. Use **Security → Report a vulnerability** neste repositório (GitHub Private Vulnerability Reporting). Inclua versão, sistema operacional e passos para reproduzir. Nunca envie faturas ou extratos reais: use dados fictícios.

## Modelo de ameaça

O Meus Gastos roda só no computador do usuário (`127.0.0.1`), sem conta, nuvem ou conexão com bancos.

| Ameaça | Proteção |
| --- | --- |
| Site aberto no mesmo navegador chamando `http://127.0.0.1:8765/api/...` | `Sec-Fetch-Site` cross-site recusado; `Origin` e `Host` validados (contra DNS rebinding); POST só com JSON; cookie `SameSite=Strict` |
| Outros programas ou pessoas com acesso ao usuário do sistema | Com senha ativa: banco só no arquivo cifrado; API exige sessão (cookie `HttpOnly`) |
| Disco perdido, copiado ou roubado | Cofre AES-256-GCM; a cópia decifrada existe só na memória |
| Senha fraca ou tentativas repetidas | scrypt (N=2¹⁷, r=8, p=1, ~0,7 s por tentativa) e espera crescente a partir da 3ª falha |
| App esquecido aberto | Bloqueio automático (padrão 15 min) e *Bloquear agora* |
| PDF compartilhado e encaminhado | Senha opcional no PDF (AES-256, PDF 2.0 V5/R6); com senha, a mensagem de compartilhamento não leva valores |
| XSS / injeção | Todo dado exibido passa por escape; CSP sem scripts inline; CSV exportado protegido contra *formula injection* |
| Clickjacking / vazamento por referer | `frame-ancestors 'none'`, `X-Frame-Options`, `Referrer-Policy: no-referrer`, COOP/CORP |
| Geração de PDF | Chrome/Edge instalados, em modo headless, perfil temporário, sem rede de fundo, acesso com token de 2 minutos somente leitura |

Fora do escopo: um malware com controle do computador enquanto o app está desbloqueado (pode ler a memória ou o teclado).

## Criptografia em repouso

- `financas.cofre` = cabeçalho autenticado + banco SQLite inteiro cifrado com **AES-256-GCM**; qualquer alteração no arquivo é detectada.
- Uma chave de dados aleatória (256 bits) cifra o banco. Ela é guardada embrulhada duas vezes, por chaves derivadas com scrypt da **senha** e da **chave de recuperação** (125 bits, exibida uma única vez).
- Trocar a senha só reembrulha a chave; gerar nova chave de recuperação invalida a anterior.
- Cada alteração é cifrada e gravada de forma atômica (temporário + `fsync` + troca). Ao ativar a proteção, o banco aberto é sobrescrito e apagado depois de conferir que o cofre abre.
- **Sem a senha e sem a chave de recuperação não há como recuperar os dados.** Não existe porta dos fundos.

Implementação: [`finance/vault.py`](finance/vault.py) e [`finance/security.py`](finance/security.py). Testes: [`tests/test_security.py`](tests/test_security.py).

## Recomendações ao usuário

1. Ative a senha (Ajustes → *Proteger com senha*) e guarde a chave de recuperação fora do computador.
2. Ative a criptografia de disco do sistema (BitLocker, FileVault, LUKS): em SSD, arquivos apagados podem sobreviver à sobrescrita.
3. Use senha e bloqueio de tela no seu usuário do sistema.
4. Apague faturas, CSVs e PDFs baixados depois de importar ou compartilhar. Ajustes → *Cópias sem proteção* lista cópias antigas do banco na pasta de dados.
5. Combine a senha de um PDF por outro canal, nunca na mesma conversa do arquivo.

## Limites conhecidos

- Sem senha, o app funciona como antes: qualquer processo local pode usar a API. A proteção é opcional para ninguém ficar trancado para fora sem querer.
- A memória do processo contém os dados enquanto desbloqueado e o sistema pode levá-la ao arquivo de paginação; a criptografia de disco cobre esse caso.
- Extensões do navegador com acesso a todos os sites podem ler a página aberta.
- PDFs de bancos são lidos com pypdf; um arquivo malicioso poderia travar a importação (limite de 20 MB), sem acesso aos dados.
- Os executáveis ainda não são assinados digitalmente. Verifique o `SHA256SUMS.txt` de cada release ou gere o binário a partir do código.
