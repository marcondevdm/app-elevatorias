"""
Módulo de Tratamento de Níveis de Reservatórios e Poços.
Realiza o unpivot (melt) dos níveis médio, máximo e mínimo, cruza com o De-Para,
aplica escalonamento percentual, filtros estatísticos, hierarquia física e jitter anti-repetição.
"""

import pandas as pd
import numpy as np
import gc

def _unpivot_e_mapear_nivel(
    df_raw: pd.DataFrame,
    df_depara_niveis: pd.DataFrame,
    nome_coluna_nivel: str,
    fuso_horario: str = 'Etc/GMT+4'
) -> pd.DataFrame:
    """Função auxiliar para unpivot (melt), merge de De-Para e conversão de fuso."""
    if df_raw.empty:
        return pd.DataFrame(columns=['ELEVATORIA', 'DATA_HORA', nome_coluna_nivel])

    # 1. Identificar colunas de data/hora e valores
    timestamp_cols = [c for c in df_raw.columns if 'Timestamp' in c or 'Data' in c or 'DATA' in c]
    timestamp_col_ref = timestamp_cols[0] if timestamp_cols else df_raw.columns[0]
    
    tag_value_cols = [c for c in df_raw.columns if c.endswith(' Value') or 'Value' in c]
    if not tag_value_cols:
        tag_value_cols = [c for c in df_raw.columns if c != timestamp_col_ref]

    # 2. Cópia e limpeza
    df_temp = df_raw.copy()
    df_temp.rename(columns={timestamp_col_ref: 'DATA_HORA_BRUTA'}, inplace=True)
    
    # Remove outras colunas de timestamp
    cols_to_drop = [c for c in timestamp_cols if c != timestamp_col_ref and c in df_temp.columns]
    df_temp.drop(columns=cols_to_drop, errors='ignore', inplace=True)

    # Conversão de formato de data
    df_temp['DATA_HORA_BRUTA'] = pd.to_datetime(
        df_temp['DATA_HORA_BRUTA'],
        dayfirst=True,
        errors='coerce'
    )

    # 3. Unpivot (Derretimento)
    df_melted = pd.melt(
        df_temp,
        id_vars=['DATA_HORA_BRUTA'],
        value_vars=tag_value_cols,
        var_name='TAG_VALUE_COL',
        value_name='VALOR_OPERACAO'
    )
    
    df_melted['TAG_ELIPSE'] = df_melted['TAG_VALUE_COL'].astype(str).str.replace(' Value', '', regex=False).str.strip()
    df_melted.dropna(subset=['DATA_HORA_BRUTA'], inplace=True)
    df_melted.drop(columns=['TAG_VALUE_COL'], inplace=True, errors='ignore')

    # 4. Ajuste de fuso horário
    df_melted.rename(columns={'DATA_HORA_BRUTA': 'DATA_HORA'}, inplace=True)
    if df_melted['DATA_HORA'].dt.tz is None:
        df_melted['DATA_HORA'] = df_melted['DATA_HORA'].dt.tz_localize('UTC', ambiguous='NaT')
    
    try:
        df_melted['DATA_HORA'] = df_melted['DATA_HORA'].dt.tz_convert(fuso_horario)
    except Exception:
        pass
    
    # Remove tz para operações posteriores simples
    df_melted['DATA_HORA'] = df_melted['DATA_HORA'].dt.tz_localize(None)

    # 5. Merge com De-Para de Níveis
    df_dp = df_depara_niveis.copy()
    if 'RESERVATORIO' in df_dp.columns and 'TAG_ELIPSE' not in df_dp.columns:
        df_dp.rename(columns={'RESERVATORIO': 'TAG_ELIPSE'}, inplace=True)
        
    for c in ['TAG_ELIPSE', 'ELEVATORIA']:
        if c in df_dp.columns:
            df_dp[c] = df_dp[c].astype(str).str.replace(r'[\xa0\s]+', ' ', regex=True).str.strip().str.upper()

    df_melted['TAG_ELIPSE'] = df_melted['TAG_ELIPSE'].astype(str).str.strip().str.upper()
    df_merged = df_melted.merge(df_dp, on='TAG_ELIPSE', how='inner')

    df_merged.rename(columns={'VALOR_OPERACAO': nome_coluna_nivel}, inplace=True)
    return df_merged[['ELEVATORIA', 'DATA_HORA', nome_coluna_nivel]]


