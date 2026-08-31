"""
Módulo de Telemetria de Operação de Bombas (Ultra-Otimizado com Vetorização NumPy/Pandas).
Processa milhões de linhas em segundos agrupando todas as bombas em uma única operação matricial.
"""

from __future__ import annotations
import pandas as pd
import numpy as np
import gc

def padronizar_de_para_bombas(df_depara: pd.DataFrame) -> pd.DataFrame:
    """Padroniza e limpa as colunas do De-Para de Bombas."""
    df = df_depara.copy()
    if 'EQUIPAMENTO' in df.columns and 'BOMBA' not in df.columns:
        df.rename(columns={'EQUIPAMENTO': 'BOMBA'}, inplace=True)
        
    for col in ['TAG_ELIPSE', 'ELEVATORIA', 'BOMBA']:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace(r'[\xa0\s]+', ' ', regex=True).str.strip()
            
    return df

def processar_telemetria_bombas(
    df_bruto: pd.DataFrame,
    df_depara_bombas: pd.DataFrame,
    data_inicio: pd.Timestamp | str,
    data_fim: pd.Timestamp | str,
    elevatorias_selecionadas: list[str] | None = None
) -> pd.DataFrame:
    """
    Processa os dados brutos minuto a minuto de status das bombas de forma vetorizada.
    
    Returns:
        pd.DataFrame com colunas: ['ELEVATORIA', 'BOMBA', 'DATA', 'HORAS_LIGADO']
    """
    data_inicio_ts = pd.to_datetime(data_inicio).normalize()
    data_fim_ts = pd.to_datetime(data_fim).normalize()
    
    # 1. Padronização do De-Para
    df_depara = padronizar_de_para_bombas(df_depara_bombas)
    
    if elevatorias_selecionadas:
        elevs_upper = {e.upper().strip() for e in elevatorias_selecionadas}
        df_depara = df_depara[df_depara['ELEVATORIA'].str.upper().isin(elevs_upper)].copy()
        
    if df_depara.empty:
        return pd.DataFrame(columns=['ELEVATORIA', 'BOMBA', 'DATA', 'HORAS_LIGADO'])

    # 2. Identificação e filtro de data rápido
    col_ts = df_bruto.columns[0]
    ts_series = pd.to_datetime(df_bruto[col_ts], dayfirst=True, errors='coerce')
    data_dt_series = ts_series.dt.normalize()
    
    # Máscara de filtro de período
    mascara_periodo = (data_dt_series >= data_inicio_ts) & (data_dt_series <= data_fim_ts)
    if not mascara_periodo.any():
        idx_periodo = pd.date_range(start=data_inicio_ts, end=data_fim_ts, freq='D')
        registros_zerados = []
        for _, row in df_depara.iterrows():
            df_vazio = pd.DataFrame({
                'DATA': idx_periodo,
                'HORAS_LIGADO': 0.0,
                'ELEVATORIA': row['ELEVATORIA'],
                'BOMBA': row['BOMBA']
            })
            registros_zerados.append(df_vazio)
        return pd.concat(registros_zerados, ignore_index=True) if registros_zerados else pd.DataFrame()

    # Filtra as linhas do período
    df_filtrado_raw = df_bruto.loc[mascara_periodo].copy()
    datas_agrupamento = data_dt_series.loc[mascara_periodo]

    # 3. Mapeamento de TAGs para colunas existentes
    colunas_valor = [c for c in df_filtrado_raw.columns if 'Value' in c]
    tag_para_coluna = {}
    for col in colunas_valor:
        tag_nome = col.replace(' Value', '').strip()
        tag_para_coluna[tag_nome] = col

    # Mapear cada linha do De-Para para uma coluna física
    colunas_para_somar = []
    mapa_col_info = {} # col -> (elevatoria, bomba)
    bombas_sem_coluna = []

    for _, row in df_depara.iterrows():
        tag = str(row['TAG_ELIPSE']).strip()
        elev = str(row['ELEVATORIA']).strip()
        bba = str(row['BOMBA']).strip()

        col_encontrada = None
        if tag in tag_para_coluna:
            col_encontrada = tag_para_coluna[tag]
        else:
            # Fallback substring
            matches = [c for c in colunas_valor if tag in c]
            if matches:
                col_encontrada = matches[0]

        if col_encontrada and col_encontrada in df_filtrado_raw.columns:
            colunas_para_somar.append(col_encontrada)
            mapa_col_info[col_encontrada] = (elev, bba)
        else:
            bombas_sem_coluna.append((elev, bba))

    # 4. Agregação Vetorizada Única (MUITO mais rápida que loop por bomba)
    idx_periodo = pd.date_range(start=data_inicio_ts, end=data_fim_ts, freq='D')
    resultados = []

    if colunas_para_somar:
        # Converte as colunas de status para booleano numérico de forma rápida
        matriz_status = (df_filtrado_raw[colunas_para_somar] == 1) | (df_filtrado_raw[colunas_para_somar] == '1')
        
        # Agrupamento único de todas as colunas de uma vez
        soma_minutos_diarios = matriz_status.groupby(datas_agrupamento).sum()
        
        # Reindexa todas as datas do período de uma só vez
        soma_minutos_diarios = soma_minutos_diarios.reindex(idx_periodo, fill_value=0)
        
        # Converte minutos para horas
        horas_diarias = (soma_minutos_diarios / 60.0).clip(lower=0.0, upper=24.0).astype(np.float32)

        for col, (elev, bba) in mapa_col_info.items():
            df_bba = pd.DataFrame({
                'DATA': idx_periodo,
                'HORAS_LIGADO': horas_diarias[col].values,
                'ELEVATORIA': elev,
                'BOMBA': bba
            })
            resultados.append(df_bba)

    # 5. Adiciona bombas não encontradas com horas zeradas
    for elev, bba in bombas_sem_coluna:
        df_bba_zerada = pd.DataFrame({
            'DATA': idx_periodo,
            'HORAS_LIGADO': 0.0,
            'ELEVATORIA': elev,
            'BOMBA': bba
        })
        resultados.append(df_bba_zerada)

    del df_filtrado_raw, ts_series, data_dt_series
    gc.collect()

    if resultados:
        resumo = pd.concat(resultados, ignore_index=True)
        resumo['DATA'] = pd.to_datetime(resumo['DATA']).dt.normalize()
        resumo.sort_values(by=['ELEVATORIA', 'BOMBA', 'DATA'], inplace=True)
        resumo.reset_index(drop=True, inplace=True)
        return resumo
    else:
        return pd.DataFrame(columns=['ELEVATORIA', 'BOMBA', 'DATA', 'HORAS_LIGADO'])
