"""Etapa 3 - Limpeza, identificacao de seguros/peculios e modelo dimensional.
Uso: python preparar.py <consignacoes_anonimas.csv> <pasta_saida>
Saidas: fato_consignacao.csv, dim_cliente.csv, dim_entidade.csv, serie_mensal.csv
"""
import sys, pathlib, re
import pandas as pd

def categoria(servico, entidade):
    s = f'{servico} {entidade}'.upper()
    if 'ASSIST' in s and 'JURID' in s: return 'Assistência jurídica'
    if 'DECESSO' in s or 'FUNERAL' in s: return 'Seguro funeral'
    if 'PECULIO' in s or 'PECÚLIO' in s: return 'Pecúlio'
    if 'SEG' in s: return 'Seguro'
    if 'PREV' in s or 'P N DED' in s or 'P DEDUT' in s or 'PN DED' in s or 'P ND' in s or 'P PRIVADA' in s: return 'Previdência/pecúlio'
    return 'Outros (prazo indeterminado)'

def entidade_padrao(e):
    e = re.sub(r'\s+', ' ', str(e).upper()).strip()
    for chave, nome in [('SABEMI', 'SABEMI'), ('FUTURO', 'FUTURO PREVIDÊNCIA'), ('POUPEX', 'POUPEX/FHE'), ('FHE', 'POUPEX/FHE'),
                        ('GBOEX', 'GBOEX'), ('HOJE', 'HOJE PREVIDÊNCIA'), ('PREVIMIL', 'PREVIMIL'), ('KOVR', 'KOVR'),
                        ('MONGERAL', 'MONGERAL'), ('MBM', 'MBM PREVIDÊNCIA'), ('UNIÃO SEG', 'UNIÃO SEGURADORA'),
                        ('UNIAO SEG', 'UNIÃO SEGURADORA'), ('CIASPREV', 'CIASPREV'), ('JAIRO', 'ASSOCIAÇÃO JURÍDICA (JC)'),
                        ('DAYCOVAL', 'BANCO DAYCOVAL'), ('INBURSA', 'BANCO INBURSA'), ('BANCO DO BRASIL', 'BANCO DO BRASIL'),
                        ('MASTER', 'BANCO MASTER'), ('BRADESCO', 'BRADESCO'), ('ITAU', 'ITAÚ'), ('ITAÚ', 'ITAÚ'),
                        ('SANTANDER', 'SANTANDER'), ('CAIXA', 'CAIXA'), ('BMG', 'BMG'), ('PAN', 'BANCO PAN')]:
        if chave in e: return nome
    return re.sub(r'^\S+\s*-\s*', '', e)[:40]

