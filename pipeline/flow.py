"""
Módulo de Cálculo de Vazões, Volume Diário e Ajuste de Outorga.
Calcula o volume diário bombeado (m³/dia), vazão média horária (Q_MEDIA),
vazões cíclicas estimadas (Q_MIN e Q_MAX) e conformidade/ajustes com relação à Outorga Máxima.
"""

import pandas as pd
import numpy as np

def calcular_vazoes_e_outorga(
    resumo_bombas: pd.DataFrame,
    df_capacidade_bombas: pd.DataFrame,
    df_max_outorga: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Calcula vazões diárias, agregações por elevatória e enquadramento de outorga.
    
    Args:
        resumo_bombas: DataFrame vindo de processar_telemetria_bombas.
        df_capacidade_bombas: DataFrame da aba CAPACIDADE_BOMBAS (BOMBA, ELEVATORIA, Q_BOMBA).
        df_max_outorga: DataFrame da aba CAPACIDADE_MAX_ELEVATORIAS (ELEVATORIA, Q_MAX_OUTORGA).
        
    Returns:
        tuple[pd.DataFrame, pd.DataFrame]:
            1. resumo_agregado: Nível diário por Elevatória (com vazões e outorga).
            2. resumo_com_capacidade: Nível diário por Bomba (com Q_BOMBA e M3_DIA).
    """
    if resumo_bombas.empty:
        cols_agregado = ['ELEVATORIA', 'DATA', 'HORAS_LIGADO', 'M3_DIA', 'Q_MEDIA', 
                         'Q_MAX_OUTORGA', 'Q_MIN', 'Q_MAX', 'SUCESSO_AJUSTE', 'DIA_DA_SEMANA']
        return pd.DataFrame(columns=cols_agregado), pd.DataFrame()

    # 1. Limpeza de colunas e dados no De-Para de Capacidade
    df_cap = df_capacidade_bombas.copy()
    df_cap.columns = df_cap.columns.str.strip()
    
    if 'EQUIPAMENTO' in df_cap.columns and 'BOMBA' not in df_cap.columns:
        df_cap.rename(columns={'EQUIPAMENTO': 'BOMBA'}, inplace=True)
        
    for col in ['BOMBA', 'ELEVATORIA']:
        if col in df_cap.columns:
            df_cap[col] = df_cap[col].astype(str).str.replace(r'[\xa0\s]+', ' ', regex=True).str.strip().str.upper()
            
    df_cap['Q_BOMBA'] = pd.to_numeric(df_cap['Q_BOMBA'], errors='coerce').fillna(0.0)

    # 2. Padronização do resumo_bombas para merge
    resumo_calc = resumo_bombas.copy()
    resumo_calc['BOMBA_KEY'] = resumo_calc['BOMBA'].astype(str).str.replace(r'[\xa0\s]+', ' ', regex=True).str.strip().str.upper()
    resumo_calc['ELEV_KEY'] = resumo_calc['ELEVATORIA'].astype(str).str.replace(r'[\xa0\s]+', ' ', regex=True).str.strip().str.upper()

    df_cap['BOMBA_KEY'] = df_cap['BOMBA']
    df_cap['ELEV_KEY'] = df_cap['ELEVATORIA']

    # Merge da capacidade da bomba (Q_BOMBA em m³/h)
    resumo_com_capacidade = resumo_calc.merge(
        df_cap[['BOMBA_KEY', 'ELEV_KEY', 'Q_BOMBA']],
        on=['BOMBA_KEY', 'ELEV_KEY'],
        how='left'
    )
    resumo_com_capacidade['Q_BOMBA'] = resumo_com_capacidade['Q_BOMBA'].fillna(0.0)
    
    # Cálculo do volume diário bombeado por equipamento (m³/dia)
    resumo_com_capacidade['M3_DIA'] = (resumo_com_capacidade['HORAS_LIGADO'] * resumo_com_capacidade['Q_BOMBA']).astype(np.float64)
    resumo_com_capacidade.drop(columns=['BOMBA_KEY', 'ELEV_KEY'], inplace=True, errors='ignore')

    # 3. Agregação diária a nível de Elevatória
    resumo_agregado = resumo_com_capacidade.groupby(['ELEVATORIA', 'DATA'], as_index=False).agg(
        HORAS_LIGADO=('HORAS_LIGADO', 'sum'),
        M3_DIA=('M3_DIA', 'sum')
    )
    
    # Vazão Média diária (m³/h) diluída em 24 horas
    resumo_agregado['Q_MEDIA'] = (resumo_agregado['M3_DIA'] / 24.0).astype(np.float64)

    # 4. Merge com a Outorga Máxima Permitida (Q_MAX_OUTORGA)
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

    # 5. Cálculo Vetorial das Vazões Cíclicas (Q_MIN e Q_MAX)
    resumo_agregado['DATA'] = pd.to_datetime(resumo_agregado['DATA'])
    dia_do_ano = resumo_agregado['DATA'].dt.dayofyear
    q_med = resumo_agregado['Q_MEDIA'].values
    q_outorga = resumo_agregado['Q_MAX_OUTORGA'].values

    # Modelo trigonométrico cíclico
    cos_val = np.cos(q_med * dia_do_ano)
    cos_sq = cos_val ** 2

    q_min_bruto = q_med * (0.7 - 0.1 * cos_val)
    q_max_bruto = q_med * (1.6 - 0.2 * cos_sq)

    resumo_agregado['Q_MIN'] = q_min_bruto
    resumo_agregado['Q_MAX'] = q_max_bruto

    # 6. Algoritmo de Ajuste e Rastreabilidade de Outorga
    def recalcular_vazoes(q_m, fator):
        q_min_adj = q_m * (0.7 - 0.1 * np.cos(q_m * fator))
        q_max_adj = q_m * (1.6 - 0.2 * (np.cos(q_m * fator)) ** 2)
        return q_min_adj, q_max_adj

    status_lista = []
    q_min_final = []
    q_max_final = []

    for idx, row in resumo_agregado.iterrows():
        qm = row['Q_MEDIA']
        qmax_orig = row['Q_MAX']
        qmin_orig = row['Q_MIN']
        qout = row['Q_MAX_OUTORGA']
        dia_orig = row['DATA'].dayofyear

        if qout <= 0:
            status_lista.append('Sem Outorga Mapeada')
            q_min_final.append(qmin_orig)
            q_max_final.append(qmax_orig)
        elif qm > qout:
            status_lista.append('Crítico: Q_MEDIA Excede Outorga')
            q_min_final.append(qmin_orig)
            q_max_final.append(qout)  # Limita ao teto para segurança
        elif (qmax_orig > qout) or (qmin_orig > qout):
            # Tenta varredura de ajuste cíclico nos próximos 100 dias
            ajustado = False
            for offset in range(1, 101):
                fator_teste = (dia_orig + offset) % 366
                if fator_teste == 0:
                    fator_teste = 366
                qmin_t, qmax_t = recalcular_vazoes(qm, fator_teste)
                if (qmax_t <= qout) and (qmin_t <= qout) and (qm <= qout):
                    status_lista.append('Corrigido com Sucesso')
                    q_min_final.append(qmin_t)
                    q_max_final.append(qout) # Trava de conformidade
                    ajustado = True
                    break
            if not ajustado:
                status_lista.append('Falhou no Ajuste (Limitado à Outorga)')
                q_min_final.append(qmin_orig)
                q_max_final.append(qout)
        else:
            status_lista.append('Manteve Original (Dentro do Limite)')
            q_min_final.append(qmin_orig)
            q_max_final.append(qmax_orig)

    resumo_agregado['SUCESSO_AJUSTE'] = status_lista
    resumo_agregado['Q_MIN'] = np.round(q_min_final, 2)
    resumo_agregado['Q_MAX'] = np.round(q_max_final, 2)
    resumo_agregado['Q_MEDIA'] = np.round(resumo_agregado['Q_MEDIA'], 2)
    resumo_agregado['HORAS_LIGADO'] = np.round(resumo_agregado['HORAS_LIGADO'], 2)
    resumo_agregado['M3_DIA'] = np.round(resumo_agregado['M3_DIA'], 2)

    # Dia da semana formatado em inglês/português
    mapa_dias = {
        0: 'Segunda-feira', 1: 'Terça-feira', 2: 'Quarta-feira',
        3: 'Quinta-feira', 4: 'Sexta-feira', 5: 'Sábado', 6: 'Domingo'
    }
    resumo_agregado['DIA_DA_SEMANA'] = resumo_agregado['DATA'].dt.weekday.map(mapa_dias)

    return resumo_agregado, resumo_com_capacidade
