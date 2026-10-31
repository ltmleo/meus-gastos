# Componentes de terceiros

O Meus Gastos é distribuído sob a [AGPL-3.0](LICENSE). Os executáveis incluem os componentes abaixo, cada um sob a sua licença.

| Componente | Uso | Licença |
| --- | --- | --- |
| [Python](https://www.python.org/) | Interpretador embutido no executável | PSF License |
| [pypdf](https://github.com/py-pdf/pypdf) | Leitura de faturas em PDF e senha nos relatórios | BSD-3-Clause |
| [cryptography](https://github.com/pyca/cryptography) | AES-256-GCM do cofre e AES-256 dos PDFs | Apache-2.0 ou BSD-3-Clause |
| [cffi](https://github.com/python-cffi/cffi) / [pycparser](https://github.com/eliben/pycparser) | Dependências do cryptography | MIT / BSD-3-Clause |
| [OpenSSL](https://www.openssl.org/) | Embutido no cryptography | Apache-2.0 |
| [PyInstaller](https://pyinstaller.org/) (bootloader) | Empacotamento em um único executável | GPL-2.0 com exceção para o bootloader |

A paleta dos gráficos segue uma paleta categórica validada para daltonismo; os ícones são desenhos próprios em SVG. A interface não carrega fontes, scripts ou estilos de terceiros.
