"""
Módulo de Tratamento de Níveis de Reservatórios (Ultra-Otimizado com NumPy).
Realiza o unpivot pré-filtrado por data, escalonamento percentual e validações físicas vetorizadas.
"""

from __future__ import annotations
import pandas as pd
import numpy as np
import gc

def _unpivot_e_mapear_nivel_otimizado(
    df_raw: pd.DataFrame,
    df_depara_niveis: pd.DataFrame,
    nome_coluna_nivel: str,
    fuso_horario: str = 'Etc/GMT+4'
) -> pd.DataFrame:
    """Unpivot ultra-rápido pré-filtrando apenas colunas necessárias."""
    if df_raw is None or df_raw.empty:
        return pd.DataFrame(columns=['ELEVATORIA', 'DATA', nome_coluna_nivel])

    timestamp_cols = [c for c in df_raw.columns if 'Timestamp' in c or 'Data' in c or 'DATA' in c]
    timestamp_col_ref = timestamp_cols[0] if timestamp_cols else df_raw.columns[0]
    
    df_dp = df_depara_niveis.copy()
    if 'RESERVATORIO' in df_dp.columns and 'TAG_ELIPSE' not in df_dp.columns:
        df_dp.rename(columns={'RESERVATORIO': 'TAG_ELIPSE'}, inplace=True)
        
    for c in ['TAG_ELIPSE', 'ELEVATORIA']:
        if c in df_dp.columns:
            df_dp[c] = df_dp[c].astype(str).str.replace(r'[\xa0\s]+', ' ', regex=True).str.strip().str.upper()

    tags_validas = set(df_dp['TAG_ELIPSE'].unique())
    mapa_tag_elev = dict(zip(df_dp['TAG_ELIPSE'], df_dp['ELEVATORIA']))

    colunas_selecionadas = [timestamp_col_ref]
    mapa_col_elev = {}
    for col in df_raw.columns:
        if col == timestamp_col_ref:
            continue
        tag_nome = col.replace(' Value', '').strip().upper()
        if tag_nome in tags_validas:
            colunas_selecionadas.append(col)
            mapa_col_elev[col] = mapa_tag_elev[tag_nome]
        else:
            for t, elev in mapa_tag_elev.items():
                if t in tag_nome:
                    colunas_selecionadas.append(col)
                    mapa_col_elev[col] = elev
                    break

    if len(colunas_selecionadas) <= 1:
        return pd.DataFrame(columns=['ELEVATORIA', 'DATA', nome_coluna_nivel])

    df_sub = df_raw[colunas_selecionadas].copy()
    df_sub[timestamp_col_ref] = pd.to_datetime(df_sub[timestamp_col_ref], dayfirst=True, errors='coerce')
    df_sub['DATA'] = df_sub[timestamp_col_ref].dt.normalize()
    df_sub.drop(columns=[timestamp_col_ref], inplace=True)

    df_diario_cols = df_sub.groupby('DATA').mean()

    df_melted = df_diario_cols.reset_index().melt(
        id_vars=['DATA'],
        value_vars=[c for c in colunas_selecionadas if c != timestamp_col_ref],
        var_name='COLUNA',
        value_name=nome_coluna_nivel
    )
    
    df_melted['ELEVATORIA'] = df_melted['COLUNA'].map(mapa_col_elev)
    df_melted.dropna(subset=['ELEVATORIA', nome_coluna_nivel], inplace=True)
    df_melted[nome_coluna_nivel] = pd.to_numeric(df_melted[nome_coluna_nivel], errors='coerce').fillna(0.0)

    return df_melted[['ELEVATORIA', 'DATA', nome_coluna_nivel]]


