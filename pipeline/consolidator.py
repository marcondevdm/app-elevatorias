"""
Módulo de Consolidação Analítica e Auditoria.
Une a agregação de vazão/outorga com os níveis de reservatórios gerando a base geral analítica (df_geral_analitico)
e produz relatórios de diagnóstico e conformidade operacional.
"""

import pandas as pd
import numpy as np

MAPA_MESES_PT = {
    1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
    5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
    9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
}

def consolidar_dados_analiticos(
    resumo_agregado: pd.DataFrame,
    df_niveis: pd.DataFrame
) -> pd.DataFrame:
    """
    Consolida as bases de vazão/operação e níveis em um único DataFrame analítico.
    
    Args:
        resumo_agregado: DataFrame diário com HORAS_LIGADO, M3_DIA, Q_MEDIA, Q_MIN, Q_MAX, Q_MAX_OUTORGA.
        df_niveis: DataFrame diário com NIVEL_MEDIO, NIVEL_MAXIMO, NIVEL_MINIMO (em %).
        
    Returns:
        pd.DataFrame analítico consolidado e formatado.
    """
    if resumo_agregado.empty:
        return pd.DataFrame()

    resumo = resumo_agregado.copy()
    resumo['DATA'] = pd.to_datetime(resumo['DATA']).dt.normalize()
    resumo['ELEVATORIA'] = resumo['ELEVATORIA'].astype(str).str.strip().str.upper()

    if not df_niveis.empty:
        niveis = df_niveis.copy()
        niveis['DATA'] = pd.to_datetime(niveis['DATA']).dt.normalize()
        niveis['ELEVATORIA'] = niveis['ELEVATORIA'].astype(str).str.strip().str.upper()
        
        df_merged = pd.merge(
            resumo,
            niveis[['ELEVATORIA', 'DATA', 'NIVEL_MEDIO', 'NIVEL_MAXIMO', 'NIVEL_MINIMO']],
            on=['ELEVATORIA', 'DATA'],
            how='left'
        )
    else:
        df_merged = resumo.copy()
        df_merged['NIVEL_MEDIO'] = 0.0
        df_merged['NIVEL_MAXIMO'] = 0.0
        df_merged['NIVEL_MINIMO'] = 0.0

    # Preenche eventuais nulos de níveis
    df_merged[['NIVEL_MEDIO', 'NIVEL_MAXIMO', 'NIVEL_MINIMO']] = (
        df_merged[['NIVEL_MEDIO', 'NIVEL_MAXIMO', 'NIVEL_MINIMO']].fillna(0.0)
    )

    # Colunas de apoio de data
    df_merged['ANO_MES'] = df_merged['DATA'].dt.to_period('M').astype(str)
    df_merged['DATA_FORMATADA'] = df_merged['DATA'].dt.strftime('%d/%m')
    df_merged['MES_NUM'] = df_merged['DATA'].dt.month
    df_merged['MES_NOME'] = df_merged['MES_NUM'].map(MAPA_MESES_PT)
    df_merged['ANO'] = df_merged['DATA'].dt.year

    # Ordenação final
    df_merged.sort_values(by=['ELEVATORIA', 'DATA'], inplace=True)
    df_merged.reset_index(drop=True, inplace=True)

    return df_merged


def gerar_relatorio_auditoria(df_geral_analitico: pd.DataFrame) -> dict:
    """
    Gera métricas e tabelas de diagnóstico de conformidade com a outorga.
    
    Returns:
        dict contendo estatísticas gerais e DataFrame de detalhamento por elevatória.
    """
    if df_geral_analitico.empty:
        return {
            'total_registros': 0,
            'total_conformidade': 0,
            'total_estouros': 0,
            'percentual_conformidade': 100.0,
            'df_estouros_por_elevatoria': pd.DataFrame(),
            'df_top_excessos': pd.DataFrame()
        }

    df = df_geral_analitico.copy()
    
    # Identifica estouros reais onde Q_MAX > Q_MAX_OUTORGA e outorga > 0
    mascara_estouro = (df['Q_MAX'] > df['Q_MAX_OUTORGA']) & (df['Q_MAX_OUTORGA'] > 0)
    
    total_registros = len(df)
    total_estouros = int(mascara_estouro.sum())
    total_conformidade = total_registros - total_estouros
    perc_conformidade = round((total_conformidade / total_registros) * 100, 2) if total_registros > 0 else 100.0

    df_estouro = df[mascara_estouro].copy()

    if not df_estouro.empty:
        df_estouro['EXCESSO_M3_H'] = (df_estouro['Q_MAX'] - df_estouro['Q_MAX_OUTORGA']).round(2)
        
        # Agrupamento por elevatória
        df_por_elev = df_estouro.groupby('ELEVATORIA').agg(
            DIAS_COM_ESTOURO=('DATA', 'count'),
            MAIOR_EXCESSO_M3_H=('EXCESSO_M3_H', 'max'),
            MEDIA_EXCESSO_M3_H=('EXCESSO_M3_H', 'mean'),
            OUTORGA_PERMITIDA=('Q_MAX_OUTORGA', 'first')
        ).reset_index().sort_values(by='DIAS_COM_ESTOURO', ascending=False)
        
        df_por_elev['MEDIA_EXCESSO_M3_H'] = df_por_elev['MEDIA_EXCESSO_M3_H'].round(2)

        # Top 10 maiores picos
        cols_top = ['DATA', 'ELEVATORIA', 'Q_MEDIA', 'Q_MAX', 'Q_MAX_OUTORGA', 'EXCESSO_M3_H']
        df_top = df_estouro.sort_values(by='EXCESSO_M3_H', ascending=False)[cols_top].head(10)
    else:
        df_por_elev = pd.DataFrame(columns=['ELEVATORIA', 'DIAS_COM_ESTOURO', 'MAIOR_EXCESSO_M3_H', 'MEDIA_EXCESSO_M3_H', 'OUTORGA_PERMITIDA'])
        df_top = pd.DataFrame()

    return {
        'total_registros': total_registros,
        'total_conformidade': total_conformidade,
        'total_estouros': total_estouros,
        'percentual_conformidade': perc_conformidade,
        'df_estouros_por_elevatoria': df_por_elev,
        'df_top_excessos': df_top
    }
