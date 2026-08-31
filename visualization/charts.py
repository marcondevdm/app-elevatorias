"""
Módulo de Geração de Gráficos em Alta Resolução (Matplotlib).
Implementa os 4 tipos de gráficos padronizados com tema escuro (#303030), fontes legíveis,
limites dinâmicos de eixos, offsets adaptativos para evitar sobreposição de rótulos e exportação em PNG.
"""

import io
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np

# Constantes globais de estilo
COR_FUNDO = '#303030'
COR_TEXTO = 'white'
COR_GRID = 'gray'
COR_BARRA_TOTAL = '#1772B1'

CORES_BOMBA = {
    'BBA-01': '#1772B1',
    'BBA-02': '#FFFFFF',
    'BBA-03': '#E57C04',
    'BBA-04': '#3EB489',
    'BOMBA 01': '#1772B1',
    'BOMBA 02': '#FFFFFF',
    'BOMBA 03': '#E57C04',
    'BOMBA 04': '#3EB489'
}
ORDEM_BOMBAS_PADRAO = ['BBA-01', 'BBA-02', 'BBA-03', 'BBA-04']

def _aplicar_estilo_seguro():
    """Aplica o estilo de plot de forma segura com fallbacks."""
    try:
        plt.style.use('seaborn-v0_8-whitegrid')
    except Exception:
        try:
            plt.style.use('seaborn-whitegrid')
        except Exception:
            plt.style.use('default')

def figura_para_bytes_png(fig: plt.Figure, dpi: int = 300) -> bytes:
    """Converte uma figura Matplotlib para bytes PNG em alta resolução."""
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight', facecolor=fig.get_facecolor())
    buf.seek(0)
    img_bytes = buf.getvalue()
    buf.close()
    return img_bytes

def _configurar_estilo_base(ax: plt.Axes, titulo: str, x_label: str, y_label: str):
    """Configura o estilo escuro padrão dos eixos."""
    ax.set_facecolor(COR_FUNDO)
    ax.set_title(titulo, color=COR_TEXTO, fontsize=16, pad=15, fontweight='bold')
    ax.set_xlabel(x_label, color=COR_TEXTO, fontsize=13, labelpad=10)
    ax.set_ylabel(y_label, color=COR_TEXTO, fontsize=13, labelpad=10)
    ax.tick_params(axis='x', colors=COR_TEXTO, labelsize=11)
    ax.tick_params(axis='y', colors=COR_TEXTO, labelsize=11)
    ax.grid(axis='y', linestyle='--', alpha=0.4, color=COR_GRID)
    ax.grid(axis='x', linestyle=':', alpha=0.2, color=COR_GRID)
    for spine in ax.spines.values():
        spine.set_color(COR_TEXTO)


# =========================================================================
# 1. GRÁFICO DE HORAS TOTAIS DIÁRIAS (BARRAS)
# =========================================================================
def gerar_grafico_horas_totais_diario(
    df_elev: pd.DataFrame,
    elevatoria: str,
    titulo_periodo: str = ""
) -> plt.Figure:
    """Gera o gráfico de barras das horas totais de operação útil diária."""
    _aplicar_estilo_seguro()
    fig, ax = plt.subplots(figsize=(16, 8))
    fig.patch.set_facecolor(COR_FUNDO)

    df_plot = df_elev.sort_values(by='DATA').copy()
    if 'DATA_FORMATADA' not in df_plot.columns:
        df_plot['DATA_FORMATADA'] = pd.to_datetime(df_plot['DATA']).dt.strftime('%d/%m')

    horas_serie = df_plot['HORAS_LIGADO'].round().astype(int)

    barras = ax.bar(
        df_plot['DATA_FORMATADA'],
        horas_serie,
        color=COR_BARRA_TOTAL,
        width=0.75,
        zorder=2
    )

    for bar in barras:
        yval = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            yval + 0.35,
            f"{int(yval)}h",
            ha='center',
            va='bottom',
            fontsize=10,
            color=COR_TEXTO,
            fontweight='bold',
            zorder=3
        )

    max_y = horas_serie.max() if not horas_serie.empty else 0
    y_lim_max = int(np.ceil(max(26.0, max_y * 1.15)))
    ax.set_ylim(0, y_lim_max)

    titulo = f"Horas Totais de Operação Útil por Dia - {elevatoria}"
    if titulo_periodo:
        titulo += f" ({titulo_periodo})"

    _configurar_estilo_base(ax, titulo, "Dia", "Total de Horas de Operação Útil")
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    return fig


