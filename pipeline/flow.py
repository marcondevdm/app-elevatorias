"""
Módulo de Cálculo de Vazões, Volume Diário e Ajuste de Outorga (Otimizado com NumPy).
"""

from __future__ import annotations
import pandas as pd
import numpy as np

def calcular_vazoes_e_outorga(
    resumo_bombas: pd.DataFrame,
    df_capacidade_bombas: pd.DataFrame,
    df_max_outorga: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Cálculo vetorizado rápido de vazões diárias, volume e enquadramento de outorga.
    """
    if resumo_bombas.empty:
        cols_agregado = ['ELEVATORIA', 'DATA', 'HORAS_LIGADO', 'M3_DIA', 'Q_MEDIA', 
                         'Q_MAX_OUTORGA', 'Q_MIN', 'Q_MAX', 'SUCESSO_AJUSTE', 'DIA_DA_SEMANA']
        return pd.DataFrame(columns=cols_agregado), pd.DataFrame()

    # 1. Capacidade das bombas
    df_cap = df_capacidade_bombas.copy()
    df_cap.columns = df_cap.columns.str.strip()
    if 'EQUIPAMENTO' in df_cap.columns and 'BOMBA' not in df_cap.columns:
        df_cap.rename(columns={'EQUIPAMENTO': 'BOMBA'}, inplace=True)
        
    for col in ['BOMBA', 'ELEVATORIA']:
        if col in df_cap.columns:
            df_cap[col] = df_cap[col].astype(str).str.replace(r'[\xa0\s]+', ' ', regex=True).str.strip().str.upper()
            
    df_cap['Q_BOMBA'] = pd.to_numeric(df_cap['Q_BOMBA'], errors='coerce').fillna(0.0)

    resumo_calc = resumo_bombas.copy()
    resumo_calc['BOMBA_KEY'] = resumo_calc['BOMBA'].astype(str).str.replace(r'[\xa0\s]+', ' ', regex=True).str.strip().str.upper()
    resumo_calc['ELEV_KEY'] = resumo_calc['ELEVATORIA'].astype(str).str.replace(r'[\xa0\s]+', ' ', regex=True).str.strip().str.upper()

    df_cap['BOMBA_KEY'] = df_cap['BOMBA']
    df_cap['ELEV_KEY'] = df_cap['ELEVATORIA']

    resumo_com_capacidade = resumo_calc.merge(
        df_cap[['BOMBA_KEY', 'ELEV_KEY', 'Q_BOMBA']],
        on=['BOMBA_KEY', 'ELEV_KEY'],
        how='left'
    )
    resumo_com_capacidade['Q_BOMBA'] = resumo_com_capacidade['Q_BOMBA'].fillna(0.0)
    resumo_com_capacidade['M3_DIA'] = (resumo_com_capacidade['HORAS_LIGADO'] * resumo_com_capacidade['Q_BOMBA']).astype(np.float64)
    resumo_com_capacidade.drop(columns=['BOMBA_KEY', 'ELEV_KEY'], inplace=True, errors='ignore')

    # 2. Agregação diária por Elevatória
    resumo_agregado = resumo_com_capacidade.groupby(['ELEVATORIA', 'DATA'], as_index=False).agg(
        HORAS_LIGADO=('HORAS_LIGADO', 'sum'),
        M3_DIA=('M3_DIA', 'sum')
    )
    resumo_agregado['Q_MEDIA'] = (resumo_agregado['M3_DIA'] / 24.0).astype(np.float64)

    # 3. Outorga Máxima
    df_out = df_max_outorga.copy()
    df_out.columns = df_out.columns.str.strip()
    df_out['ELEV_KEY'] = df_out['ELEVATORIA'].astype(str).str.replace(r'[\xa0\s]+', ' ', regex=True).str.strip().str.upper()
    df_out['Q_MAX_OUTORGA'] = pd.to_numeric(df_out['Q_MAX_OUTORGA'], errors='coerce').fillna(0.0)

    resumo_agregado['ELEV_KEY'] = resumo_agregado['ELEVATORIA'].astype(str).str.replace(r'[\xa0\s]+', ' ', regex=True).str.strip().str.upper()
    resumo_agregado = resumo_agregado.merge(
        df_out[['ELEV_KEY', 'Q_MAX_OUTORGA']],
        on='ELEV_KEY',
        how='left'
    )
    resumo_agregado['Q_MAX_OUTORGA'] = resumo_agregado['Q_MAX_OUTORGA'].fillna(0.0)
    resumo_agregado.drop(columns=['ELEV_KEY'], inplace=True, errors='ignore')

    # 4. Cálculo Cíclico Vetorizado (NumPy)
    resumo_agregado['DATA'] = pd.to_datetime(resumo_agregado['DATA'])
    dia_ano = resumo_agregado['DATA'].dt.dayofyear.values
    qm = resumo_agregado['Q_MEDIA'].values
    qout = resumo_agregado['Q_MAX_OUTORGA'].values

    cos_val = np.cos(qm * dia_ano)
    cos_sq = cos_val ** 2
    q_min_bruto = qm * (0.7 - 0.1 * cos_val)
    q_max_bruto = qm * (1.6 - 0.2 * cos_sq)

    # 5. Enquadramento Vetorizado
    sem_outorga = (qout <= 0)
    critico_qm = (qm > qout) & (~sem_outorga)
    estourou = (q_max_bruto > qout) & (~sem_outorga) & (~critico_qm)

    q_max_final = np.where(sem_outorga, q_max_bruto, np.where(critico_qm | estourou, qout, q_max_bruto))
    q_min_final = q_min_bruto

    status_condicoes = [
        sem_outorga,
        critico_qm,
        estourou,
        (~estourou) & (~critico_qm) & (~sem_outorga)
    ]
    status_opcoes = [
        'Sem Outorga Mapeada',
        'Crítico: Q_MEDIA Excede Outorga',
        'Corrigido com Sucesso (Limitado à Outorga)',
        'Manteve Original (Dentro do Limite)'
    ]
    resumo_agregado['SUCESSO_AJUSTE'] = np.select(status_condicoes, status_opcoes, default='Manteve Original')

    resumo_agregado['Q_MIN'] = np.round(q_min_final, 2)
    resumo_agregado['Q_MAX'] = np.round(q_max_final, 2)
    resumo_agregado['Q_MEDIA'] = np.round(qm, 2)
    resumo_agregado['HORAS_LIGADO'] = np.round(resumo_agregado['HORAS_LIGADO'], 2)
    resumo_agregado['M3_DIA'] = np.round(resumo_agregado['M3_DIA'], 2)

    mapa_dias = {
        0: 'Segunda-feira', 1: 'Terça-feira', 2: 'Quarta-feira',
        3: 'Quinta-feira', 4: 'Sexta-feira', 5: 'Sábado', 6: 'Domingo'
    }
    resumo_agregado['DIA_DA_SEMANA'] = resumo_agregado['DATA'].dt.weekday.map(mapa_dias)

    return resumo_agregado, resumo_com_capacidade
