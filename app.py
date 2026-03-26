from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import os, psycopg2, psycopg2.extras, logging
from datetime import datetime, timedelta, timezone

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
)

app = Flask(__name__, static_folder='static')
CORS(app)

# Fuso horário de Brasília (UTC-3)
BRASILIA = timezone(timedelta(hours=-3))

def agora():
    return datetime.now(BRASILIA).strftime('%Y-%m-%d %H:%M:%S')

def get_db():
    """Abre conexão com PostgreSQL usando a variável DATABASE_URL do Railway."""
    url = os.environ.get('DATABASE_URL', '')
    # Railway usa postgres://, psycopg2 precisa de postgresql://
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)
    conn = psycopg2.connect(url)
    return conn

def q(conn, sql, params=()):
    """Executa uma query e retorna os resultados como lista de dicts."""
    # Converte ? (SQLite) para %s (PostgreSQL)
    sql = sql.replace('?', '%s')
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        try:
            return cur.fetchall()
        except Exception:
            return []

def qone(conn, sql, params=()):
    rows = q(conn, sql, params)
    return rows[0] if rows else None

def exe(conn, sql, params=()):
    """Executa INSERT/UPDATE/DELETE, retorna o id gerado em INSERTs ou None."""
    sql = sql.replace('?', '%s')
    is_write = sql.strip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))
    # PostgreSQL: usa RETURNING id para obter o id gerado pelo INSERT
    if sql.strip().upper().startswith('INSERT') and 'RETURNING' not in sql.upper():
        sql = sql + ' RETURNING id'
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            result = None
            if sql.strip().upper().startswith('INSERT'):
                row = cur.fetchone()
                result = row[0] if row else None
        if is_write:
            conn.commit()
        return result
    except Exception as e:
        logging.error('exe() falhou — sql: %s | params: %s | erro: %s', sql, params, e)
        conn.rollback()
        return None

