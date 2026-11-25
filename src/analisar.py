"""Etapa 4 - KPIs e analise preditiva (H2).
Uso: python analisar.py <pasta_dados>
Gera kpis.json, previsao.csv e metricas_h2.json na mesma pasta.
"""
import sys, json, pathlib
import numpy as np, pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

JANELA = ('2020-01', '2025-03')   # todos os extratos cobrem ate 03/2025 (cargas a partir de 04/2025)
TESTE_MESES = 12
HORIZONTE = 12

def kpis(fato, cli):
    ind = fato[fato.potencial_indevido]
    ativos = ind[ind.ativo]
    top = ind.groupby('entidade_padrao').size().sort_values(ascending=False)
    return {
        'clientes_analisados': int(len(cli)),
        'consignacoes_lidas': int(len(fato)),
        'seguros_peculios_identificados': int(len(ind)),
        'pct_clientes_com_desconto': round(100 * cli.tem_desconto_indevido.mean(), 1),
        'valor_mensal_ativo': round(float(ativos.valor_prestacao.sum()), 2),
        'descontos_ativos': int(len(ativos)),
        'total_ja_pago': round(float(ind.total_pago.sum()), 2),
        'restituicao_em_dobro_potencial': round(float(2 * ind.total_pago.sum()), 2),
        'media_meses_desconto': round(float(ind.pagas.mean()), 1),
        'mediana_meses_desconto': float(ind.pagas.median()),
        'ticket_medio_mensal': round(float(ind.valor_prestacao.mean()), 2),
        'entidade_lider': top.index[0], 'pct_entidade_lider': round(100 * top.iloc[0] / len(ind), 1),
        'top3_pct': round(100 * top.iloc[:3].sum() / len(ind), 1),
    }

def mape(y, p):
    return float(np.mean(np.abs((y - p) / y)) * 100)

def avaliar(s, nome):
    """Treina nos meses antigos, testa nos ultimos 12 e devolve metricas + previsoes do teste."""
    s = s.reset_index(drop=True).copy(); s['t'] = np.arange(len(s))
    treino, teste = s.iloc[:-TESTE_MESES], s.iloc[-TESTE_MESES:]
    m = LinearRegression().fit(treino[['t']], treino.valor_descontado)
    p = m.predict(teste[['t']])
    base = np.repeat(treino.valor_descontado.iloc[-1], len(teste))  # baseline ingenuo: repete o ultimo mes
    return {'modelo': nome, 'inicio': s.mes.iloc[0], 'fim': s.mes.iloc[-1], 'meses_treino': len(treino),
            'meses_teste': len(teste), 'MAE': round(mean_absolute_error(teste.valor_descontado, p), 2),
            'RMSE': round(float(np.sqrt(mean_squared_error(teste.valor_descontado, p))), 2),
            'MAPE_%': round(mape(teste.valor_descontado.values, p), 2),
            'MAPE_baseline_%': round(mape(teste.valor_descontado.values, base), 2),
            'coef_mensal': round(float(m.coef_[0]), 2)}, p

def previsao(serie):
    s = serie[(serie.mes >= JANELA[0]) & (serie.mes <= JANELA[1])].reset_index(drop=True)
    # Modelo 1 (planejado na Fase 1): tendencia linear na janela completa 2020-2025
    m1, p1 = avaliar(s, 'Janela completa (2020-01 a 2025-03)')
    # Modelo 2: regime atual - comeca no ponto minimo da serie entre 2021 e 2023 (inversao da tendencia)
    meio = s[(s.mes >= '2021-01') & (s.mes <= '2023-12')]
    inicio_regime = meio.loc[meio.valor_descontado.idxmin(), 'mes']
    r = s[s.mes >= inicio_regime].reset_index(drop=True)
    m2, p2 = avaliar(r, f'Regime atual ({inicio_regime} a 2025-03)')
    met = {'modelo_janela_completa': m1, 'modelo_regime_atual': m2, 'inicio_regime': inicio_regime,
           'H2_janela_completa': m1['MAPE_%'] < 15, 'H2_regime_atual': m2['MAPE_%'] < 15}
    # modelo final (regime atual, todos os meses) -> proximos 12 meses com intervalo de 95%
    r['t'] = np.arange(len(r))
    mf = LinearRegression().fit(r[['t']], r.valor_descontado)
    sd = float((r.valor_descontado - mf.predict(r[['t']])).std())
    fut_t = np.arange(len(r), len(r) + HORIZONTE)
    meses = pd.period_range(pd.Period(JANELA[1], 'M') + 1, periods=HORIZONTE, freq='M').astype(str)
    fut = pd.DataFrame({'mes': meses, 'previsto': mf.predict(pd.DataFrame({'t': fut_t}))})
    fut['limite_inf'] = fut.previsto - 1.96 * sd
    fut['limite_sup'] = fut.previsto + 1.96 * sd
    hist = s[['mes', 'valor_descontado']].copy()
    hist['teste_janela_completa'] = np.nan; hist.loc[hist.index[-TESTE_MESES:], 'teste_janela_completa'] = p1
    hist['teste_regime_atual'] = np.nan; hist.loc[hist.index[-TESTE_MESES:], 'teste_regime_atual'] = p2
    met['previsao_total_12m'] = round(float(fut.previsto.sum()), 2)
    met['previsao_media_mensal'] = round(float(fut.previsto.mean()), 2)
    met['crescimento_mensal_regime'] = round(float(mf.coef_[0]), 2)
    return met, hist, fut

if __name__ == '__main__':
    d = pathlib.Path(sys.argv[1])
    fato = pd.read_csv(d / 'fato_consignacao.csv')
    cli = pd.read_csv(d / 'dim_cliente.csv')
    serie = pd.read_csv(d / 'serie_mensal.csv')
    k = kpis(fato, cli)
    met, hist, fut = previsao(serie)
    json.dump(k, open(d / 'kpis.json', 'w'), ensure_ascii=False, indent=2)
    json.dump(met, open(d / 'metricas_h2.json', 'w'), ensure_ascii=False, indent=2)
    hist.to_csv(d / 'serie_ajustada.csv', index=False)
    fut.to_csv(d / 'previsao.csv', index=False)
    print(json.dumps(k, ensure_ascii=False, indent=1)); print(json.dumps(met, ensure_ascii=False, indent=1))
