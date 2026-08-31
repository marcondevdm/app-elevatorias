"""
Módulo de Empacotamento e Exportação de Arquivos.
Gera planilhas Excel formatadas e constrói o pacote ZIP completo estruturado
por elevatória e por mês com tabelas analíticas e gráficos em alta resolução.
"""

import os
import sys
import io
import zipfile
import pandas as pd
import matplotlib.pyplot as plt

# Garante path para importação na nuvem
DIRETORIO_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DIRETORIO_RAIZ not in sys.path:
    sys.path.insert(0, DIRETORIO_RAIZ)

from visualization.charts import (
    gerar_grafico_horas_totais_diario,
    gerar_grafico_horas_individuais_bombas,
    gerar_grafico_niveis,
    gerar_grafico_vazao,
    figura_para_bytes_png
)
from pipeline.consolidator import gerar_relatorio_auditoria

def gerar_excel_simples_bytes(df: pd.DataFrame, nome_aba: str = 'DADOS') -> bytes:
    """Converte um único DataFrame em um arquivo Excel (.xlsx) em bytes."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name=nome_aba[:31], index=False)
    output.seek(0)
    return output.getvalue()

def gerar_excel_consolidado(
    df_geral_analitico: pd.DataFrame,
    resumo_bombas: pd.DataFrame | None = None
) -> bytes:
    """Gera o arquivo Excel completo consolidado (base_consolidada_elevatorias.xlsx)."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_geral_analitico.to_excel(writer, sheet_name='BASE_CONSOLIDADA', index=False)
        
        if resumo_bombas is not None and not resumo_bombas.empty:
            resumo_bombas.to_excel(writer, sheet_name='DETALHE_BOMBAS', index=False)
            
        auditoria = gerar_relatorio_auditoria(df_geral_analitico)
        df_aud = auditoria['df_estouros_por_elevatoria']
        if not df_aud.empty:
            df_aud.to_excel(writer, sheet_name='AUDITORIA_ESTOUROS', index=False)
        if not auditoria['df_top_excessos'].empty:
            auditoria['df_top_excessos'].to_excel(writer, sheet_name='TOP_EXCESSOS', index=False)

    output.seek(0)
    return output.getvalue()


def gerar_pacote_zip_completo(
    df_geral_analitico: pd.DataFrame,
    resumo_bombas: pd.DataFrame | None = None,
    dpi: int = 300,
    callback_progresso = None
) -> bytes:
    """Gera um pacote .ZIP contendo toda a estrutura de diretórios organizada por elevatória e mês."""
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # 1. Base consolidada global
        excel_consolidado_bytes = gerar_excel_consolidado(df_geral_analitico, resumo_bombas)
        zip_file.writestr('base_consolidada_elevatorias.xlsx', excel_consolidado_bytes)

        # 2. Relatório de auditoria
        auditoria = gerar_relatorio_auditoria(df_geral_analitico)
        aud_buf = io.BytesIO()
        with pd.ExcelWriter(aud_buf, engine='openpyxl') as writer:
            if not auditoria['df_estouros_por_elevatoria'].empty:
                auditoria['df_estouros_por_elevatoria'].to_excel(writer, sheet_name='RESUMO_ELEVATORIAS', index=False)
            if not auditoria['df_top_excessos'].empty:
                auditoria['df_top_excessos'].to_excel(writer, sheet_name='TOP_EXCESSOS', index=False)
        aud_buf.seek(0)
        zip_file.writestr('relatorio_auditoria_outorga.xlsx', aud_buf.getvalue())

        # 3. Pastas por Elevatória e Mês
        grupos = df_geral_analitico.groupby(['ELEVATORIA', 'ANO_MES'])
        total_grupos = len(grupos)
        idx_atual = 0

        for (elevatoria, ano_mes), df_grupo in grupos:
            idx_atual += 1
            if callback_progresso:
                callback_progresso(idx_atual / total_grupos, f"Gerando pacote: {elevatoria} - {ano_mes}")

            elev_pasta = str(elevatoria).replace('/', '_').replace('\\', '_').strip()
            mes_pasta = str(ano_mes).replace('/', '_').strip()
            
            caminho_base = f"Elevatorias/{elev_pasta}/{mes_pasta}"

            primeira_data = df_grupo['DATA'].iloc[0]
            mes_ano_arquivo = primeira_data.strftime('%m_%Y')
            titulo_periodo = f"{df_grupo['MES_NOME'].iloc[0]}/{df_grupo['ANO'].iloc[0]}"

            # A. Planilha Analítica Mensal
            df_grupo_clean = df_grupo.drop(columns=['ANO_MES', 'DATA_FORMATADA', 'MES_NUM', 'MES_NOME', 'ANO'], errors='ignore')
            excel_mensal_bytes = gerar_excel_simples_bytes(df_grupo_clean, nome_aba='TABELA_ANALITICA')
            nome_arq_excel = f"tabela_analitica_{elev_pasta}_{mes_ano_arquivo}.xlsx"
            zip_file.writestr(f"{caminho_base}/{nome_arq_excel}", excel_mensal_bytes)

            # B. Gráfico 1: Horas Totais
            fig1 = gerar_grafico_horas_totais_diario(df_grupo, elev_pasta, titulo_periodo)
            img1 = figura_para_bytes_png(fig1, dpi=dpi)
            plt.close(fig1)
            zip_file.writestr(f"{caminho_base}/01_horas_totais_{elev_pasta}_{mes_ano_arquivo}.png", img1)

            # C. Gráfico 2: Horas Individuais das Bombas
            if resumo_bombas is not None and not resumo_bombas.empty:
                df_bombas_grupo = resumo_bombas[
                    (resumo_bombas['ELEVATORIA'].str.upper() == str(elevatoria).upper()) &
                    (resumo_bombas['DATA'].isin(df_grupo['DATA']))
                ]
                if not df_bombas_grupo.empty:
                    fig2 = gerar_grafico_horas_individuais_bombas(df_bombas_grupo, elev_pasta, titulo_periodo)
                    img2 = figura_para_bytes_png(fig2, dpi=dpi)
                    plt.close(fig2)
                    zip_file.writestr(f"{caminho_base}/02_horas_individuais_bombas_{elev_pasta}_{mes_ano_arquivo}.png", img2)

            # D. Gráfico 3: Níveis de Reservatório
            fig3 = gerar_grafico_niveis(df_grupo, elev_pasta, titulo_periodo)
            img3 = figura_para_bytes_png(fig3, dpi=dpi)
            plt.close(fig3)
            zip_file.writestr(f"{caminho_base}/03_niveis_reservatorio_{elev_pasta}_{mes_ano_arquivo}.png", img3)

            # E. Gráfico 4: Vazão e Outorga
            fig4 = gerar_grafico_vazao(df_grupo, elev_pasta, titulo_periodo)
            img4 = figura_para_bytes_png(fig4, dpi=dpi)
            plt.close(fig4)
            zip_file.writestr(f"{caminho_base}/04_vazao_e_outorga_{elev_pasta}_{mes_ano_arquivo}.png", img4)

    zip_buffer.seek(0)
    return zip_buffer.getvalue()