def init_db():
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS produtos (
                id SERIAL PRIMARY KEY,
                nome TEXT NOT NULL,
                categoria TEXT,
                preco REAL NOT NULL,
                emoji TEXT DEFAULT '🌽',
                ativo INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS vendas (
                id SERIAL PRIMARY KEY,
                total REAL NOT NULL,
                desconto REAL DEFAULT 0,
                forma_pagamento TEXT DEFAULT 'dinheiro',
                criado_em TEXT
            );

            CREATE TABLE IF NOT EXISTS itens_venda (
                id SERIAL PRIMARY KEY,
                venda_id INTEGER,
                produto_id INTEGER,
                nome_produto TEXT,
                quantidade INTEGER NOT NULL,
                preco_unit REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS caixa (
                id SERIAL PRIMARY KEY,
                tipo TEXT NOT NULL,
                descricao TEXT,
                valor REAL NOT NULL,
                data TEXT
            );

            CREATE TABLE IF NOT EXISTS turno (
                id SERIAL PRIMARY KEY,
                tipo TEXT NOT NULL,
                valor_informado REAL DEFAULT 0,
                observacao TEXT,
                data TEXT
            );

            CREATE TABLE IF NOT EXISTS fornecedores (
                id SERIAL PRIMARY KEY,
                nome TEXT NOT NULL,
                telefone TEXT,
                ativo INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS compras (
                id SERIAL PRIMARY KEY,
                fornecedor_id INTEGER,
                fornecedor_nome TEXT,
                descricao TEXT NOT NULL,
                quantidade REAL DEFAULT 1,
                unidade TEXT DEFAULT 'un',
                valor_unit REAL NOT NULL,
                valor_total REAL NOT NULL,
                pago INTEGER DEFAULT 0,
                data TEXT
            );
        ''')
    conn.commit()
    conn.close()

# ── PRODUTOS ──────────────────────────────────────────────────
@app.route('/api/produtos', methods=['GET'])
def get_produtos():
    conn = get_db()
    rows = q(conn, 'SELECT * FROM produtos WHERE ativo=1 ORDER BY categoria, nome')
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/produtos/todos', methods=['GET'])
def get_todos_produtos():
    conn = get_db()
    rows = q(conn, 'SELECT * FROM produtos ORDER BY categoria, nome')
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/produtos', methods=['POST'])
def add_produto():
    d = request.json
    conn = get_db()
    exe(conn, 'INSERT INTO produtos (nome, categoria, preco, emoji) VALUES (?,?,?,?)',
        (d['nome'], d.get('categoria',''), d['preco'], d.get('emoji','🌽')))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/produtos/<int:id>', methods=['PUT'])
def update_produto(id):
    d = request.json
    conn = get_db()
    exe(conn, 'UPDATE produtos SET nome=?, categoria=?, preco=?, emoji=?, ativo=? WHERE id=?',
        (d['nome'], d.get('categoria',''), d['preco'], d.get('emoji','🌽'), d.get('ativo',1), id))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/produtos/<int:id>', methods=['DELETE'])
def delete_produto(id):
    conn = get_db()
    exe(conn, 'UPDATE produtos SET ativo=0 WHERE id=?', (id,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ── VENDAS ────────────────────────────────────────────────────
@app.route('/api/vendas', methods=['POST'])
def registrar_venda():
    d = request.json
    conn = get_db()
    now = agora()
    vid = exe(conn, 'INSERT INTO vendas (total, desconto, forma_pagamento, criado_em) VALUES (?,?,?,?)',
              (d['total'], d.get('desconto', 0), d.get('forma_pagamento', 'dinheiro'), now))
    for item in d.get('itens', []):
        exe(conn, 'INSERT INTO itens_venda (venda_id, produto_id, nome_produto, quantidade, preco_unit) VALUES (?,?,?,?,?)',
            (vid, item.get('produto_id'), item['nome_produto'], item['quantidade'], item['preco_unit']))
    exe(conn, 'INSERT INTO caixa (tipo, descricao, valor, data) VALUES (?,?,?,?)',
        ('entrada', f'Venda #{vid}', d['total'], now))
    conn.commit(); conn.close()
    return jsonify({'ok': True, 'id': vid})

@app.route('/api/vendas', methods=['GET'])
def get_vendas():
    conn = get_db()
    rows = q(conn, 'SELECT * FROM vendas ORDER BY criado_em DESC LIMIT 100')
    conn.close()
    return jsonify([dict(r) for r in rows])

# ── DASHBOARD ─────────────────────────────────────────────────
@app.route('/api/dashboard')
def dashboard():
    conn = get_db()
    hoje      = datetime.now(BRASILIA).strftime('%Y-%m-%d')
    mes       = datetime.now(BRASILIA).strftime('%Y-%m')
    sete_dias = (datetime.now(BRASILIA) - timedelta(days=7)).strftime('%Y-%m-%d')

    # PostgreSQL usa TO_CHAR e DATE() em vez de strftime
    vendas_hoje = qone(conn,
        "SELECT COUNT(*) as c, COALESCE(SUM(total),0) as s FROM vendas WHERE criado_em::date = ?::date", (hoje,))
    vendas_mes = qone(conn,
        "SELECT COUNT(*) as c, COALESCE(SUM(total),0) as s FROM vendas WHERE TO_CHAR(criado_em::date,'YYYY-MM') = ?", (mes,))
    por_forma = q(conn,
        "SELECT forma_pagamento, COUNT(*) as qtd, SUM(total) as total FROM vendas WHERE TO_CHAR(criado_em::date,'YYYY-MM') = ? GROUP BY forma_pagamento", (mes,))
    por_dia = q(conn,
        "SELECT criado_em::date as dia, COUNT(*) as vendas, SUM(total) as total FROM vendas WHERE criado_em::date >= ?::date GROUP BY criado_em::date ORDER BY criado_em::date", (sete_dias,))
    por_hora = q(conn,
        "SELECT TO_CHAR(criado_em::timestamp,'HH24') as hora, COUNT(*) as qtd, SUM(total) as total FROM vendas WHERE criado_em::date = ?::date GROUP BY hora ORDER BY hora", (hoje,))
    ticket_row = qone(conn,
        "SELECT AVG(total) as avg FROM vendas WHERE TO_CHAR(criado_em::date,'YYYY-MM') = ?", (mes,))
    recentes = q(conn, 'SELECT * FROM vendas ORDER BY criado_em DESC LIMIT 8')
    conn.close()

    ticket = ticket_row['avg'] if ticket_row and ticket_row['avg'] else 0

    return jsonify({
        'hoje': {'qtd': vendas_hoje['c'], 'total': round(float(vendas_hoje['s']), 2)},
        'mes':  {'qtd': vendas_mes['c'],  'total': round(float(vendas_mes['s']),  2)},
        'ticket_medio': round(float(ticket), 2),
        'por_forma': [dict(r) for r in por_forma],
        'por_dia':   [{'dia': str(r['dia']), 'vendas': r['vendas'], 'total': float(r['total'])} for r in por_dia],
        'por_hora':  [dict(r) for r in por_hora],
        'recentes':  [dict(r) for r in recentes],
    })

# ── CAIXA ─────────────────────────────────────────────────────
@app.route('/api/caixa', methods=['GET'])
def get_caixa():
    conn = get_db()
    hoje = datetime.now(BRASILIA).strftime('%Y-%m-%d')
    rows = q(conn, "SELECT * FROM caixa WHERE data::date = ?::date ORDER BY data DESC", (hoje,))
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/caixa', methods=['POST'])
def add_caixa():
    d = request.json
    conn = get_db()
    exe(conn, 'INSERT INTO caixa (tipo, descricao, valor, data) VALUES (?,?,?,?)',
        (d['tipo'], d.get('descricao',''), d['valor'], agora()))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ── TURNO ─────────────────────────────────────────────────────
@app.route('/api/turno/status', methods=['GET'])
def turno_status():
    conn = get_db()
    hoje = datetime.now(BRASILIA).strftime('%Y-%m-%d')
    ultimo = qone(conn,
        "SELECT * FROM turno WHERE data::date = ?::date ORDER BY id DESC LIMIT 1", (hoje,))
    vendas_turno = qone(conn,
        "SELECT COUNT(*) as c, COALESCE(SUM(total),0) as s FROM vendas WHERE criado_em::date = ?::date", (hoje,))
    sang_row = qone(conn,
        "SELECT COALESCE(SUM(valor),0) as s FROM caixa WHERE tipo='sangria' AND data::date = ?::date", (hoje,))
    conn.close()
    aberto = ultimo and ultimo['tipo'] == 'abertura'
    return jsonify({
        'aberto': aberto,
        'ultimo_turno': dict(ultimo) if ultimo else None,
        'vendas_turno': {'qtd': vendas_turno['c'], 'total': round(float(vendas_turno['s']), 2)},
        'sangrias': round(float(sang_row['s']), 2),
    })

@app.route('/api/turno/abrir', methods=['POST'])
def abrir_turno():
    d = request.json or {}
    conn = get_db()
    hoje = datetime.now(BRASILIA).strftime('%Y-%m-%d')
    ultimo = qone(conn,
        "SELECT * FROM turno WHERE data::date = ?::date ORDER BY id DESC LIMIT 1", (hoje,))
    if ultimo and ultimo['tipo'] == 'abertura':
        conn.close()
        return jsonify({'ok': False, 'erro': 'Turno já está aberto.'}), 400
    valor = d.get('valor_informado', 0)
    obs   = d.get('observacao', '')
    now   = agora()
    exe(conn, 'INSERT INTO turno (tipo, valor_informado, observacao, data) VALUES (?,?,?,?)',
        ('abertura', valor, obs, now))
    exe(conn, 'INSERT INTO caixa (tipo, descricao, valor, data) VALUES (?,?,?,?)',
        ('abertura', f'Abertura de caixa — Fundo: R$ {valor:.2f}', valor, now))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/turno/fechar', methods=['POST'])
def fechar_turno():
    d = request.json or {}
    conn = get_db()
    hoje = datetime.now(BRASILIA).strftime('%Y-%m-%d')
    ultimo = qone(conn,
        "SELECT * FROM turno WHERE data::date = ?::date ORDER BY id DESC LIMIT 1", (hoje,))
    if not ultimo or ultimo['tipo'] != 'abertura':
        conn.close()
        return jsonify({'ok': False, 'erro': 'Nenhum turno aberto para fechar.'}), 400
    valor_informado = d.get('valor_informado', 0)
    obs = d.get('observacao', '')
    fundo    = float(qone(conn, "SELECT COALESCE(SUM(valor),0) as s FROM caixa WHERE tipo='abertura' AND data::date=?::date", (hoje,))['s'])
    vendas   = float(qone(conn, "SELECT COALESCE(SUM(total),0) as s FROM vendas WHERE criado_em::date=?::date", (hoje,))['s'])
    sangrias = float(qone(conn, "SELECT COALESCE(SUM(valor),0) as s FROM caixa WHERE tipo='sangria' AND data::date=?::date", (hoje,))['s'])
    esperado  = fundo + vendas - sangrias
    diferenca = valor_informado - esperado
    now = agora()
    exe(conn, 'INSERT INTO turno (tipo, valor_informado, observacao, data) VALUES (?,?,?,?)',
        ('fechamento', valor_informado, obs, now))
    exe(conn, 'INSERT INTO caixa (tipo, descricao, valor, data) VALUES (?,?,?,?)',
        ('fechamento', f'Fechamento — Contado: R$ {valor_informado:.2f} | Esperado: R$ {esperado:.2f} | Diferença: R$ {diferenca:.2f}', valor_informado, now))
    conn.commit(); conn.close()
    return jsonify({'ok': True, 'esperado': round(esperado,2), 'contado': round(valor_informado,2), 'diferenca': round(diferenca,2)})

@app.route('/api/turno/sangria', methods=['POST'])
def sangria():
    d = request.json or {}
    valor = d.get('valor', 0)
    obs   = d.get('observacao', 'Sangria')
    if valor <= 0:
        return jsonify({'ok': False, 'erro': 'Valor inválido'}), 400
    conn = get_db()
    exe(conn, 'INSERT INTO caixa (tipo, descricao, valor, data) VALUES (?,?,?,?)',
        ('sangria', obs, valor, agora()))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ── FORNECEDORES ───────────────────────────────────────────────
@app.route('/api/fornecedores', methods=['GET'])
def get_fornecedores():
    conn = get_db()
    rows = q(conn, 'SELECT * FROM fornecedores WHERE ativo=1 ORDER BY nome')
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/fornecedores', methods=['POST'])
def add_fornecedor():
    d = request.json
    conn = get_db()
    exe(conn, 'INSERT INTO fornecedores (nome, telefone) VALUES (?,?)',
        (d['nome'], d.get('telefone', '')))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/fornecedores/<int:id>', methods=['PUT'])
def update_fornecedor(id):
    d = request.json
    conn = get_db()
    exe(conn, 'UPDATE fornecedores SET nome=?, telefone=? WHERE id=?',
        (d['nome'], d.get('telefone', ''), id))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/fornecedores/<int:id>', methods=['DELETE'])
def delete_fornecedor(id):
    conn = get_db()
    exe(conn, 'UPDATE fornecedores SET ativo=0 WHERE id=?', (id,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ── COMPRAS ────────────────────────────────────────────────────
@app.route('/api/compras', methods=['GET'])
def get_compras():
    mes = request.args.get('mes', datetime.now(BRASILIA).strftime('%Y-%m'))
    conn = get_db()
    rows = q(conn,
        "SELECT * FROM compras WHERE TO_CHAR(data::date,'YYYY-MM') = ? ORDER BY data DESC", (mes,))
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/compras', methods=['POST'])
def add_compra():
    try:
        d = request.json
        if not d:
            return jsonify({'ok': False, 'erro': 'Corpo da requisição inválido ou ausente'}), 400
        if not d.get('descricao'):
            return jsonify({'ok': False, 'erro': 'Campo "descricao" é obrigatório'}), 400
        if d.get('valor_unit') is None:
            return jsonify({'ok': False, 'erro': 'Campo "valor_unit" é obrigatório'}), 400

        qtd    = float(d.get('quantidade', 1))
        vunit  = float(d['valor_unit'])
        vtotal = round(qtd * vunit, 2)

        logging.debug('add_compra() — payload: %s', d)

        conn = get_db()
        novo_id = exe(conn,
            'INSERT INTO compras (fornecedor_id, fornecedor_nome, descricao, quantidade, unidade, valor_unit, valor_total, pago, data) VALUES (?,?,?,?,?,?,?,?,?)',
            (d.get('fornecedor_id'), d.get('fornecedor_nome', ''), d['descricao'],
             qtd, d.get('unidade', 'un'), vunit, vtotal, 0, agora()))
        conn.close()

        if novo_id is None:
            logging.error('add_compra() — inserção não retornou id; registro pode não ter sido salvo')
            return jsonify({'ok': False, 'erro': 'Falha ao registrar compra no banco de dados'}), 500

        logging.info('add_compra() — compra registrada com id=%s', novo_id)
        return jsonify({'ok': True, 'id': novo_id})

    except (KeyError, ValueError, TypeError) as e:
        logging.error('add_compra() — erro de validação: %s', e)
        return jsonify({'ok': False, 'erro': f'Dados inválidos: {e}'}), 400

@app.route('/api/compras/<int:id>', methods=['DELETE'])
def delete_compra(id):
    conn = get_db()
    exe(conn, 'DELETE FROM compras WHERE id=?', (id,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/compras/<int:id>/pagar', methods=['PUT'])
def pagar_compra(id):
    conn = get_db()
    exe(conn, 'UPDATE compras SET pago=1 WHERE id=?', (id,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/compras/resumo', methods=['GET'])
def resumo_compras():
    mes = request.args.get('mes', datetime.now(BRASILIA).strftime('%Y-%m'))
    conn = get_db()
    totais = qone(conn,
        "SELECT COALESCE(SUM(valor_total),0) as total, COALESCE(SUM(CASE WHEN pago=1 THEN valor_total ELSE 0 END),0) as pago, COALESCE(SUM(CASE WHEN pago=0 THEN valor_total ELSE 0 END),0) as pendente FROM compras WHERE TO_CHAR(data::date,'YYYY-MM')=?", (mes,))
    por_forn = q(conn,
        "SELECT fornecedor_nome, COUNT(*) as qtd_compras, SUM(valor_total) as total, SUM(CASE WHEN pago=1 THEN valor_total ELSE 0 END) as pago, SUM(CASE WHEN pago=0 THEN valor_total ELSE 0 END) as pendente FROM compras WHERE TO_CHAR(data::date,'YYYY-MM')=? GROUP BY fornecedor_nome ORDER BY total DESC", (mes,))
    conn.close()
    return jsonify({
        'mes': mes,
        'totais': {k: float(v) for k, v in dict(totais).items()},
        'por_fornecedor': [{k: float(v) if isinstance(v, (int, float)) else v for k, v in dict(r).items()} for r in por_forn]
    })

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

if __name__ == '__main__':
    os.makedirs('static', exist_ok=True)
    print("Iniciando banco de dados...")
    init_db()
    print("Quiosque do Milho iniciado!")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
