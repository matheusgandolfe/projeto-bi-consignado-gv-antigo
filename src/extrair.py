"""Etapa 1 - Leitura dos extratos de consignacao (eConsig) em PDF.
Uso: python extrair.py <pasta_pdfs> <saida.csv> [cobertura.json]
Gera uma linha por consignacao, ainda COM dados pessoais (arquivo privado,
nunca versionado). A anonimizacao acontece na etapa 2 (anonimizar.py).
"""
import re, sys, hashlib, subprocess, pathlib, csv

RE_CLIENTE = re.compile(r'(\d{9,10})\s+-\s+(\d{3}\.\d{3}\.\d{3}-\d{2})\s+-\s+(.+?)(?:\s{2,}|$)')
RE_CARGA   = re.compile(r'DATA DA CARGA DAS\s+MARGENS:\s*(\d{2}/\d{2}/\d{4})', re.S)
RE_EMISSAO = re.compile(r'(\d{2}/\d{2}/\d{4}),?\s+\d{2}:\d{2}:\d{2}\s+BRT')
RE_MARGEM  = re.compile(r'(?:MARGEM CONSIGNACAO|Margem Limite 70%)\s*\n\s*R\$\s*(-?[\d\.]+,\d{2})', re.I)
RE_LINHA = re.compile(
    r'^\s*(?P<cod>[A-Z0-9]{3})\s+-\s+(?P<ent>.*?)\s+(?P<ade>\d{6,10})\s+(?P<serv>.*?)\s*'
    r'(?P<incl>\d{2}/\d{2}/\d{4})\s+(?P<vp>R\$(?:\s*[\d\.]+,\d{2})?)\s+(?P<vf>R\$(?:\s*[\d\.]+,\d{2})?|-)\s+'
    r'(?P<nprest>\d+|Indet\.?)\s+(?P<pagas>\d+)\s+(?P<sit>.+?)\s*(?:Visualizar)?\s*$')
RE_DATA_SIT = re.compile(r'\((\d{2}/\d{2}/\d{4})')

def texto(pdf):
    return subprocess.run(['pdftotext', '-layout', str(pdf), '-'], capture_output=True, text=True).stdout

def valor(s):
    if s is None or s.strip() in ('-', 'R$', ''):
        return None
    return float(s.replace('R$', '').strip().replace('.', '').replace(',', '.'))

