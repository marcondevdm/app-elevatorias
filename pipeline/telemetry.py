"""
Módulo de Telemetria de Operação de Bombas.
Processa os registros de operação minuto a minuto, correlaciona com o De-Para de TAGs
e calcula as horas de operação diárias para cada bomba e elevatória no período definido.
"""

import pandas as pd
import numpy as np
import gc

def padronizar_de_para_bombas(df_depara: pd.DataFrame) -> pd.DataFrame:
    """Padroniza e limpa as colunas do De-Para de Bombas."""
    df = df_depara.copy()
    
    # Se a coluna se chamar EQUIPAMENTO, renomeia para BOMBA
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
    Processa os dados brutos minuto a minuto de status das bombas.
    
    Args:
        df_bruto: DataFrame com timestamp na 1ª coluna e colunas de TAGs com status (1=ligado, 0=desligado).
        df_depara_bombas: DataFrame da aba BOMBAS_ELIPSE (TAG_ELIPSE, ELEVATORIA, BOMBA).
        data_inicio: Data inicial do período de processamento.
        data_fim: Data final do período de processamento.
        elevatorias_selecionadas: Lista opcional de elevatórias para filtrar.
        
    Returns:
        pd.DataFrame com colunas: ['ELEVATORIA', 'BOMBA', 'DATA', 'HORAS_LIGADO']
    """
    data_inicio_ts = pd.to_datetime(data_inicio)
    data_fim_ts = pd.to_datetime(data_fim)
    
    # Padronização do De-Para
    df_depara = padronizar_de_para_bombas(df_depara_bombas)
    
    if elevatorias_selecionadas:
        elevs_upper = [e.upper().strip() for e in elevatorias_selecionadas]
        df_depara = df_depara[df_depara['ELEVATORIA'].str.upper().isin(elevs_upper)].copy()
        
    if df_depara.empty:
        return pd.DataFrame(columns=['ELEVATORIA', 'BOMBA', 'DATA', 'HORAS_LIGADO'])

    # Preparação da base de telemetria bruta
    df_temp = df_bruto.copy()
    col_ts = df_temp.columns[0]
    df_temp[col_ts] = pd.to_datetime(df_temp[col_ts], dayfirst=True, errors='coerce')
    df_temp['DATA_DT'] = df_temp[col_ts].dt.normalize()
    
    # Filtro preliminar de data na base bruta para otimizar velocidade e memória
    df_temp = df_temp[
        (df_temp['DATA_DT'] >= data_inicio_ts.normalize()) & 
        (df_temp['DATA_DT'] <= data_fim_ts.normalize())
    ].copy()
    
    # Mapeamento rápido de colunas disponíveis que contêm 'Value'
    colunas_valor = [c for c in df_temp.columns if 'Value' in c]
    
    # Grade contínua de datas para garantir que todos os dias do período existam (mesmo zerados)
    idx_periodo = pd.date_range(start=data_inicio_ts.normalize(), end=data_fim_ts.normalize(), freq='D')
    
    resultados_finais = []
    
    for _, row in df_depara.iterrows():
        tag = str(row['TAG_ELIPSE']).strip()
        nome_elevatoria = str(row['ELEVATORIA']).strip()
        nome_bomba = str(row['BOMBA']).strip()
        
        # Procura coluna correspondente à TAG no df_bruto
        coluna_encontrada = [c for c in colunas_valor if tag in c]
        
        if coluna_encontrada:
            c_val = coluna_encontrada[0]
            
            # Filtra apenas os minutos onde o equipamento operou (status == 1)
            status_num = pd.to_numeric(df_temp[c_val], errors='coerce').fillna(0)
            df_ligado = df_temp[status_num == 1]
            
            if not df_ligado.empty:
                diario = df_ligado.groupby('DATA_DT').size().reset_index(name='MINUTOS')
                diario['HORAS_LIGADO'] = (diario['MINUTOS'] / 60.0).astype(np.float32)
                
                # Reindexa para cobrir todo o período selecionado
                df_indexed = diario.set_index('DATA_DT')
                df_resampled = df_indexed.reindex(idx_periodo).fillna({'HORAS_LIGADO': 0.0}).reset_index()
                df_resampled.rename(columns={'index': 'DATA'}, inplace=True)
            else:
                df_resampled = pd.DataFrame({
                    'DATA': idx_periodo,
                    'HORAS_LIGADO': 0.0
                })
        else:
            # TAG não encontrada na base bruta: gera série zerada
            df_resampled = pd.DataFrame({
                'DATA': idx_periodo,
                'HORAS_LIGADO': 0.0
            })
            
        df_resampled['ELEVATORIA'] = nome_elevatoria
        df_resampled['BOMBA'] = nome_bomba
        
        # Limita ao teto físico de 24 horas por dia por bomba
        df_resampled['HORAS_LIGADO'] = df_resampled['HORAS_LIGADO'].clip(lower=0.0, upper=24.0)
        
        resultados_finais.append(df_resampled[['ELEVATORIA', 'BOMBA', 'DATA', 'HORAS_LIGADO']])

    del df_temp
    gc.collect()
    
    if resultados_finais:
        resumo = pd.concat(resultados_finais, ignore_index=True)
        resumo['DATA'] = pd.to_datetime(resumo['DATA']).dt.normalize()
        resumo.sort_values(by=['ELEVATORIA', 'BOMBA', 'DATA'], inplace=True)
        resumo.reset_index(drop=True, inplace=True)
        return resumo
    else:
        return pd.DataFrame(columns=['ELEVATORIA', 'BOMBA', 'DATA', 'HORAS_LIGADO'])
