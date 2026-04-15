import sqlite3

def criar_banco_mock():
    conn = sqlite3.connect('operacoes.db')
    cursor = conn.cursor()


#Criacao de tabelas 
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome_empresa TEXT NOT NULL,
            status TEXT NOT NULL,
            saldo_devedor REAL,
            data_ultima_compra TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chamados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER,
            assunto TEXT,
            prioridade TEXT,
            status TEXT,
            FOREIGN KEY(cliente_id) REFERENCES clientes(id)
        )
    ''')

    cursor.execute('DELETE FROM chamados')
    cursor.execute('DELETE FROM clientes')


#Mock dos dados
    clientes = [
        ('AgroTech Sul', 'Ativo', 0.0, '2026-04-10'),
        ('Fazenda Boa Vista', 'Inadimplente', 15430.50, '2026-03-15'),
        ('Comercial Santos', 'Ativo', 250.0, '2026-04-14'),
        ('Distribuidora Vale', 'Ativo', 0.0, '2026-02-20')
    ]
    cursor.executemany('INSERT INTO clientes (nome_empresa, status, saldo_devedor, data_ultima_compra) VALUES (?, ?, ?, ?)', clientes)

    chamados = [
        (1, 'Erro na emissão de nota', 'Alta', 'Aberto'),
        (2, 'Dúvida sobre fatura', 'Baixa', 'Resolvido'),
        (2, 'Atraso na entrega', 'Alta', 'Aberto'),
        (4, 'Atualização de cadastro', 'Média', 'Aberto')
    ]
    cursor.executemany('INSERT INTO chamados (cliente_id, assunto, prioridade, status) VALUES (?, ?, ?, ?)', chamados)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    criar_banco_mock()