def ler_pdf(pdf):
    t = texto(pdf)
    linhas = t.splitlines()
    cli = RE_CLIENTE.search(t)
    carga = RE_CARGA.search(t)
    emis = RE_EMISSAO.search(t)
    marg = RE_MARGEM.search(t)
    cab = dict(
        arquivo_md5=hashlib.md5(pathlib.Path(pdf).read_bytes()).hexdigest(),
        matricula=cli.group(1) if cli else None,
        cpf=cli.group(2) if cli else None,
        nome=cli.group(3).strip() if cli else None,
        data_carga=carga.group(1) if carga else None,
        data_emissao=emis.group(1) if emis else (carga.group(1) if carga else None),
        margem=valor(marg.group(1)) if marg else None,
    )
    regs, falhas = [], []
    i = 0
    while i < len(linhas):
        ln = linhas[i]
        m = RE_LINHA.match(ln)
        if m:
            ent0, ade0, serv0 = m.group('ent'), m.group('ade'), m.group('serv')
            if re.fullmatch(r'\d{6,10}', ent0.strip()):
                # nome da entidade so nas linhas de baixo: o 1o numero e o ADE e o 2o ja e o codigo do servico
                ent0, ade0, serv0 = '', ent0.strip(), ade0 + ' ' + serv0
            # bloco = linha principal + continuacoes ate a linha em branco
            bloco = [ln]
            j = i + 1
            while j < len(linhas) and linhas[j].strip() and not RE_LINHA.match(linhas[j]):
                bloco.append(linhas[j]); j += 1
            # texto das colunas de continuacao (entidade/servico) pelas posicoes da linha principal
            pos_ade = ln.index(ade0)
            pos_incl = ln.index(m.group('incl'))
            ent_cont = ' '.join(b[:pos_ade].strip() for b in bloco[1:] if b[:pos_ade].strip())
            serv_cont = ' '.join(b[pos_ade:pos_incl].strip() for b in bloco[1:] if b[pos_ade:pos_incl].strip())
            sit_full = ' '.join([m.group('sit')] + [b[pos_incl:].strip() for b in bloco[1:]])
            ds = RE_DATA_SIT.search(sit_full)
            sit = re.sub(r'\(.*', '', sit_full)
            sit = re.sub(r'\d{2}:\d{2}:\d{2}', '', sit)
            sit = re.sub(r'[\d\.]+,\d{2}|\d{2}:\d{2}(:\d{2})?', '', sit)
            sit = re.sub(r'\s+', ' ', sit).strip()
            for nome_sit in ('Em Andamento', 'Liquidada', 'Deferida', 'Cancelada', 'Concluído', 'Suspensa', 'Aguard'):
                if sit.startswith(nome_sit.split()[0]):
                    sit = nome_sit; break
            serv = (serv0 + ' ' + re.sub(r'^\d{2}:\d{2}:\d{2}\s*', '', serv_cont)).strip()
            serv = re.sub(r'\d{2}:\d{2}:\d{2}', '', serv)
            vp, vf = valor(m.group('vp')), valor(m.group('vf'))
            if vp is None or (vf is None and m.group('vf').strip() != '-'):
                nums = []
                for b in bloco[1:]:
                    nums += re.findall(r'(?<![\d:/])(\d[\d\.]*,\d{2})(?![\d:/])', b[pos_incl:])
                nums = [valor(n) for n in nums]
                if vp is None and nums: vp = nums.pop(0)
                if vf is None and m.group('vf').strip() != '-' and nums: vf = nums.pop(0)
            regs.append(dict(cab,
                cod_entidade=m.group('cod'),
                entidade=re.sub(r'\s+', ' ', (ent0 + ' ' + ent_cont)).strip(),
                ade=ade0,
                servico=re.sub(r'\s+', ' ', serv).strip(),
                data_inclusao=m.group('incl'),
                valor_prestacao=vp,
                valor_folha=vf,
                n_prestacoes=m.group('nprest'),
                pagas=int(m.group('pagas')),
                situacao=sit,
                data_situacao=ds.group(1) if ds else None))
            i = j
        else:
            if re.match(r'^\s*[A-Z0-9]{3}\s+-\s+\S', ln) and 'R$' in ln:
                falhas.append(ln)
            i += 1
    return cab, regs, falhas

if __name__ == '__main__':
    pasta, saida = pathlib.Path(sys.argv[1]), sys.argv[2]
    todos, vistos, sem_texto, arquivos = [], set(), 0, 0
    for pdf in sorted(pasta.glob('*.pdf')):
        arquivos += 1
        cab, regs, falhas = ler_pdf(pdf)
        if cab['arquivo_md5'] in vistos:
            print('DUPLICADO ignorado:', pdf.name); continue
        vistos.add(cab['arquivo_md5'])
        if not regs and not cab['cpf']:
            sem_texto += 1   # PDF escaneado (imagem): fica fora e entra como limitacao
        print(f"{pdf.name}: {len(regs)} consignacoes, {len(falhas)} falhas, cliente={'ok' if cab['cpf'] else 'NAO ACHOU'}")
        for f in falhas: print('   FALHA:', f.strip()[:150])
        todos += regs
    with open(saida, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(todos[0].keys()))
        w.writeheader(); w.writerows(todos)
    print('TOTAL', len(todos))
    if len(sys.argv) > 3:
        import json
        unicos = len(vistos)
        json.dump({'arquivos_encontrados': arquivos, 'duplicados': arquivos - unicos, 'arquivos_unicos': unicos,
                   'lidos_texto': unicos - sem_texto, 'imagem_sem_texto': sem_texto,
                   'pct_lidos': round(100 * (unicos - sem_texto) / unicos, 1), 'linhas_extraidas': len(todos)},
                  open(sys.argv[3], 'w'), indent=2)