if __name__ == '__main__':
    d = pd.read_csv(sys.argv[1], dtype=str)
    out = pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    for c in ['data_inclusao', 'data_situacao', 'data_carga', 'data_emissao']:
        d[c] = pd.to_datetime(d[c], format='%d/%m/%Y', errors='coerce')
    d['data_carga'] = d['data_carga'].fillna(d['data_emissao'])
    for c in ['valor_prestacao', 'valor_folha', 'margem']:
        d[c] = pd.to_numeric(d[c], errors='coerce')
    d['pagas'] = pd.to_numeric(d['pagas']).astype(int)
    antes = len(d)
    # mesma consignacao (cliente + ADE) aparece em mais de um extrato: fica a versao mais recente
    d = d.sort_values('data_emissao').drop_duplicates(['cliente_id', 'ade'], keep='last')
    print(f'Duplicadas removidas: {antes - len(d)}')
    cob_path = out / 'cobertura.json'
    if cob_path.exists():
        import json
        cob = json.load(open(cob_path))
        cob.update({'duplicadas_entre_extratos': antes - len(d), 'consignacoes_finais': len(d), 'clientes': int(d.cliente_id.nunique())})
        json.dump(cob, open(cob_path, 'w'), indent=2)
    d['prazo_indeterminado'] = d['n_prestacoes'].str.startswith('Indet')
    d['entidade_padrao'] = d['entidade'].map(entidade_padrao)
    d['tipo'] = d['prazo_indeterminado'].map({True: 'Seguro/pecúlio (prazo indeterminado)', False: 'Empréstimo/cartão'})
    d['categoria'] = [categoria(s, e) if ind else 'Empréstimo/cartão' for s, e, ind in zip(d.servico, d.entidade, d.prazo_indeterminado)]
    # regra da empresa: pecúlio POUPEX/FHE abaixo de R$ 8,00 nao entra
    excecao = (d.entidade_padrao == 'POUPEX/FHE') & (d.valor_prestacao < 8)
    d['potencial_indevido'] = d.prazo_indeterminado & ~excecao & (d.pagas > 0)
    d['ativo'] = d['situacao'].eq('Em Andamento')
    d['total_pago'] = d['valor_prestacao'] * d['pagas']
    # ultimo mes descontado: data da carga (se ativa) ou data da situacao (liquidada/cancelada)
    fim = d['data_carga'].where(d['ativo'], d['data_situacao'].fillna(d['data_carga']))
    d['fim_desconto'] = fim.dt.to_period('M')
    d['inicio_desconto'] = d['fim_desconto'] - (d['pagas'] - 1).clip(lower=0)
    d['ano_inclusao'] = d['data_inclusao'].dt.year
    fato = d[['cliente_id', 'documento_id', 'ade', 'entidade_padrao', 'cod_entidade', 'servico', 'tipo', 'categoria',
              'data_inclusao', 'inicio_desconto', 'fim_desconto', 'ano_inclusao', 'valor_prestacao', 'valor_folha', 'n_prestacoes', 'pagas',
              'total_pago', 'situacao', 'data_situacao', 'ativo', 'prazo_indeterminado', 'potencial_indevido', 'data_carga']]
    fato.to_csv(out / 'fato_consignacao.csv', index=False)
    g = d.groupby('cliente_id')
    dim_cli = pd.DataFrame({
        'n_consignacoes': g.size(),
        'n_ativas': g['ativo'].sum(),
        'n_entidades': g['entidade_padrao'].nunique(),
        'valor_mensal_total_ativo': d[d.ativo].groupby('cliente_id')['valor_prestacao'].sum(),
        'margem_disponivel': g['margem'].min(),
        'data_carga': g['data_carga'].max(),
        'n_seguros_indevidos': g['potencial_indevido'].sum(),
        'valor_mensal_indevido_ativo': d[d.ativo & d.potencial_indevido].groupby('cliente_id')['valor_prestacao'].sum(),
        'total_pago_indevido': d[d.potencial_indevido].groupby('cliente_id')['total_pago'].sum(),
    }).fillna({'valor_mensal_total_ativo': 0, 'valor_mensal_indevido_ativo': 0, 'total_pago_indevido': 0})
    dim_cli['tem_desconto_indevido'] = dim_cli['n_seguros_indevidos'] > 0
    dim_cli.reset_index().to_csv(out / 'dim_cliente.csv', index=False)
    ent = d.groupby('entidade_padrao').agg(n_consignacoes=('ade', 'size'), n_indevidas=('potencial_indevido', 'sum'),
                                           n_clientes=('cliente_id', 'nunique')).reset_index()
    ent.to_csv(out / 'dim_entidade.csv', index=False)
    # serie mensal: cada parcela paga de seguro/peculio vira um mes de desconto, contando para tras a partir do ultimo mes descontado
    linhas = []
    for r in d[d.potencial_indevido].itertuples():
        for k in range(r.pagas):
            linhas.append((r.inicio_desconto + k, r.cliente_id, r.valor_prestacao))
    s = pd.DataFrame(linhas, columns=['mes', 'cliente_id', 'valor'])
    serie = s.groupby('mes').agg(valor_descontado=('valor', 'sum'), clientes_com_desconto=('cliente_id', 'nunique'),
                                 parcelas=('valor', 'size')).reset_index()
    serie['mes'] = serie['mes'].astype(str)
    serie.to_csv(out / 'serie_mensal.csv', index=False)
    print(f'{len(fato)} consignacoes | {d.cliente_id.nunique()} clientes | {int(d.potencial_indevido.sum())} seguros/peculios | serie {serie.mes.min()}..{serie.mes.max()}')