# =========================================================================
# 2. GRÁFICO DE HORAS INDIVIDUAIS POR BOMBA (SUBPLOTS VERTICAIS)
# =========================================================================
def gerar_grafico_horas_individuais_bombas(
    df_elev_bombas: pd.DataFrame,
    elevatoria: str,
    titulo_periodo: str = ""
) -> plt.Figure:
    """Gera subplots verticais com a série diária de cada bomba da elevatória."""
    _aplicar_estilo_seguro()
    
    bombas_unicas = df_elev_bombas['BOMBA'].unique()
    ordem_bombas = [eq for eq in ORDEM_BOMBAS_PADRAO if eq in bombas_unicas]
    outras_bombas = [eq for eq in bombas_unicas if eq not in ORDEM_BOMBAS_PADRAO]
    ordem_bombas.extend(sorted(outras_bombas))

    num_bombas = max(1, len(ordem_bombas))
    fig_height = max(10, num_bombas * 4.5)
    
    fig, axes = plt.subplots(
        nrows=num_bombas,
        ncols=1,
        figsize=(16, fig_height),
        sharex=True
    )
    fig.patch.set_facecolor(COR_FUNDO)

    if num_bombas == 1:
        axes = [axes]

    for i, eq in enumerate(ordem_bombas):
        ax = axes[i]
        ax.set_facecolor(COR_FUNDO)

        dados = df_elev_bombas[df_elev_bombas['BOMBA'] == eq].sort_values('DATA').copy()
        if 'DATA_FORMATADA' not in dados.columns:
            dados['DATA_FORMATADA'] = pd.to_datetime(dados['DATA']).dt.strftime('%d/%m')

        cor = CORES_BOMBA.get(eq, '#AAAAAA')

        ax.plot(
            dados['DATA_FORMATADA'],
            dados['HORAS_LIGADO'],
            label=f"Bomba {eq}",
            marker='o',
            color=cor,
            linewidth=2,
            zorder=2
        )

        for _, row in dados.iterrows():
            val = row['HORAS_LIGADO']
            if not pd.isna(val) and np.isfinite(val):
                ax.text(
                    row['DATA_FORMATADA'],
                    val + 0.45,
                    f"{val:.2f}",
                    ha='center',
                    va='bottom',
                    fontsize=8.5,
                    color=COR_TEXTO,
                    zorder=3
                )

        ax.set_title(f'Bomba {eq}', fontsize=14, color=COR_TEXTO, pad=8)
        ax.set_ylabel('Horas', fontsize=12, color=COR_TEXTO)
        ax.grid(axis='y', linestyle='--', alpha=0.4, color=COR_GRID)
        ax.grid(axis='x', linestyle=':', alpha=0.2, color=COR_GRID)
        ax.tick_params(axis='both', colors=COR_TEXTO)
        for spine in ax.spines.values():
            spine.set_color(COR_TEXTO)

        y_max = dados['HORAS_LIGADO'].max() if not dados.empty else 0
        ax.set_ylim(bottom=0, top=max(25.5, y_max + 3.0))

        leg = ax.legend(fontsize=9, facecolor=COR_FUNDO, edgecolor=COR_TEXTO, loc='upper right')
        for text in leg.get_texts():
            text.set_color(COR_TEXTO)

    plt.xticks(rotation=45, ha='right', color=COR_TEXTO, fontsize=10)
    plt.xlabel('Data', fontsize=12, color=COR_TEXTO)

    titulo_principal = f'Tempo de Operação de Cada Bomba (horas) - {elevatoria}'
    if titulo_periodo:
        titulo_principal += f" - {titulo_periodo}"
    fig.suptitle(titulo_principal, fontsize=18, color=COR_TEXTO, y=0.99, fontweight='bold')

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    return fig


# =========================================================================
# 3. GRÁFICO DE NÍVEIS PERCENTUAIS (% MÉDIO, MÁXIMO, MÍNIMO)
# =========================================================================
def gerar_grafico_niveis(
    df_elev: pd.DataFrame,
    elevatoria: str,
    titulo_periodo: str = ""
) -> plt.Figure:
    """Gera o gráfico de linhas dos níveis do reservatório (% Médio, Máximo e Mínimo)."""
    _aplicar_estilo_seguro()
    fig, ax = plt.subplots(figsize=(16, 8))
    fig.patch.set_facecolor(COR_FUNDO)

    df_plot = df_elev.sort_values(by='DATA').copy()
    if 'DATA_FORMATADA' not in df_plot.columns:
        df_plot['DATA_FORMATADA'] = pd.to_datetime(df_plot['DATA']).dt.strftime('%d/%m')

    ax.plot(df_plot['DATA_FORMATADA'], df_plot['NIVEL_MEDIO'],
            label='Nível Médio (%)', marker='o', color='#FF8010', linewidth=2, zorder=2)
    ax.plot(df_plot['DATA_FORMATADA'], df_plot['NIVEL_MAXIMO'],
            label='Nível Máximo (%)', marker='o', color='#1772B1', linewidth=2, zorder=2)
    ax.plot(df_plot['DATA_FORMATADA'], df_plot['NIVEL_MINIMO'],
            label='Nível Mínimo (%)', marker='o', color='#209B20', linewidth=2, zorder=2)

    offset = 1.0
    for _, row in df_plot.iterrows():
        dt = row['DATA_FORMATADA']
        ax.text(dt, row['NIVEL_MEDIO'] + offset, f"{row['NIVEL_MEDIO']:.1f}",
                ha='center', va='bottom', fontsize=8.5, color='white', zorder=3)
        ax.text(dt, row['NIVEL_MAXIMO'] + offset, f"{row['NIVEL_MAXIMO']:.1f}",
                ha='center', va='bottom', fontsize=8.5, color='white', zorder=3)
        ax.text(dt, row['NIVEL_MINIMO'] + offset, f"{row['NIVEL_MINIMO']:.1f}",
                ha='center', va='bottom', fontsize=8.5, color='white', zorder=3)

    titulo = f"Nível de Reservatório (%) - {elevatoria}"
    if titulo_periodo:
        titulo += f" - {titulo_periodo}"

    _configurar_estilo_base(ax, titulo, "Data", "Nível (%)")
    ax.set_ylim(0, 115)
    plt.xticks(rotation=90)

    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.15), ncol=3,
              fontsize=10, frameon=False, facecolor=COR_FUNDO, labelcolor='white')

    plt.tight_layout()
    return fig


