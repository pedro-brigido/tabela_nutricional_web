# Terracota | Calculadora Nutricional

Calculadora nutricional em conformidade com a **RDC 429/2020** e **IN 75/2020** (ANVISA). Projeto Python com pacote instalável e aplicação Flask.

## Requisitos

- Python 3.10+

## Instalação

```bash
pip install -r requirements.txt
# Opcional: instalar o pacote em modo editável para desenvolvimento
pip install -e .
```

## Como executar

```bash
python app.py
```

Acesse [http://localhost:5000](http://localhost:5000) no navegador.

## Estrutura do projeto

```
.
├── app.py                 # Aplicação Flask (rotas, API, import Excel)
├── pyproject.toml         # Configuração do pacote Python
├── requirements.txt
├── src/
│   └── tabela_nutricional/   # Pacote principal
│       ├── __init__.py
│       └── calculator.py    # Cálculo ANVISA (RDC 429/2020, IN 75/2020)
├── tests/
│   └── test_calculator.py
├── static/
│   ├── app.js             # Frontend (wizard, chamadas à API)
│   └── styles.css
├── templates/
│   └── index.html
└── legacy/                # Implementação antiga em JavaScript (referência)
    ├── README.md
    ├── anvisaCalculator.js
    ├── script.js
    ├── index.html
    └── styles.css
```

## API

- **POST /api/calculate** — Recebe `{ product, ingredients }` e retorna dados nutricionais calculados.
- **POST /api/import-excel** — Recebe arquivo `.xlsx` e retorna lista de ingredientes extraídos.

## Importação de Excel

O arquivo Excel deve conter colunas identificáveis por nomes como: Nome/Ingrediente, Quantidade/Qtd, Kcal, Carboidratos, Proteínas, Gorduras, Fibra, Sódio, etc. O formato `.xlsx` é suportado (requer `openpyxl`).

## Testes

```bash
pip install -e ".[dev]"
pytest
```

## Legado

A pasta `legacy/` contém a versão original em JavaScript (calculadora e app standalone). A aplicação atual usa o backend Python e o frontend em `static/app.js` (API).
