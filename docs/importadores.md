# Formatos de importação

A detecção é feita pelo conteúdo do arquivo, não pelo nome ou extensão. O mesmo arquivo (SHA-256) nunca é importado duas vezes, mesmo renomeado. Toda importação passa por uma prévia: nada é gravado antes de *Salvar*. Remover uma importação remove os lançamentos dela.

## Santander · fatura do cartão (PDF)

- Lê os blocos de cada titular, incluindo cartões adicionais e nomes abreviados. Na primeira leitura, o 1º titular é associado à 1ª pessoa cadastrada, o 2º à 2ª; a escolha fica lembrada.
- Separa compras nacionais, internacionais (coluna em dólar), IOF, estornos e parcelas (`03/05`).
- Pagamentos da fatura anterior e linhas de valor zero são excluídos.
- Compara a soma lida com o total informado no PDF e mostra a diferença na prévia.
- Datas sem ano usam o ano do vencimento (ou o anterior). PDFs digitalizados (imagem) não são suportados: não há OCR.

## Santander · extrato consolidado (PDF)

- Importa só a movimentação da conta corrente e exige que entradas, saídas e saldos confiram com o resumo do extrato.
- Descrições em várias linhas e datas omitidas no mesmo dia são reconhecidas.
- PIX enviados começam como gasto e recebidos como ganho; pagamento de cartão e vencimento/resgate de CDB viram transferência. Saldos, agendamentos, poupança e posição de investimentos não entram.

## Nubank · fatura (CSV `date,title,amount`)

- Compras são gastos no crédito; valores negativos são estornos ou IOF devolvido; o sufixo *Parcela X/Y* vira parcela.
- *Pagamento recebido* é excluído (o pagamento aparece no extrato da conta).
- O mês vem do nome original `Nubank_AAAA-MM-DD.csv`; se o arquivo foi renomeado, a prévia pede o mês.

## Nubank · conta (CSV `Data,Valor,Identificador,Descrição`)

- Sinais convertidos para a convenção do app (saída positiva, entrada negativa).
- Pagamento de fatura e aplicações/resgates reconhecidos viram transferência.
- O nome do destinatário é separado de CPF, agência e conta para permitir regras por destinatário.

## CSV padrão (qualquer banco)

Colunas `data`, `descricao`, `valor`; separador `;` ou `,`; UTF-8 ou Windows-1252. Datas `dd/mm/aaaa` ou `aaaa-mm-dd`. Valores positivos são gastos e negativos são estornos/entradas. Com separador vírgula, coloque valores com vírgula decimal entre aspas.

```csv
data;descricao;valor
02/09/2026;Mercado;123,45
03/09/2026;Estorno;-10,00
```

## Contas próprias

PIX entre contas de vocês não são gasto nem ganho. Em Ajustes → *Contas próprias*, cadastre o nome completo exatamente como aparece no PIX: os lançamentos passam a ser transferências.
