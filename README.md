# 🌽 Quiosque do Milho — Deploy no Railway

## Arquivos necessários

```
projeto/
├── app.py              ← backend PostgreSQL (este arquivo)
├── requirements.txt    ← dependências Python
├── Procfile            ← comando de start para o Railway
└── static/
    └── index.html      ← frontend (copie da pasta original)
```

---

## Passo a passo completo

### 1. Criar conta no GitHub
Acesse **github.com** e crie uma conta gratuita.

### 2. Criar repositório no GitHub
- Clique em **New repository**
- Nome: `quiosque-milho` (ou qualquer nome)
- Deixe como **Public**
- Clique em **Create repository**

### 3. Fazer upload dos arquivos
Na página do repositório clique em **uploading an existing file** e envie:
- `app.py`
- `requirements.txt`
- `Procfile`
- A pasta `static/` com o `index.html` dentro

### 4. Criar conta no Railway
Acesse **railway.app** e entre com sua conta do GitHub.

### 5. Criar o projeto no Railway
- Clique em **New Project**
- Escolha **Deploy from GitHub repo**
- Selecione o repositório `quiosque-milho`
- O Railway detecta automaticamente que é Python

### 6. Adicionar o banco PostgreSQL
- Dentro do projeto, clique em **+ New**
- Escolha **Database → Add PostgreSQL**
- O Railway cria o banco e conecta automaticamente

### 7. Configurar a variável de ambiente
- Clique no serviço do app (não no banco)
- Vá em **Variables**
- Clique em **+ New Variable**
- Nome: `DATABASE_URL`
- Valor: clique em **Add Reference** e selecione `DATABASE_URL` do PostgreSQL

### 8. Fazer o deploy
- O Railway já deve ter iniciado o deploy automaticamente
- Aguarde 2-3 minutos
- Clique em **Settings → Networking → Generate Domain**
- Vai gerar uma URL tipo: `https://quiosque-milho-production.up.railway.app`

### 9. Acessar pelo tablet
- Abra o navegador no tablet
- Acesse a URL gerada
- No Chrome: clique nos 3 pontos → **Adicionar à tela inicial**
- Vira um atalho que abre como app!

---

## Plano gratuito do Railway

O plano gratuito oferece:
- **$5 de crédito por mês** — suficiente para uso leve
- **PostgreSQL gratuito** incluso
- Se precisar de mais, o plano pago é $5/mês

---

## ⚠️ Importante: atualizar a URL da API no frontend

Depois de fazer o deploy, você precisa atualizar o `index.html`.

Procure esta linha no `index.html`:
```javascript
const API = 'http://localhost:5000/api';
```

Troque pelo endereço do Railway:
```javascript
const API = 'https://quiosque-milho-production.up.railway.app/api';
```

Depois faça o upload do `index.html` atualizado no GitHub.
O Railway vai atualizar automaticamente.