def _aplicar_logica_correcao_grupo(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica escalonamento percentual e validações físicas por elevatória."""
    if df.empty:
        return df

    df_grp = df.sort_values(by='DATA_HORA').reset_index(drop=True).copy()

    # 1. Escalonamento para percentual (0 a 100%)
    percentil_corte = 0.90
    if len(df_grp) < 2:
        limite_altos_valores = df_grp['NIVEL_MAXIMO'].max() if not df_grp.empty else 0
    else:
        limite_altos_valores = df_grp['NIVEL_MAXIMO'].quantile(percentil_corte)

    dias_de_pico = df_grp[df_grp['NIVEL_MAXIMO'] >= limite_altos_valores]

    if not dias_de_pico.empty:
        valor_maximo_representativo = dias_de_pico['NIVEL_MAXIMO'].mean()
    else:
        valor_maximo_representativo = df_grp['NIVEL_MAXIMO'].max()

    if valor_maximo_representativo > 0:
        fator_escala = 100.0 / valor_maximo_representativo
    else:
        fator_escala = 1.0

    df_grp['NIVEL_MAXIMO_PERC'] = (df_grp['NIVEL_MAXIMO'] * fator_escala).clip(lower=0.0)
    df_grp['NIVEL_MEDIO_PERC'] = (df_grp['NIVEL_MEDIO'] * fator_escala).clip(lower=0.0)
    df_grp['NIVEL_MINIMO_PERC'] = (df_grp['NIVEL_MINIMO'] * fator_escala).clip(lower=0.0)

    # 2. Proteção estatística e fallbacks para valores espúrios ou zerados
    minimo_limite_inf = df_grp.loc[df_grp['NIVEL_MINIMO_PERC'] > 0, 'NIVEL_MINIMO_PERC'].quantile(0.05)
    if pd.isna(minimo_limite_inf) or minimo_limite_inf <= 0:
        minimo_limite_inf = 1.0

    minimo_fallback = df_grp.loc[df_grp['NIVEL_MINIMO_PERC'] >= minimo_limite_inf, 'NIVEL_MINIMO_PERC'].mean()
    if pd.isna(minimo_fallback):
        minimo_fallback = minimo_limite_inf

    media_limite_inf = df_grp['NIVEL_MEDIO_PERC'].quantile(0.05)
    if pd.isna(media_limite_inf) or media_limite_inf <= 0:
        media_limite_inf = 5.0

    media_fallback = df_grp.loc[df_grp['NIVEL_MEDIO_PERC'] >= media_limite_inf, 'NIVEL_MEDIO_PERC'].mean()
    if pd.isna(media_fallback):
        media_fallback = df_grp['NIVEL_MEDIO_PERC'].mean() if not df_grp.empty else 10.0

    for i in range(len(df_grp)):
        # Máximo > 100%
        if df_grp.loc[i, 'NIVEL_MAXIMO_PERC'] > 100:
            anteriores = df_grp.loc[:i-1, 'NIVEL_MAXIMO_PERC'][lambda x: x <= 100]
            df_grp.loc[i, 'NIVEL_MAXIMO_PERC'] = anteriores.mean() if not anteriores.empty else 100.0

        # Médio > 100%
        if df_grp.loc[i, 'NIVEL_MEDIO_PERC'] > 100:
            anteriores = df_grp.loc[:i-1, 'NIVEL_MEDIO_PERC'][lambda x: x <= 100]
            df_grp.loc[i, 'NIVEL_MEDIO_PERC'] = anteriores.mean() if not anteriores.empty else 100.0

        # Médio baixo demais
        if df_grp.loc[i, 'NIVEL_MEDIO_PERC'] < media_limite_inf:
            anteriores = df_grp.loc[:i-1, 'NIVEL_MEDIO_PERC'][lambda x: x >= media_limite_inf]
            df_grp.loc[i, 'NIVEL_MEDIO_PERC'] = anteriores.mean() if not anteriores.empty else media_fallback

        # Mínimo baixo demais
        if df_grp.loc[i, 'NIVEL_MINIMO_PERC'] < minimo_limite_inf:
            anteriores = df_grp.loc[:i-1, 'NIVEL_MINIMO_PERC'][lambda x: x >= minimo_limite_inf]
            df_grp.loc[i, 'NIVEL_MINIMO_PERC'] = anteriores.mean() if not anteriores.empty else minimo_fallback

    # 3. Ajuste de Hierarquia Física: Min <= Medio <= Max <= 100%
    df_grp['NIVEL_MINIMO_PERC'] = np.minimum(df_grp['NIVEL_MINIMO_PERC'], df_grp['NIVEL_MEDIO_PERC'])
    df_grp['NIVEL_MEDIO_PERC'] = np.minimum(df_grp['NIVEL_MEDIO_PERC'], df_grp['NIVEL_MAXIMO_PERC'])
    df_grp['NIVEL_MEDIO_PERC'] = np.maximum(df_grp['NIVEL_MEDIO_PERC'], df_grp['NIVEL_MINIMO_PERC'])
    df_grp['NIVEL_MAXIMO_PERC'] = np.minimum(df_grp['NIVEL_MAXIMO_PERC'], 100.0)

    # 4. Jitter anti-repetição para variações suaves
    jitter_val = 0.01
    for col in ['NIVEL_MINIMO_PERC', 'NIVEL_MEDIO_PERC', 'NIVEL_MAXIMO_PERC']:
        for i in range(1, len(df_grp)):
            if df_grp.loc[i, col] == df_grp.loc[i-1, col]:
                df_grp.loc[i, col] = min(df_grp.loc[i, col] + jitter_val, 100.0)

    return df_grp[['ELEVATORIA', 'DATA_HORA', 'NIVEL_MEDIO_PERC', 'NIVEL_MAXIMO_PERC', 'NIVEL_MINIMO_PERC']]


def processar_niveis(
    df_nivel_medio_raw: pd.DataFrame,
    df_nivel_maximo_raw: pd.DataFrame,
    df_nivel_minimo_raw: pd.DataFrame,
    df_depara_niveis: pd.DataFrame,
    fuso_horario: str = 'Etc/GMT+4'
) -> pd.DataFrame:
    """
    Executa o unpivot, correções físicas e cálculo percentual dos níveis de elevatórias.
    
    Returns:
        pd.DataFrame com colunas: ['ELEVATORIA', 'DATA', 'NIVEL_MEDIO', 'NIVEL_MAXIMO', 'NIVEL_MINIMO']
    """
    # 1. Unpivot de cada uma das 3 bases
    df_medio = _unpivot_e_mapear_nivel(df_nivel_medio_raw, df_depara_niveis, 'NIVEL_MEDIO', fuso_horario)
    df_maximo = _unpivot_e_mapear_nivel(df_nivel_maximo_raw, df_depara_niveis, 'NIVEL_MAXIMO', fuso_horario)
    df_minimo = _unpivot_e_mapear_nivel(df_nivel_minimo_raw, df_depara_niveis, 'NIVEL_MINIMO', fuso_horario)

    if df_medio.empty and df_maximo.empty and df_minimo.empty:
        return pd.DataFrame(columns=['ELEVATORIA', 'DATA', 'NIVEL_MEDIO', 'NIVEL_MAXIMO', 'NIVEL_MINIMO'])

    # 2. Conversão e higienização numérica
    for df_item, col_nome in [(df_medio, 'NIVEL_MEDIO'), (df_maximo, 'NIVEL_MAXIMO'), (df_minimo, 'NIVEL_MINIMO')]:
        if not df_item.empty:
            df_item[col_nome] = df_item[col_nome].astype(str).str.replace(',', '.', regex=False)
            df_item[col_nome] = pd.to_numeric(df_item[col_nome], errors='coerce').fillna(0.0)

    # 3. Mesclagem das 3 bases
    df_comb = pd.merge(df_medio, df_maximo, on=['ELEVATORIA', 'DATA_HORA'], how='outer')
    df_comb = pd.merge(df_comb, df_minimo, on=['ELEVATORIA', 'DATA_HORA'], how='outer')

    df_comb[['NIVEL_MEDIO', 'NIVEL_MAXIMO', 'NIVEL_MINIMO']] = (
        df_comb[['NIVEL_MEDIO', 'NIVEL_MAXIMO', 'NIVEL_MINIMO']].fillna(0.0)
    )

    # 4. Aplicação da lógica de correção por elevatória
    df_corrigido_list = []
    for elev, df_grp in df_comb.groupby('ELEVATORIA'):
        df_proc = _aplicar_logica_correcao_grupo(df_grp)
        df_corrigido_list.append(df_proc)

    if not df_corrigido_list:
        return pd.DataFrame(columns=['ELEVATORIA', 'DATA', 'NIVEL_MEDIO', 'NIVEL_MAXIMO', 'NIVEL_MINIMO'])

    df_final = pd.concat(df_corrigido_list, ignore_index=True)
    df_final.rename(columns={
        'NIVEL_MEDIO_PERC': 'NIVEL_MEDIO',
        'NIVEL_MAXIMO_PERC': 'NIVEL_MAXIMO',
        'NIVEL_MINIMO_PERC': 'NIVEL_MINIMO',
        'DATA_HORA': 'DATA'
    }, inplace=True)

    # Padroniza para data pura normalizada se os dados forem diários
    df_final['DATA'] = pd.to_datetime(df_final['DATA']).dt.normalize()
    
    # Se houver múltiplos registros no mesmo dia (ex: dados horários), agrega diário
    df_final = df_final.groupby(['ELEVATORIA', 'DATA'], as_index=False).agg({
        'NIVEL_MEDIO': 'mean',
        'NIVEL_MAXIMO': 'max',
        'NIVEL_MINIMO': 'min'
    })

    df_final['NIVEL_MEDIO'] = df_final['NIVEL_MEDIO'].round(2)
    df_final['NIVEL_MAXIMO'] = df_final['NIVEL_MAXIMO'].round(2)
    df_final['NIVEL_MINIMO'] = df_final['NIVEL_MINIMO'].round(2)

    return df_final
