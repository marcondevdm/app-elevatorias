# ⚡ Sistema de Telemetria e Gestão Analítica de Elevatórias

Aplicação Web completa, modular e interativa em **Streamlit** para processamento, análise e geração de relatórios de telemetria de Estações Elevatórias de Esgoto e Água (EEE).

---

## 🌟 Funcionalidades Principais

1. **Upload Flexível de Arquivos**:
   - Suporte para os 5 arquivos de entrada (CSV de operação, Excel De-Para com 4 abas, e os 3 CSVs de níveis).
   - Modo de demonstração com gerador sintético integrado para testes instantâneos.
2. **Seleção Dinâmica de Período**:
   - Permite processar intervalos livres (De / Até), meses específicos ou períodos semestrais sem nenhuma data fixa hardcoded no código.
3. **Pipeline de Dados Completo**:
   - Conversão de minutos para horas diárias por bomba (`HORAS_LIGADO`).
   - Cálculo de volume diário bombeado ($m^3/dia$) e vazão média horária ($Q_{média} = M3/24$).
   - Modelagem trigonométrica cíclica ($Q_{min}$ e $Q_{max}$) e algoritmo de enquadramento de outorga com varredura e travas de segurança.
   - Tratamento de níveis de reservatórios: Unpivot (melt), ajuste de fuso horário, escalonamento percentual, proteções estatísticas, hierarquia física ($Min \le Med \le Max \le 100\%$) e jitter anti-repetição.
4. **Visualizações em Alta Resolução (300 / 600 DPI)**:
   - **01. Horas Totais Diárias**: Gráfico de barras com valores inteiros arredondados no topo (`17h`, `24h`).
   - **02. Horas Individuais por Bomba**: Painel vertical de subplots para cada bomba (`BBA-01`, `BBA-02`, etc.) com cores específicas e rótulos de valores.
   - **03. Níveis de Reservatório**: Gráfico percentual com curvas de nível Médio, Máximo e Mínimo.
   - **04. Curvas de Vazão e Outorga**: $Q_{min}$, $Q_{max}$, $Q_{média}$, linha limite de outorga vermelha tracejada, zoom automático quando a vazão real for baixa e offsets adaptativos sem sobreposição de textos.
5. **Consulta e Edição Interativa**:
   - Tabela com editor embutido (`st.data_editor`) para consultar, ordenar, filtrar e alterar valores antes de exportar.
6. **Central de Exportação e Pacote ZIP**:
   - Download da planilha consolidada global (`base_consolidada_elevatorias.xlsx`).
   - Download de pacote `.ZIP` com estrutura de pastas organizada por elevatória e por mês contendo a planilha analítica e todos os 4 gráficos em alta resolução PNG.

---

## 📁 Estrutura do Projeto

```
app_elevatorias/
├── app.py                          # Interface principal Streamlit
├── requirements.txt                # Dependências da aplicação
├── README.md                       # Documentação técnica
├── pipeline/
│   ├── __init__.py
│   ├── telemetry.py                # Processamento minuto a minuto e cálculo de horas
│   ├── flow.py                     # Vazão, volume diário, ciclo trigonométrico e outorga
│   ├── levels.py                   # Melt dos níveis, fuso horário, escala %, correções e jitter
│   └── consolidator.py             # Consolidação geral e auditoria operacional
├── visualization/
│   ├── __init__.py
│   └── charts.py                   # Geração de gráficos temáticos em alta definição (Matplotlib)
├── export/
│   ├── __init__.py
│   └── packager.py                 # Empacotamento de planilhas e montagem de pacotes ZIP
└── sample_data/
    ├── __init__.py
    └── generator.py                # Gerador de dados sintéticos para testes e demonstrações
```

---

## 🚀 Como Executar o Aplicativo

### 1. Instalar as Dependências
Abra o terminal ou prompt de comando na pasta do projeto e instale os pacotes:

```bash
pip install -r requirements.txt
```

### 2. Iniciar o Aplicativo Streamlit
Execute o comando:

```bash
streamlit run app.py
```

O aplicativo abrirá automaticamente no seu navegador padrão no endereço `http://localhost:8501`.

---

## 📥 Estrutura Esperada dos Arquivos de Entrada

1. **`status_op_elevatorias.csv`**:
   - 1ª Coluna: `Timestamp` (ex: `01/06/2026 00:00:00`).
   - Demais Colunas: `<TAG_ELIPSE> Value` com status binário `1` (ligado) ou `0` (desligado).
2. **`depara_elevatorias_elipse.xlsx`**:
   - Aba **`BOMBAS_ELIPSE`**: Colunas `TAG_ELIPSE`, `ELEVATORIA`, `BOMBA`.
   - Aba **`CAPACIDADE_BOMBAS`**: Colunas `BOMBA`, `ELEVATORIA`, `Q_BOMBA` (em $m^3/h$).
   - Aba **`CAPACIDADE_MAX_ELEVATORIAS`**: Colunas `ELEVATORIA`, `Q_MAX_OUTORGA` (em $m^3/h$).
   - Aba **`RESERVATORIO_NIVEL`**: Colunas `TAG_ELIPSE`, `ELEVATORIA`.
3. **`nivel_medio.csv`**, **`nivel_maximo.csv`**, **`nivel_minimo.csv`**:
   - 1ª Coluna: `Timestamp`.
   - Demais Colunas: `<TAG_ELIPSE> Value` com o nível medido (em metros ou percentual).

---

## 📦 Estrutura do Pacote ZIP Gerado

Ao clicar em **"Gerar e Empacotar Pacote ZIP"**, o sistema gera automaticamente a seguinte árvore de diretórios:

```
pacote_elevatorias_YYYYMMDD.zip
├── base_consolidada_elevatorias.xlsx
├── relatorio_auditoria_outorga.xlsx
└── Elevatorias/
    ├── EEE 001/
    │   ├── 2026-06/
    │   │   ├── tabela_analitica_EEE_001_06_2026.xlsx
    │   │   ├── 01_horas_totais_EEE_001_06_2026.png
    │   │   ├── 02_horas_individuais_bombas_EEE_001_06_2026.png
    │   │   ├── 03_niveis_reservatorio_EEE_001_06_2026.png
    │   │   └── 04_vazao_e_outorga_EEE_001_06_2026.png
    │   └── ...
    └── EEE 002/
        └── ...
```