# =========================================================================
# 4. GRÁFICO DE VAZÃO (Q_MIN, Q_MAX, Q_MEDIA E LIMITE DE OUTORGA)
# =========================================================================
def gerar_grafico_vazao(
    df_elev: pd.DataFrame,
    elevatoria: str,
    titulo_periodo: str = ""
) -> plt.Figure:
    """Gera o gráfico de vazões com linha de outorga, zoom adaptativo e offsets sem sobreposição."""
    _aplicar_estilo_seguro()
    fig, ax = plt.subplots(figsize=(16, 8))
    fig.patch.set_facecolor(COR_FUNDO)

    df_plot = df_elev.sort_values(by='DATA').copy()
    if 'DATA_FORMATADA' not in df_plot.columns:
        df_plot['DATA_FORMATADA'] = pd.to_datetime(df_plot['DATA']).dt.strftime('%d/%m')

    linha_limite = float(df_plot['Q_MAX_OUTORGA'].iloc[0]) if not df_plot.empty and 'Q_MAX_OUTORGA' in df_plot.columns else 0.0

    all_q_values = pd.concat([df_plot['Q_MIN'], df_plot['Q_MAX'], df_plot['Q_MEDIA']])
    q_min_data = float(all_q_values.min()) if not all_q_values.empty else 0.0
    q_max_data = float(all_q_values.max()) if not all_q_values.empty else 10.0

    pico_maximo = max(q_max_data, linha_limite)
    y_margin_top = max(0.5, pico_maximo * 0.12)
    y_margin_bottom = max(0.5, (q_max_data - q_min_data) * 0.15)

    y_min_limite = max(0.0, q_min_data - y_margin_bottom)
    
    if (linha_limite > 10) and (linha_limite / (q_max_data + 1e-6) > 10):
        y_max_limite = q_max_data + y_margin_top
    else:
        y_max_limite = pico_maximo + y_margin_top

    ax.plot(df_plot['DATA_FORMATADA'], df_plot['Q_MIN'],
            label='Vazão Mínima', marker='o', color='#FF8010', linewidth=2, zorder=2)
    ax.plot(df_plot['DATA_FORMATADA'], df_plot['Q_MAX'],
            label='Vazão Máxima', marker='o', color='#1772B1', linewidth=2, zorder=2)
    ax.plot(df_plot['DATA_FORMATADA'], df_plot['Q_MEDIA'],
            label='Vazão Média', marker='o', color='#209B20', linewidth=2, zorder=2)

    if linha_limite > 0:
        ax.axhline(
            y=linha_limite,
            color='red',
            linestyle='--',
            linewidth=2,
            label=f'Vazão Máx. Outorga ({linha_limite:.2f} m³/h)',
            zorder=1
        )

    range_para_offset = max(y_max_limite - y_min_limite, 5.0)
    offset_base = range_para_offset * 0.018
    multiplicadores = [-1.6, 0.5, 2.6]

    for _, row in df_plot.iterrows():
        dt = row['DATA_FORMATADA']
        vazoes = [
            (row['Q_MIN'], 'Q_MIN'),
            (row['Q_MEDIA'], 'Q_MEDIA'),
            (row['Q_MAX'], 'Q_MAX')
        ]
        vazoes_ord = sorted(vazoes, key=lambda x: x[0])

        for valor, col_nome in vazoes:
            pos = next(j for j, (v, c) in enumerate(vazoes_ord) if v == valor and c == col_nome)
            offset_final = offset_base * multiplicadores[pos]

            ax.text(
                dt,
                valor + offset_final,
                f"{valor:.2f}",
                ha='center',
                va='bottom',
                fontsize=8.5,
                color='white',
                zorder=3
            )

    titulo = f"Vazão (m³/h) - {elevatoria}"
    if titulo_periodo:
        titulo += f" - {titulo_periodo}"

    _configurar_estilo_base(ax, titulo, "Data", "Vazão (m³/h)")
    ax.set_ylim(y_min_limite, y_max_limite)
    plt.xticks(rotation=90)

    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.15), ncol=4,
              fontsize=10, facecolor=COR_FUNDO, edgecolor='white', labelcolor='white')

    plt.tight_layout()
    return fig
