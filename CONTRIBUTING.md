# Como contribuir

Obrigado pelo interesse! Issues e pull requests são bem-vindos, em português ou inglês.

## Regra número um: nunca publique dados reais

Faturas, extratos, prints, bancos de dados e logs com dados financeiros reais **não** devem aparecer em issues, PRs ou testes. Use dados fictícios. Se precisar mostrar um layout de banco, troque nomes, valores, números de cartão, CPF e estabelecimentos por exemplos inventados mantendo a estrutura.

## Ambiente

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py --port 8799 --no-browser   # usa ./data; MEUSGASTOS_DATA=/outra/pasta para isolar
python -m unittest discover -s tests -v
```

O front-end é JavaScript puro em módulos ES (`web/js`), sem build e sem dependências. Os gráficos são SVG desenhados em [`web/js/charts.js`](web/js/charts.js).

## Adicionar um banco ou formato

1. Crie um importador em `finance/importers/` que receba os bytes do arquivo e devolva `(rows, warnings, metadata)`, como [`nubank.py`](finance/importers/nubank.py). Cada linha precisa de `date`, `month`, `description`, `cents` (inteiro; gasto positivo, entrada negativa) e, quando souber, `kind`, `payment_channel`, `installment`, `holder`, `card`.
2. Faça a detecção pelo **conteúdo** em [`auto.py`](finance/importers/auto.py) (cabeçalhos, textos fixos do layout), nunca pelo nome do arquivo.
3. Escreva testes com um arquivo **fictício** no formato do banco (CSV inline no teste, ou texto extraído de PDF com valores inventados). Cubra estornos, parcelas, IOF e totais.
4. Documente o formato em [`docs/importadores.md`](docs/importadores.md).

Não é preciso escrever regras de categoria para estabelecimentos locais: o app aprende com as correções de cada usuário. Regras em [`classification.py`](finance/classification.py) devem ser de marcas nacionais ou palavras genéricas.

## Pull requests

- Um assunto por PR, com testes.
- `python -m unittest discover -s tests` precisa passar nos três sistemas (o CI roda Windows, macOS e Linux).
- Nada de chamadas de rede, telemetria, CDNs ou dependências novas no navegador. Dependências Python novas precisam de boa justificativa (cada uma vai para dentro do executável).
- Mudanças de segurança: leia [SECURITY.md](SECURITY.md) e explique o impacto no PR.

Ao contribuir, você concorda em licenciar sua contribuição sob a [AGPL-3.0](LICENSE).
