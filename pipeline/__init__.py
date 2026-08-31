"""
Pacote de Pipeline de Processamento de Dados de Elevatórias.
Contém módulos para telemetria de bombas, cálculo de vazões e outorgas,
tratamento e escalonamento de níveis de reservatórios, e consolidação analítica.
"""

from .telemetry import processar_telemetria_bombas
from .flow import calcular_vazoes_e_outorga
from .levels import processar_niveis
from .consolidator import consolidar_dados_analiticos, gerar_relatorio_auditoria

__all__ = [
    'processar_telemetria_bombas',
    'calcular_vazoes_e_outorga',
    'processar_niveis',
    'consolidar_dados_analiticos',
    'gerar_relatorio_auditoria'
]
