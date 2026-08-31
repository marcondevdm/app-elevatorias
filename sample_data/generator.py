"""
Módulo de Geração de Dados Sintéticos e Modelos de Exemplo.
Cria DataFrames realistas de telemetria, De-Para em Excel e níveis de reservatório
para fins de teste imediato, validação de regras de negócio e demonstração.
"""

import pandas as pd
import numpy as np

def gerar_dados_amostra_completos(
    data_inicio: str = '2026-06-01',
    data_fim: str = '2026-06-30'
) -> dict[str, pd.DataFrame]:
    """
    Gera um conjunto completo e coerente de dados sintéticos para demonstração.
    
    Returns:
        dict com as chaves:
            - 'df_bruto': DataFrame minuto a minuto de status das bombas
            - 'df_depara_bombas': DataFrame da aba BOMBAS_ELIPSE
            - 'df_capacidade_bombas': DataFrame da aba CAPACIDADE_BOMBAS
            - 'df_max_outorga': DataFrame da aba CAPACIDADE_MAX_ELEVATORIAS
            - 'df_depara_niveis': DataFrame da aba RESERVATORIO_NIVEL
            - 'df_nivel_medio': DataFrame com níveis médios
            - 'df_nivel_maximo': DataFrame com níveis máximos
            - 'df_nivel_minimo': DataFrame com níveis mínimos
    """
    np.random.seed(42)

    # 1. Estrutura de Elevatórias e Bombas
    elevatorias = ['EEE 001', 'EEE 002', 'EEE 003']
    bombas_por_elev = {
        'EEE 001': ['BBA-01', 'BBA-02', 'BBA-03'],
        'EEE 002': ['BBA-01', 'BBA-02'],
        'EEE 003': ['BBA-01', 'BBA-02', 'BBA-03', 'BBA-04']
    }

    # 2. Construção das tabelas de De-Para
    lista_bombas_depara = []
    lista_capacidade = []
    lista_outorga = []
    lista_niveis_depara = []

    for elev in elevatorias:
        # Outorga
        q_outorga = 350.0 if elev == 'EEE 001' else (250.0 if elev == 'EEE 002' else 500.0)
        lista_outorga.append({'ELEVATORIA': elev, 'Q_MAX_OUTORGA': q_outorga})

        # Nível
        tag_niv = f"TAG_NIV_{elev.replace(' ', '_')}"
        lista_niveis_depara.append({'TAG_ELIPSE': tag_niv, 'ELEVATORIA': elev})

        # Bombas e Capacidade
        for bba in bombas_por_elev[elev]:
            tag_bba = f"TAG_{elev.replace(' ', '_')}_{bba.replace('-', '')}"
            lista_bombas_depara.append({
                'TAG_ELIPSE': tag_bba,
                'ELEVATORIA': elev,
                'BOMBA': bba
            })
            cap = 110.0 if bba == 'BBA-01' else (115.0 if bba == 'BBA-02' else 125.0)
            lista_capacidade.append({
                'BOMBA': bba,
                'ELEVATORIA': elev,
                'Q_BOMBA': cap
            })

    df_depara_bombas = pd.DataFrame(lista_bombas_depara)
    df_capacidade_bombas = pd.DataFrame(lista_capacidade)
    df_max_outorga = pd.DataFrame(lista_outorga)
    df_depara_niveis = pd.DataFrame(lista_niveis_depara)

    # 3. Geração de Telemetria de Status das Bombas
    # Para performance na amostra, usamos passos de 15 minutos e simulamos padrão diário
    timestamps = pd.date_range(start=f"{data_inicio} 00:00:00", end=f"{data_fim} 23:59:00", freq='15min')
    
    df_bruto = pd.DataFrame({'Timestamp': timestamps.strftime('%d/%m/%Y %H:%M:%S')})

    for _, row in df_depara_bombas.iterrows():
        tag = row['TAG_ELIPSE']
        col_name = f"{tag} Value"
        # Probabilidade de estar ligado dependendo da hora do dia
        horas = timestamps.hour
        prob_ligado = np.where((horas >= 6) & (horas <= 22), 0.65, 0.25)
        status = (np.random.rand(len(timestamps)) < prob_ligado).astype(int)
        df_bruto[col_name] = status

    # 4. Geração dos Níveis (Médio, Máximo, Mínimo)
    # Níveis diários/horários realistas em metros (ex: 1.5m a 4.5m)
    timestamps_niveis = pd.date_range(start=f"{data_inicio} 00:00:00", end=f"{data_fim} 23:00:00", freq='1D')

    df_nivel_medio = pd.DataFrame({'Timestamp': timestamps_niveis.strftime('%d/%m/%Y %H:%M:%S')})
    df_nivel_maximo = pd.DataFrame({'Timestamp': timestamps_niveis.strftime('%d/%m/%Y %H:%M:%S')})
    df_nivel_minimo = pd.DataFrame({'Timestamp': timestamps_niveis.strftime('%d/%m/%Y %H:%M:%S')})

    for _, row in df_depara_niveis.iterrows():
        tag = row['TAG_ELIPSE']
        col_name = f"{tag} Value"

        base_nivel = np.random.uniform(3.0, 4.2, size=len(timestamps_niveis))
        ruido = np.random.normal(0, 0.2, size=len(timestamps_niveis))
        
        med = np.clip(base_nivel + ruido, 1.0, 5.0)
        maxi = np.clip(med + np.random.uniform(0.3, 0.8, size=len(timestamps_niveis)), med, 5.5)
        mini = np.clip(med - np.random.uniform(0.3, 0.8, size=len(timestamps_niveis)), 0.5, med)

        df_nivel_medio[col_name] = np.round(med, 2)
        df_nivel_maximo[col_name] = np.round(maxi, 2)
        df_nivel_minimo[col_name] = np.round(mini, 2)

    return {
        'df_bruto': df_bruto,
        'df_depara_bombas': df_depara_bombas,
        'df_capacidade_bombas': df_capacidade_bombas,
        'df_max_outorga': df_max_outorga,
        'df_depara_niveis': df_depara_niveis,
        'df_nivel_medio': df_nivel_medio,
        'df_nivel_maximo': df_nivel_maximo,
        'df_nivel_minimo': df_nivel_minimo
    }
