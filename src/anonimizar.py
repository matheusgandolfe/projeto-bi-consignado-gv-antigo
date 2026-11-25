"""Etapa 2 - Anonimizacao (LGPD).
Troca nome, CPF, matricula e numero do contrato (ADE) por um codigo irreversivel (hash SHA-256 com chave secreta).
Uso: SALT=<chave_secreta> python anonimizar.py <entrada_bruta.csv> <saida_anonima.csv>
A chave (SALT) fica fora do repositorio; sem ela nao da para refazer o vinculo codigo -> pessoa.
"""
import os, sys, hashlib
import pandas as pd

def codigo(cpf, salt):
    return 'CLI-' + hashlib.sha256((salt + str(cpf)).encode()).hexdigest()[:8].upper()

if __name__ == '__main__':
    salt = os.environ.get('SALT')
    if not salt:
        sys.exit('Defina a variavel de ambiente SALT (chave secreta).')
    d = pd.read_csv(sys.argv[1], dtype=str)
    d.insert(0, 'cliente_id', d['cpf'].map(lambda c: codigo(c, salt)))
    d['documento_id'] = d['arquivo_md5'].map(lambda h: 'DOC-' + hashlib.sha256((salt + h).encode()).hexdigest()[:8].upper())
    # numero do contrato (ADE) tambem vira codigo, para nao permitir busca no sistema da consignataria
    d['ade'] = d['ade'].map(lambda a: 'ADE-' + hashlib.sha256((salt + str(a)).encode()).hexdigest()[:10].upper())
    d = d.drop(columns=['nome', 'cpf', 'matricula', 'arquivo_md5'])
    d.to_csv(sys.argv[2], index=False)
    print(f'{len(d)} linhas, {d.cliente_id.nunique()} clientes anonimizados -> {sys.argv[2]}')
