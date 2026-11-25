"""Etapa 5 - Gera o painel interativo (docs/index.html) publicado no GitHub Pages.
Uso: python gerar_dashboard.py <pasta_dados> <saida.html>
"""
import sys, json, pathlib
import pandas as pd

d = pathlib.Path(sys.argv[1])
fato = pd.read_csv(d / 'fato_consignacao.csv')
cli = pd.read_csv(d / 'dim_cliente.csv')
serie = pd.read_csv(d / 'serie_mensal.csv')
ajuste = pd.read_csv(d / 'serie_ajustada.csv')
prev = pd.read_csv(d / 'previsao.csv')
val = pd.read_csv(d / 'validacao_h1.csv')
kpis = json.load(open(d / 'kpis.json'))
met = json.load(open(d / 'metricas_h2.json'))
cob = json.load(open(d / 'cobertura.json'))

ind = fato[fato.potencial_indevido][['cliente_id', 'entidade_padrao', 'categoria', 'valor_prestacao', 'pagas',
                                      'total_pago', 'situacao', 'ativo', 'ano_inclusao']]
dados = {
    'ind': ind.to_dict(orient='records'),
    'cli': cli[['cliente_id', 'n_ativas', 'n_entidades', 'n_seguros_indevidos', 'valor_mensal_indevido_ativo',
                'total_pago_indevido', 'tem_desconto_indevido']].to_dict(orient='records'),
    'serie': serie[serie.mes >= '2015-01'].to_dict(orient='records'),
    'ajuste': ajuste.where(ajuste.notna(), None).to_dict(orient='records'),
    'prev': prev.to_dict(orient='records'),
    'val': val.to_dict(orient='records'),
    'kpis': kpis, 'met': met, 'cob': cob,
    'n_total': int(len(fato)),
}
html = (pathlib.Path(__file__).parent / 'dashboard_template.html').read_text(encoding='utf-8')
html = html.replace('/*__DADOS__*/null', json.dumps(dados, ensure_ascii=False, default=str))
pathlib.Path(sys.argv[2]).parent.mkdir(parents=True, exist_ok=True)
pathlib.Path(sys.argv[2]).write_text(html, encoding='utf-8')
print('painel gerado em', sys.argv[2])