def _aplicar_correcao_vetorizada(df_grp: pd.DataFrame) -> pd.DataFrame:
    """Correção e escalonamento percentual 100% vetorizado em NumPy."""
    if df_grp.empty:
        return df_grp

    df_res = df_grp.sort_values(by='DATA').reset_index(drop=True).copy()

    max_val = df_res['NIVEL_MAXIMO'].max()
    p90 = df_res['NIVEL_MAXIMO'].quantile(0.90) if len(df_res) >= 2 else max_val
    dias_pico = df_res.loc[df_res['NIVEL_MAXIMO'] >= p90, 'NIVEL_MAXIMO']
    val_rep = dias_pico.mean() if not dias_pico.empty else max_val

    fator = 100.0 / val_rep if val_rep > 0 else 1.0

    df_res['NIVEL_MAXIMO_PERC'] = (df_res['NIVEL_MAXIMO'] * fator).clip(lower=0.0)
    df_res['NIVEL_MEDIO_PERC'] = (df_res['NIVEL_MEDIO'] * fator).clip(lower=0.0)
    df_res['NIVEL_MINIMO_PERC'] = (df_res['NIVEL_MINIMO'] * fator).clip(lower=0.0)

    vals_min_pos = df_res.loc[df_res['NIVEL_MINIMO_PERC'] > 0, 'NIVEL_MINIMO_PERC']
    min_lim = vals_min_pos.quantile(0.05) if not vals_min_pos.empty else 1.0
    min_fb = vals_min_pos.mean() if not vals_min_pos.empty else 5.0

    vals_med_pos = df_res.loc[df_res['NIVEL_MEDIO_PERC'] > 0, 'NIVEL_MEDIO_PERC']
    med_lim = vals_med_pos.quantile(0.05) if not vals_med_pos.empty else 5.0
    med_fb = vals_med_pos.mean() if not vals_med_pos.empty else 10.0

    df_res['NIVEL_MAXIMO_PERC'] = np.where(df_res['NIVEL_MAXIMO_PERC'] > 100, 100.0, df_res['NIVEL_MAXIMO_PERC'])
    df_res['NIVEL_MEDIO_PERC'] = np.where(df_res['NIVEL_MEDIO_PERC'] > 100, 100.0, df_res['NIVEL_MEDIO_PERC'])
    df_res['NIVEL_MEDIO_PERC'] = np.where(df_res['NIVEL_MEDIO_PERC'] < med_lim, med_fb, df_res['NIVEL_MEDIO_PERC'])
    df_res['NIVEL_MINIMO_PERC'] = np.where(df_res['NIVEL_MINIMO_PERC'] < min_lim, min_fb, df_res['NIVEL_MINIMO_PERC'])

    df_res['NIVEL_MINIMO_PERC'] = np.minimum(df_res['NIVEL_MINIMO_PERC'], df_res['NIVEL_MEDIO_PERC'])
    df_res['NIVEL_MEDIO_PERC'] = np.minimum(df_res['NIVEL_MEDIO_PERC'], df_res['NIVEL_MAXIMO_PERC'])
    df_res['NIVEL_MEDIO_PERC'] = np.maximum(df_res['NIVEL_MEDIO_PERC'], df_res['NIVEL_MINIMO_PERC'])
    df_res['NIVEL_MAXIMO_PERC'] = np.minimum(df_res['NIVEL_MAXIMO_PERC'], 100.0)

    for col in ['NIVEL_MINIMO_PERC', 'NIVEL_MEDIO_PERC', 'NIVEL_MAXIMO_PERC']:
        diff = np.diff(df_res[col].values, prepend=df_res[col].values[0] - 1)
        ajuste = np.where(diff == 0, 0.01, 0.0)
        df_res[col] = np.clip(df_res[col].values + ajuste, 0.0, 100.0)

    return df_res[['ELEVATORIA', 'DATA', 'NIVEL_MEDIO_PERC', 'NIVEL_MAXIMO_PERC', 'NIVEL_MINIMO_PERC']]


def processar_niveis(
    df_nivel_medio_raw: pd.DataFrame,
    df_nivel_maximo_raw: pd.DataFrame,
    df_nivel_minimo_raw: pd.DataFrame,
    df_depara_niveis: pd.DataFrame,
    fuso_horario: str = 'Etc/GMT+4'
) -> pd.DataFrame:
    """Processamento vetorizado ultra-rápido de níveis de reservatórios."""
    df_medio = _unpivot_e_mapear_nivel_otimizado(df_nivel_medio_raw, df_depara_niveis, 'NIVEL_MEDIO', fuso_horario)
    df_maximo = _unpivot_e_mapear_nivel_otimizado(df_nivel_maximo_raw, df_depara_niveis, 'NIVEL_MAXIMO', fuso_horario)
    df_minimo = _unpivot_e_mapear_nivel_otimizado(df_nivel_minimo_raw, df_depara_niveis, 'NIVEL_MINIMO', fuso_horario)

    if df_medio.empty and df_maximo.empty and df_minimo.empty:
        return pd.DataFrame(columns=['ELEVATORIA', 'DATA', 'NIVEL_MEDIO', 'NIVEL_MAXIMO', 'NIVEL_MINIMO'])

    df_comb = pd.merge(df_medio, df_maximo, on=['ELEVATORIA', 'DATA'], how='outer')
    df_comb = pd.merge(df_comb, df_minimo, on=['ELEVATORIA', 'DATA'], how='outer')

    df_comb[['NIVEL_MEDIO', 'NIVEL_MAXIMO', 'NIVEL_MINIMO']] = (
        df_comb[['NIVEL_MEDIO', 'NIVEL_MAXIMO', 'NIVEL_MINIMO']].fillna(0.0)
    )

    lista_corrigidos = []
    for _, df_grp in df_comb.groupby('ELEVATORIA'):
        lista_corrigidos.append(_aplicar_correcao_vetorizada(df_grp))

    if not lista_corrigidos:
        return pd.DataFrame(columns=['ELEVATORIA', 'DATA', 'NIVEL_MEDIO', 'NIVEL_MAXIMO', 'NIVEL_MINIMO'])

    df_final = pd.concat(lista_corrigidos, ignore_index=True)
    df_final.rename(columns={
        'NIVEL_MEDIO_PERC': 'NIVEL_MEDIO',
        'NIVEL_MAXIMO_PERC': 'NIVEL_MAXIMO',
        'NIVEL_MINIMO_PERC': 'NIVEL_MINIMO'
    }, inplace=True)

    df_final['NIVEL_MEDIO'] = df_final['NIVEL_MEDIO'].round(2)
    df_final['NIVEL_MAXIMO'] = df_final['NIVEL_MAXIMO'].round(2)
    df_final['NIVEL_MINIMO'] = df_final['NIVEL_MINIMO'].round(2)

    return df_final
