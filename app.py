from __future__ import annotations
import os
import sys

# Adiciona o diretório raiz ao sys.path para garantir imports na nuvem
DIRETORIO_RAIZ = os.path.dirname(os.path.abspath(__file__))
if DIRETORIO_RAIZ not in sys.path:
    sys.path.insert(0, DIRETORIO_RAIZ)

import streamlit as st
import pandas as pd
import numpy as np
import io
import gc
from datetime import date, datetime
import matplotlib.pyplot as plt

# Import dos módulos internos do pipeline
from pipeline.telemetry import processar_telemetria_bombas
from pipeline.flow import calcular_vazoes_e_outorga
from pipeline.levels import processar_niveis
from pipeline.consolidator import consolidar_dados_analiticos, gerar_relatorio_auditoria
from visualization.charts import (
    gerar_grafico_horas_totais_diario,
    gerar_grafico_horas_individuais_bombas,
    gerar_grafico_niveis,
    gerar_grafico_vazao,
    figura_para_bytes_png
)
from export.packager import (
    gerar_excel_consolidado,
    gerar_pacote_zip_completo,
    gerar_excel_simples_bytes
)
from sample_data.generator import gerar_dados_amostra_completos

# =========================================================================
# CONFIGURAÇÃO GERAL DA PÁGINA STREAMLIT
# =========================================================================
st.set_page_config(
    page_title="App Elevatórias | Telemetria & Gestão Analítica",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilização CSS customizada
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1772B1;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #adb5bd;
        margin-bottom: 1.5rem;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 48px;
        white-space: pre-wrap;
        border-radius: 6px 6px 0px 0px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


# =========================================================================
# FUNÇÕES DE LEITURA OTIMIZADAS PARA MEMÓRIA E NUVEM
# =========================================================================
def ler_csv_rapido(uploaded_file) -> pd.DataFrame | None:
    """Lê CSV de forma rápida e com baixo uso de memória detectando o separador na 1ª linha."""
    if uploaded_file is None:
        return None
    try:
        sample_bytes = uploaded_file.read(4096)
        uploaded_file.seek(0)
        sample_str = sample_bytes.decode('utf-8', errors='ignore')
        first_line = sample_str.split('\n')[0] if '\n' in sample_str else sample_str
        sep = ';' if ';' in first_line else (',' if ',' in first_line else '\t')
        return pd.read_csv(uploaded_file, sep=sep, low_memory=False)
    except Exception as e:
        st.error(f"Erro ao ler CSV {uploaded_file.name}: {e}")
        return None

def ler_excel_abas(uploaded_file) -> dict[str, pd.DataFrame]:
    """Lê todas as abas do Excel de-para."""
    if uploaded_file is None:
        return {}
    try:
        excel_file = pd.ExcelFile(uploaded_file)
        sheets = {}
        for s in excel_file.sheet_names:
            sheets[s.upper().strip()] = pd.read_excel(excel_file, sheet_name=s)
        return sheets
    except Exception as e:
        st.error(f"Erro ao ler Excel {uploaded_file.name}: {e}")
        return {}


# =========================================================================
# INICIALIZAÇÃO DO ESTADO DA SESSÃO (SESSION STATE)
# =========================================================================
if 'dados_carregados' not in st.session_state:
    st.session_state['dados_carregados'] = False
if 'df_geral_analitico' not in st.session_state:
    st.session_state['df_geral_analitico'] = pd.DataFrame()
if 'resumo_bombas' not in st.session_state:
    st.session_state['resumo_bombas'] = pd.DataFrame()
if 'resumo_agregado' not in st.session_state:
    st.session_state['resumo_agregado'] = pd.DataFrame()
if 'df_niveis' not in st.session_state:
    st.session_state['df_niveis'] = pd.DataFrame()
if 'auditoria_resultado' not in st.session_state:
    st.session_state['auditoria_resultado'] = {}

# Armazenamento em cache de bases carregadas
if 'df_bruto_cached' not in st.session_state:
    st.session_state['df_bruto_cached'] = None
if 'df_depara_bombas_cached' not in st.session_state:
    st.session_state['df_depara_bombas_cached'] = None
if 'df_capacidade_bombas_cached' not in st.session_state:
    st.session_state['df_capacidade_bombas_cached'] = None
if 'df_max_outorga_cached' not in st.session_state:
    st.session_state['df_max_outorga_cached'] = None
if 'df_depara_niveis_cached' not in st.session_state:
    st.session_state['df_depara_niveis_cached'] = None
if 'df_nivel_medio_cached' not in st.session_state:
    st.session_state['df_nivel_medio_cached'] = None
if 'df_nivel_maximo_cached' not in st.session_state:
    st.session_state['df_nivel_maximo_cached'] = None
if 'df_nivel_minimo_cached' not in st.session_state:
    st.session_state['df_nivel_minimo_cached'] = None


# =========================================================================
# BARRA LATERAL (SIDEBAR): UPLOAD, PARÂMETROS E FILTROS
# =========================================================================
st.sidebar.title("⚡ Painel de Controle")

fonte_dados = st.sidebar.radio(
    "📂 Origem dos Dados:",
    ["Upload das Bases", "Usar Dados de Exemplo / Demonstração"],
    index=0
)

if fonte_dados == "Upload das Bases":
    st.sidebar.subheader("1. Upload das Bases")
    
    metodo_upload = st.sidebar.radio(
        "Modo de Upload:",
        ["📁 Soltar Todos os Arquivos Juntos (Recomendado)", "📄 Campos Individuais"],
        index=0
    )

    if metodo_upload == "📁 Soltar Todos os Arquivos Juntos (Recomendado)":
        arquivos_multi = st.sidebar.file_uploader(
            "Arraste e solte os arquivos CSV e XLSX aqui:",
            type=["csv", "xlsx"],
            accept_multiple_files=True,
            help="Você pode selecionar todos os 5 arquivos de uma vez e soltá-los aqui."
        )

        if arquivos_multi:
            for f in arquivos_multi:
                nome_lower = f.name.lower()
                if nome_lower.endswith('.xlsx'):
                    abas = ler_excel_abas(f)
                    st.session_state['df_depara_bombas_cached'] = abas.get('BOMBAS_ELIPSE', list(abas.values())[0] if abas else None)
                    st.session_state['df_capacidade_bombas_cached'] = abas.get('CAPACIDADE_BOMBAS', None)
                    st.session_state['df_max_outorga_cached'] = abas.get('CAPACIDADE_MAX_ELEVATORIAS', None)
                    st.session_state['df_depara_niveis_cached'] = abas.get('RESERVATORIO_NIVEL', None)
                elif 'status' in nome_lower or 'op' in nome_lower or 'telemetria' in nome_lower:
                    st.session_state['df_bruto_cached'] = ler_csv_rapido(f)
                elif 'medio' in nome_lower or 'med' in nome_lower:
                    st.session_state['df_nivel_medio_cached'] = ler_csv_rapido(f)
                elif 'maximo' in nome_lower or 'max' in nome_lower:
                    st.session_state['df_nivel_maximo_cached'] = ler_csv_rapido(f)
                elif 'minimo' in nome_lower or 'min' in nome_lower:
                    st.session_state['df_nivel_minimo_cached'] = ler_csv_rapido(f)
                else:
                    if st.session_state['df_bruto_cached'] is None:
                        st.session_state['df_bruto_cached'] = ler_csv_rapido(f)

            st.sidebar.success("✅ Arquivos carregados e identificados!")

    else:
        file_status = st.sidebar.file_uploader("1. Status de Operação (CSV)", type=["csv"], key="upl_status")
        file_depara = st.sidebar.file_uploader("2. De-Para e Capacidades (XLSX)", type=["xlsx"], key="upl_depara")
        file_nivel_med = st.sidebar.file_uploader("3. Nível Médio (CSV)", type=["csv"], key="upl_med")
        file_nivel_max = st.sidebar.file_uploader("4. Nível Máximo (CSV)", type=["csv"], key="upl_max")
        file_nivel_min = st.sidebar.file_uploader("5. Nível Mínimo (CSV)", type=["csv"], key="upl_min")

        if file_status:
            st.session_state['df_bruto_cached'] = ler_csv_rapido(file_status)
        if file_depara:
            abas = ler_excel_abas(file_depara)
            st.session_state['df_depara_bombas_cached'] = abas.get('BOMBAS_ELIPSE', list(abas.values())[0] if abas else None)
            st.session_state['df_capacidade_bombas_cached'] = abas.get('CAPACIDADE_BOMBAS', None)
            st.session_state['df_max_outorga_cached'] = abas.get('CAPACIDADE_MAX_ELEVATORIAS', None)
            st.session_state['df_depara_niveis_cached'] = abas.get('RESERVATORIO_NIVEL', None)
        if file_nivel_med:
            st.session_state['df_nivel_medio_cached'] = ler_csv_rapido(file_nivel_med)
        if file_nivel_max:
            st.session_state['df_nivel_maximo_cached'] = ler_csv_rapido(file_nivel_max)
        if file_nivel_min:
            st.session_state['df_nivel_minimo_cached'] = ler_csv_rapido(file_nivel_min)

    # Atribui referências das variáveis
    df_bruto = st.session_state['df_bruto_cached']
    df_depara_bombas = st.session_state['df_depara_bombas_cached']
    df_capacidade_bombas = st.session_state['df_capacidade_bombas_cached']
    df_max_outorga = st.session_state['df_max_outorga_cached']
    df_depara_niveis = st.session_state['df_depara_niveis_cached']
    df_nivel_medio = st.session_state['df_nivel_medio_cached']
    df_nivel_maximo = st.session_state['df_nivel_maximo_cached']
    df_nivel_minimo = st.session_state['df_nivel_minimo_cached']

else:
    st.sidebar.info("💡 Modo de demonstração com dados sintéticos ativos.")
    amostras = gerar_dados_amostra_completos()
    df_bruto = amostras['df_bruto']
    df_depara_bombas = amostras['df_depara_bombas']
    df_capacidade_bombas = amostras['df_capacidade_bombas']
    df_max_outorga = amostras['df_max_outorga']
    df_depara_niveis = amostras['df_depara_niveis']
    df_nivel_medio = amostras['df_nivel_medio']
    df_nivel_maximo = amostras['df_nivel_maximo']
    df_nivel_minimo = amostras['df_nivel_minimo']


# =========================================================================
# SELEÇÃO DINÂMICA DE PERÍODO
# =========================================================================
st.sidebar.subheader("2. Período de Processamento")

modo_periodo = st.sidebar.selectbox(
    "Modo de Seleção de Datas:",
    ["Intervalo Livre (De / Até)", "Mês Específico", "Semestral (1º ou 2º Semestre)"]
)

hoje = date.today()
ano_atual = hoje.year

if modo_periodo == "Intervalo Livre (De / Até)":
    col_d1, col_d2 = st.sidebar.columns(2)
    with col_d1:
        data_ini_input = st.date_input("Data Inicial", value=date(ano_atual, 1, 1))
    with col_d2:
        data_fim_input = st.date_input("Data Final", value=date(ano_atual, 6, 30))
        
elif modo_periodo == "Mês Específico":
    ano_selec = st.sidebar.number_input("Ano", min_value=2020, max_value=2035, value=ano_atual)
    mes_selec = st.sidebar.selectbox(
        "Mês",
        range(1, 13),
        format_func=lambda x: f"{x:02d} - {['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'][x-1]}",
        index=5
    )
    data_ini_input = date(ano_selec, mes_selec, 1)
    ultimo_dia = pd.Period(f"{ano_selec}-{mes_selec:02d}").days_in_month
    data_fim_input = date(ano_selec, mes_selec, ultimo_dia)

else: # Semestral
    ano_selec = st.sidebar.number_input("Ano", min_value=2020, max_value=2035, value=ano_atual)
    semestre = st.sidebar.radio("Semestre:", ["1º Semestre (Jan a Jun)", "2º Semestre (Jul a Dez)"])
    if "1º" in semestre:
        data_ini_input = date(ano_selec, 1, 1)
        data_fim_input = date(ano_selec, 6, 30)
    else:
        data_ini_input = date(ano_selec, 7, 1)
        data_fim_input = date(ano_selec, 12, 31)

# Filtro de Elevatórias
elevatorias_disponiveis = []
if df_depara_bombas is not None and 'ELEVATORIA' in df_depara_bombas.columns:
    elevatorias_disponiveis = sorted(df_depara_bombas['ELEVATORIA'].astype(str).str.strip().unique().tolist())

elevatorias_filtro = st.sidebar.multiselect(
    "Filtrar Elevatórias (Opcional):",
    options=elevatorias_disponiveis,
    default=elevatorias_disponiveis if elevatorias_disponiveis else None
)

# Configurações adicionais
st.sidebar.subheader("3. Configurações Adicionais")
fuso_horario = st.sidebar.selectbox(
    "Fuso Horário:",
    ["Etc/GMT+4", "America/Sao_Paulo", "America/Manaus", "America/Cuiaba", "UTC"],
    index=0
)

resolucao_dpi = st.sidebar.select_slider(
    "Resolução dos Gráficos (DPI):",
    options=[150, 300, 600],
    value=300,
    help="300 DPI é ideal para relatórios e impressão de alta qualidade; 600 DPI para ultra-definição."
)

# Botão de Execução
btn_processar = st.sidebar.button("🚀 Processar Telemetria e Indicadores", type="primary", use_container_width=True)

if btn_processar:
    if df_bruto is None or df_depara_bombas is None:
        st.sidebar.error("⚠️ Por favor, envie a base de status de operação e o arquivo De-Para do Excel.")
    else:
        with st.spinner("⏳ Processando telemetria, calculando vazões e integrando níveis..."):
            try:
                # 1. Telemetria de bombas
                resumo_bombas = processar_telemetria_bombas(
                    df_bruto=df_bruto,
                    df_depara_bombas=df_depara_bombas,
                    data_inicio=data_ini_input,
                    data_fim=data_fim_input,
                    elevatorias_selecionadas=elevatorias_filtro
                )

                # 2. Vazões e Outorgas
                resumo_agregado, resumo_com_cap = calcular_vazoes_e_outorga(
                    resumo_bombas=resumo_bombas,
                    df_capacidade_bombas=df_capacidade_bombas if df_capacidade_bombas is not None else pd.DataFrame(),
                    df_max_outorga=df_max_outorga if df_max_outorga is not None else pd.DataFrame()
                )

                # 3. Níveis de Reservatórios
                if df_nivel_medio is not None and df_depara_niveis is not None:
                    df_niveis = processar_niveis(
                        df_nivel_medio_raw=df_nivel_medio,
                        df_nivel_maximo_raw=df_nivel_maximo if df_nivel_maximo is not None else pd.DataFrame(),
                        df_nivel_minimo_raw=df_nivel_minimo if df_nivel_minimo is not None else pd.DataFrame(),
                        df_depara_niveis=df_depara_niveis,
                        fuso_horario=fuso_horario
                    )
                else:
                    df_niveis = pd.DataFrame()

                # 4. Consolidação Geral Analítica
                df_geral_analitico = consolidar_dados_analiticos(resumo_agregado, df_niveis)
                auditoria_res = gerar_relatorio_auditoria(df_geral_analitico)

                # Salva no Session State
                st.session_state['df_geral_analitico'] = df_geral_analitico
                st.session_state['resumo_bombas'] = resumo_bombas
                st.session_state['resumo_agregado'] = resumo_agregado
                st.session_state['df_niveis'] = df_niveis
                st.session_state['auditoria_resultado'] = auditoria_res
                st.session_state['dados_carregados'] = True
                
                gc.collect()
                st.sidebar.success("🎉 Processamento concluído com sucesso!")
            except Exception as ex:
                st.sidebar.error(f"Erro durante a execução do pipeline: {ex}")
                st.exception(ex)


# =========================================================================
# CABEÇALHO PRINCIPAL DO APP
# =========================================================================
st.markdown('<div class="main-header">⚡ Sistema Integrado de Telemetria e Gestão de Elevatórias</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">Tratamento de telemetria minuto a minuto, balanço de vazão e outorga, '
    'monitoramento de níveis e geração de relatórios analíticos em alta resolução.</div>',
    unsafe_allow_html=True
)

# Se ainda não houver dados processados, exibe tela de boas-vindas
if not st.session_state['dados_carregados'] or st.session_state['df_geral_analitico'].empty:
    st.info(
        "👋 **Bem-vindo!** Para iniciar a análise:\n\n"
        "1. Selecione a origem dos dados na barra lateral à esquerda (arraste seus arquivos ou use a base de exemplo pronta).\n"
        "2. Defina o período desejado (mensal, semestral ou intervalo livre).\n"
        "3. Clique em **'🚀 Processar Telemetria e Indicadores'** para gerar os gráficos e tabelas analíticas."
    )
    st.stop()

# Recupera dados do Session State
df_geral = st.session_state['df_geral_analitico']
resumo_bba = st.session_state['resumo_bombas']
auditoria = st.session_state['auditoria_resultado']


# =========================================================================
# ABAS DE NAVEGAÇÃO PRINCIPAIS
# =========================================================================
tab_graficos, tab_tabela, tab_auditoria, tab_exportacao = st.tabs([
    "📊 Dashboard & Gráficos",
    "📝 Tabela Analítica & Edição",
    "🚨 Auditoria de Outorga",
    "📦 Central de Exportação & Pacotes ZIP"
])


# =========================================================================
# ABA 1: DASHBOARD & GRÁFICOS INTERATIVOS
# =========================================================================
with tab_graficos:
    st.subheader("Visualização dos Indicadores e Gráficos por Elevatória")

    col_filtro1, col_filtro2 = st.columns([2, 2])
    
    with col_filtro1:
        elevatorias_unicas = sorted(df_geral['ELEVATORIA'].unique().tolist())
        elev_selecionada = st.selectbox("Selecione a Elevatória:", elevatorias_unicas, key="sb_elev_graf")
    
    with col_filtro2:
        meses_disponiveis = sorted(df_geral[df_geral['ELEVATORIA'] == elev_selecionada]['ANO_MES'].unique().tolist())
        mes_selecionado = st.selectbox("Selecione o Mês / Período:", meses_disponiveis, key="sb_mes_graf")

    # Filtragem para o gráfico
    df_filtrado_elev = df_geral[
        (df_geral['ELEVATORIA'] == elev_selecionada) &
        (df_geral['ANO_MES'] == mes_selecionado)
    ].sort_values(by='DATA').copy()

    if df_filtrado_elev.empty:
        st.warning("Nenhum dado encontrado para os filtros selecionados.")
    else:
        # Métricas Rápidas (KPIs)
        kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
        
        tot_horas = df_filtrado_elev['HORAS_LIGADO'].sum()
        tot_vol = df_filtrado_elev['M3_DIA'].sum()
        media_vazao = df_filtrado_elev['Q_MEDIA'].mean()
        max_vazao = df_filtrado_elev['Q_MAX'].max()
        outorga_val = df_filtrado_elev['Q_MAX_OUTORGA'].iloc[0] if 'Q_MAX_OUTORGA' in df_filtrado_elev.columns else 0.0

        kpi1.metric("⏱️ Horas Totais", f"{tot_horas:.1f} h")
        kpi2.metric("💧 Volume Total", f"{tot_vol:,.0f} m³".replace(',', '.'))
        kpi3.metric("🌊 Vazão Média", f"{media_vazao:.2f} m³/h")
        kpi4.metric("🚀 Pico de Vazão", f"{max_vazao:.2f} m³/h")
        kpi5.metric("📋 Limite Outorga", f"{outorga_val:.2f} m³/h")

        st.divider()

        titulo_periodo = f"{df_filtrado_elev['MES_NOME'].iloc[0]}/{df_filtrado_elev['ANO'].iloc[0]}"

        # --- Gráfico 1: Horas Totais Diárias ---
        st.markdown("#### 1. Horas Totais de Operação Útil por Dia")
        fig1 = gerar_grafico_horas_totais_diario(df_filtrado_elev, elev_selecionada, titulo_periodo)
        st.pyplot(fig1, use_container_width=True)
        img1_bytes = figura_para_bytes_png(fig1, dpi=resolucao_dpi)
        st.download_button(
            label="⬇️ Baixar Gráfico de Horas Totais (PNG Alta Resolução)",
            data=img1_bytes,
            file_name=f"{elev_selecionada}_horas_totais_{mes_selecionado}.png",
            mime="image/png",
            key="dl_fig1"
        )
        plt.close(fig1)

        st.divider()

        # --- Gráfico 2: Horas Individuais por Bomba ---
        st.markdown("#### 2. Tempo de Operação Individual de Cada Bomba (horas)")
        df_bombas_filtrado = resumo_bba[
            (resumo_bba['ELEVATORIA'].str.upper() == elev_selecionada.upper()) &
            (resumo_bba['DATA'].isin(df_filtrado_elev['DATA']))
        ]
        if not df_bombas_filtrado.empty:
            fig2 = gerar_grafico_horas_individuais_bombas(df_bombas_filtrado, elev_selecionada, titulo_periodo)
            st.pyplot(fig2, use_container_width=True)
            img2_bytes = figura_para_bytes_png(fig2, dpi=resolucao_dpi)
            st.download_button(
                label="⬇️ Baixar Gráfico de Bombas Individuais (PNG Alta Resolução)",
                data=img2_bytes,
                file_name=f"{elev_selecionada}_horas_individuais_{mes_selecionado}.png",
                mime="image/png",
                key="dl_fig2"
            )
            plt.close(fig2)
        else:
            st.info("ℹ️ Dados individuais de bombas não disponíveis para esta elevatória.")

        st.divider()

        # --- Gráfico 3: Níveis de Reservatório ---
        st.markdown("#### 3. Níveis de Reservatório (% Médio, Máximo e Mínimo)")
        fig3 = gerar_grafico_niveis(df_filtrado_elev, elev_selecionada, titulo_periodo)
        st.pyplot(fig3, use_container_width=True)
        img3_bytes = figura_para_bytes_png(fig3, dpi=resolucao_dpi)
        st.download_button(
            label="⬇️ Baixar Gráfico de Níveis (PNG Alta Resolução)",
            data=img3_bytes,
            file_name=f"{elev_selecionada}_niveis_{mes_selecionado}.png",
            mime="image/png",
            key="dl_fig3"
        )
        plt.close(fig3)

        st.divider()

        # --- Gráfico 4: Vazão e Outorga ---
        st.markdown("#### 4. Curvas de Vazão e Enquadramento de Outorga (m³/h)")
        fig4 = gerar_grafico_vazao(df_filtrado_elev, elev_selecionada, titulo_periodo)
        st.pyplot(fig4, use_container_width=True)
        img4_bytes = figura_para_bytes_png(fig4, dpi=resolucao_dpi)
        st.download_button(
            label="⬇️ Baixar Gráfico de Vazão e Outorga (PNG Alta Resolução)",
            data=img4_bytes,
            file_name=f"{elev_selecionada}_vazao_{mes_selecionado}.png",
            mime="image/png",
            key="dl_fig4"
        )
        plt.close(fig4)


# =========================================================================
# ABA 2: TABELA ANALÍTICA & EDIÇÃO INTERATIVA DE DADOS
# =========================================================================
with tab_tabela:
    st.subheader("Consulta e Edição de Dados Tratados")
    st.markdown(
        "Você pode visualizar, ordenar, filtrar e até **editar diretamente as células** da tabela abaixo antes de exportar. "
        "Qualquer alteração feita será refletida nos downloads."
    )

    tipo_tabela = st.radio(
        "Selecione a visualização de dados:",
        ["Base Geral Analítica (Consolidada)", "Detalhamento por Bomba (Horas de Operação)", "Auditoria de Outorga"],
        horizontal=True
    )

    if tipo_tabela == "Base Geral Analítica (Consolidada)":
        df_para_editar = df_geral.copy()
        
        # Filtros rápidos
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            filtro_elev = st.multiselect("Filtrar Elevatórias:", sorted(df_para_editar['ELEVATORIA'].unique().tolist()))
        with col_f2:
            filtro_mes = st.multiselect("Filtrar Meses:", sorted(df_para_editar['ANO_MES'].unique().tolist()))

        if filtro_elev:
            df_para_editar = df_para_editar[df_para_editar['ELEVATORIA'].isin(filtro_elev)]
        if filtro_mes:
            df_para_editar = df_para_editar[df_para_editar['ANO_MES'].isin(filtro_mes)]

        df_editado = st.data_editor(
            df_para_editar,
            use_container_width=True,
            num_rows="dynamic",
            key="editor_geral"
        )

        col_b1, col_b2 = st.columns([1, 4])
        with col_b1:
            excel_bytes = gerar_excel_simples_bytes(df_editado, nome_aba="BASE_ANALITICA")
            st.download_button(
                label="📥 Baixar em Excel (.xlsx)",
                data=excel_bytes,
                file_name="tabela_analitica_editada.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    elif tipo_tabela == "Detalhamento por Bomba (Horas de Operação)":
        st.dataframe(resumo_bba, use_container_width=True)
        excel_bombas_bytes = gerar_excel_simples_bytes(resumo_bba, nome_aba="DETALHE_BOMBAS")
        st.download_button(
            label="📥 Baixar Detalhe de Bombas (.xlsx)",
            data=excel_bombas_bytes,
            file_name="detalhe_bombas_operacao.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    else:
        st.dataframe(auditoria['df_estouros_por_elevatoria'], use_container_width=True)


# =========================================================================
# ABA 3: AUDITORIA DE OUTORGA & CONFORMIDADE
# =========================================================================
with tab_auditoria:
    st.subheader("Auditoria de Conformidade Operacional e Limites de Outorga")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📋 Total de Registros Diários", f"{auditoria['total_registros']:,}".replace(',', '.'))
    c2.metric("✅ Em Conformidade", f"{auditoria['total_conformidade']:,}".replace(',', '.'))
    c3.metric("⚠️ Dias com Excesso", f"{auditoria['total_estouros']:,}".replace(',', '.'))
    c4.metric("📈 Taxa de Conformidade", f"{auditoria['percentual_conformidade']:.1f}%")

    st.divider()

    st.markdown("#### Detalhamento de Ocorrências por Elevatória")
    if not auditoria['df_estouros_por_elevatoria'].empty:
        st.dataframe(auditoria['df_estouros_por_elevatoria'], use_container_width=True)
    else:
        st.success("🎉 Nenhuma elevatória apresentou volume acima do limite de outorga mapeado no período!")

    st.divider()

    st.markdown("#### 🚨 Top 10 Maiores Excessos Detectados")
    if not auditoria['df_top_excessos'].empty:
        st.dataframe(auditoria['df_top_excessos'], use_container_width=True)
    else:
        st.info("Nenhum registro com excesso de vazão detectado.")


# =========================================================================
# ABA 4: CENTRAL DE EXPORTAÇÃO & PACOTES ZIP
# =========================================================================
with tab_exportacao:
    st.subheader("Geração e Download de Pacotes Estruturados")
    st.markdown(
        "Aqui você pode baixar tanto a **base analítica consolidada única** quanto o **pacote ZIP completo** "
        "organizado com uma pasta para cada elevatória e subpastas para cada mês contendo a planilha analítica e todos os gráficos em alta resolução."
    )

    col_exp1, col_exp2 = st.columns(2)

    with col_exp1:
        st.markdown("### 📄 1. Planilha Única Consolidada")
        st.write("Gera o arquivo `base_consolidada_elevatorias.xlsx` com todas as abas consolidadas.")
        
        excel_consolidado_bytes = gerar_excel_consolidado(df_geral, resumo_bba)
        st.download_button(
            label="📥 Baixar Base Consolidada Global (Excel)",
            data=excel_consolidado_bytes,
            file_name="base_consolidada_elevatorias.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="secondary",
            use_container_width=True
        )

    with col_exp2:
        st.markdown("### 🗂️ 2. Pacote Completo Estruturado (ZIP)")
        st.write("Cria a estrutura de pastas organizada por Elevatória e Mês com todos os relatórios e imagens PNG (300 DPI).")

        btn_gerar_zip = st.button("📦 Gerar e Empacotar Pacote ZIP", type="primary", use_container_width=True)
        
        if btn_gerar_zip:
            prog_bar = st.progress(0.0)
            status_text = st.empty()

            def atualizar_progresso(prog, msg):
                prog_bar.progress(min(prog, 1.0))
                status_text.text(msg)

            with st.spinner("Empacotando planilhas e renderizando gráficos em alta definição..."):
                zip_dados = gerar_pacote_zip_completo(
                    df_geral_analitico=df_geral,
                    resumo_bombas=resumo_bba,
                    dpi=resolucao_dpi,
                    callback_progresso=atualizar_progresso
                )
                atualizar_progresso(1.0, "Pacote gerado com sucesso!")
                
                nome_zip = f"pacote_elevatorias_{date.today().strftime('%Y%m%d')}.zip"
                st.download_button(
                    label="⬇️ Baixar Pacote ZIP Completo",
                    data=zip_dados,
                    file_name=nome_zip,
                    mime="application/zip",
                    use_container_width=True
                )
