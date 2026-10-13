# Documentação do Servidor — MonetizationFeed News Engine

Motor de processamento de notícias (backend) do projecto MonetizationFeed. Responsável por descobrir fontes de notícias, extrair artigos, detectar língua, classificar tópicos, processar conteúdo com IA (tradução e tratamento editorial) e armazenar os dados em PostgreSQL e MinIO.

---

## Índice

1. [Arquitectura](#arquitectura)
2. [Módulos](#módulos)
3. [Configuração](#configuração)
4. [Variáveis de Ambiente](#variáveis-de-ambiente)
5. [Como Executar](#como-executar)
6. [CLI — Interface de Linha de Comando](#cli--interface-de-linha-de-comando)
7. [API REST](#api-rest)
8. [Testes](#testes)
9. [Solução de Problemas](#solução-de-problemas)

---

## Arquitectura

O projecto segue uma arquitectura modular orientada a domínio, onde cada camada tem responsabilidade única:

```
src/
├── main.py                  # Ponto de entrada (modo servidor contínuo)
├── cli.py                   # Interface de linha de comando
├── config/                  # Configurações e logging
│   ├── settings.py          # Dataclasses de configuração (lidas do .env)
│   └── logging_setup.py     # Setup de logging estruturado
├── core/
│   └── orchestrator.py      # Orquestrador central — monta e coordena todos os serviços
├── ingestion/               # Pipeline de ingestão de artigos
│   ├── article_fetcher.py   # Extracção de conteúdo web (Newspaper3k + crawl4ai)
│   ├── ingestion_pipeline.py# Coordena fetch → detect → classify → store
│   ├── language_detector.py # Detecção de idioma do artigo
│   └── topic_classifier.py  # Classificação de tópico (economia, tecnologia, etc.)
├── ai_agent/                # Agente de IA editorial
│   ├── article_processor.py # Traduz e trata artigos via gateway de IA
│   └── processing_pipeline.py # Gestão do fluxo de processamento pendente
├── ai_engine/               # Motor de IA multi-provider
│   ├── dispatcher.py        # Despacha tarefas para workers de IA
│   ├── pipeline.py          # AIOrchestrator — pipeline automático completo
│   ├── gateway/
│   │   ├── ai_gateway.py    # Interface base AIGateway + OllamaGateway + get_gateway()
│   │   └── openrouter_gateway.py # Gateway OpenRouter (API externa)
│   ├── models/              # Modelos de dados internos da IA
│   ├── services/            # Serviços especializados (normalização, enriquecimento, etc.)
│   └── workers/             # Workers de processamento assíncrono
├── discovery/
│   └── source_discovery.py  # Descobre novas fontes de notícias automaticamente
├── storage/                 # Camada de persistência
│   ├── database.py          # Gestão de pools sync/async PostgreSQL + migrações
│   ├── article_repository.py# CRUD de artigos (raw e processados)
│   ├── source_repository.py # CRUD de fontes e sites descobertos
│   └── media_storage.py     # Upload/download de mídia no MinIO
├── scheduler/
│   └── job_scheduler.py     # Agendamento de tarefas (APScheduler)
├── models/
│   └── entities.py          # Entidades de domínio (RawArticle, ProcessedArticle, NewsSource…)
├── api/
│   └── app.py               # API Flask — endpoints REST de exportação
└── migrations/              # Scripts SQL de migração do PostgreSQL
```

---

## Módulos

### `core/orchestrator.py` — Orquestrador Central
Ponto de montagem de todas as dependências. Não contém lógica de negócio — delega para os módulos de domínio.

- `bootstrap()` — inicializa pool síncrono, corre migrações e arranca o scheduler.
- `bootstrap_async()` — inicializa pool assíncrono e `AIOrchestrator`.
- `run_ingestion(run_type, keywords)` — corre ingestão em todas as fontes activas.
- `run_ai_processing()` — processa artigos pendentes com IA.
- `run_discovery()` — descobre novas fontes de notícias.

### `ingestion/` — Pipeline de Ingestão
1. **`ArticleFetcher`** — extrai HTML e conteúdo de URLs usando Newspaper3k e crawl4ai.
2. **`LanguageDetector`** — detecta o idioma do artigo (`langdetect`).
3. **`TopicClassifier`** — classifica o tópico com base em palavras-chave configuradas.
4. **`IngestionPipeline`** — coordena os passos acima e persiste os artigos na BD.

### `ai_engine/gateway/` — Gateways de IA
Abstracção sobre múltiplos providers de IA:

| Gateway | Provider | Quando usar |
|---|---|---|
| `OllamaGateway` | Ollama (local) | Produção / sem custo de API |
| `OpenRouterGateway` | OpenRouter API | Desenvolvimento / testes com modelos externos |

A função `get_gateway(cfg: AIConfig)` selecciona automaticamente o gateway com base na variável `AI_PROVIDER`.

### `ai_agent/article_processor.py` — Processador Editorial
Usa o gateway seleccionado para:
- Traduzir artigos para Português europeu/angolano
- Adaptar o tom editorial para o contexto africano/angolano
- Extrair *persuasion hooks* (frases de impacto)
- Retornar um `ProcessedArticle` com `title_pt`, `body_pt`, `topic` e `persuasion_hooks`

### `discovery/source_discovery.py` — Descoberta de Fontes
Pesquisa automaticamente novas fontes de notícias com base em termos configurados (`DISCOVERY_TERMS`). Guarda as sugestões na tabela `discovered_sites` para revisão.

### `storage/` — Persistência
- **PostgreSQL** — artigos raw, artigos processados, fontes, logs de ingestão.
- **MinIO** — armazenamento de imagens e ficheiros de média associados aos artigos.

### `scheduler/job_scheduler.py` — Agendador
Usa APScheduler para agendar ingestão e descoberta automáticas com expressões cron configuráveis.

---

## Configuração

1. Copie o ficheiro de exemplo:
   ```bash
   cp .env.example .env
   ```
2. Edite o `.env` com os valores do seu ambiente.

---

## Variáveis de Ambiente

| Variável | Padrão | Descrição |
|---|---|---|
| `POSTGRES_HOST` | `postgres` | Host da base de dados |
| `POSTGRES_PORT` | `5432` | Porta do PostgreSQL |
| `POSTGRES_DB` | `newsdb` | Nome da base de dados |
| `POSTGRES_USER` | `newsuser` | Utilizador da BD |
| `POSTGRES_PASSWORD` | `newspass` | Palavra-passe da BD |
| `MINIO_ENDPOINT` | `minio:9000` | Endpoint do MinIO |
| `MINIO_ACCESS_KEY` | `minioadmin` | Chave de acesso MinIO |
| `MINIO_SECRET_KEY` | `minioadmin` | Chave secreta MinIO |
| `MINIO_SECURE` | `false` | Usar HTTPS no MinIO |
| `AI_PROVIDER` | `openrouter` | Provider de IA: `ollama` ou `openrouter` |
| `AI_MODEL` | `mistral:7b` | Modelo a usar (ex: `mistral:7b`, `deepseek/deepseek-r1`) |
| `AI_MAX_TOKENS` | `4096` | Máximo de tokens por resposta |
| `AI_TIMEOUT` | `120` | Timeout de pedidos IA (segundos) |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | URL do servidor Ollama |
| `OPENROUTER_BASE_URL` | `https://api.openrouter.ai` | URL base da API OpenRouter |
| `OPENROUTER_API_KEY` | *(vazio)* | Chave da API OpenRouter |
| `INGESTION_CRON` | `0 6 * * *` | Cron de ingestão automática |
| `DISCOVERY_CRON` | `0 2 * * 0` | Cron de descoberta semanal |
| `AI_PROCESSING_INTERVAL` | `300` | Intervalo do loop de IA (segundos) |
| `LOG_LEVEL` | `INFO` | Nível de logging (`DEBUG`, `INFO`, `WARNING`) |
| `DISCOVERY_TERMS` | *(veja settings.py)* | Termos de pesquisa para descoberta de fontes |

---

## Como Executar

### Via Docker (Recomendado)

Na pasta `server/`:

```bash
docker-compose up --build
```

Inicia automaticamente:
- PostgreSQL
- MinIO
- Ollama (com o modelo configurado)
- Motor de processamento (engine)
- API REST (porta `5000`)

### Desenvolvimento Local (Manual)

1. Crie e active um ambiente virtual:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

2. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure o `PYTHONPATH` e execute:
   ```bash
   export PYTHONPATH=$(pwd)/src
   python src/main.py
   ```

---

## CLI — Interface de Linha de Comando

O CLI permite executar operações manuais sem arrancar o servidor completo.

```bash
# Ver ajuda geral
python src/cli.py --help
```

### Comandos Disponíveis

#### `ingest` — Ingestão de Notícias
Recolhe artigos de todas as fontes activas.
```bash
python src/cli.py ingest
python src/cli.py ingest "angola,economia,tecnologia"   # com filtro de keywords
```

#### `discovery` — Descoberta de Fontes
Pesquisa novas fontes de notícias automaticamente.
```bash
python src/cli.py discovery
```

#### `list-sources` — Listar Fontes
Lista todos os sites registados na base de dados.
```bash
python src/cli.py list-sources
python src/cli.py list-sources finance   # filtrar por tópico
```

#### `ai-process` — Pipeline Editorial de IA
Executa o pipeline de processamento com IA nos artigos pendentes.
```bash
# Pipeline automático completo
python src/cli.py ai-process auto

# Passos individuais
python src/cli.py ai-process normalize --limit 20
python src/cli.py ai-process enrich --limit 10
python src/cli.py ai-process cluster --limit 10
python src/cli.py ai-process post --limit 10
```

### Via Docker

```bash
docker-compose run --rm cli ingest
docker-compose run --rm cli ai-process auto
```

---

## API REST

API Flask disponível em `http://localhost:5000` (modo local) ou gerida pelo Docker Compose.

### Fontes

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/api/sources` | Lista todos os sites registados |
| `POST` | `/api/sources` | Adiciona um novo site |
| `DELETE` | `/api/sources/<id>` | Remove um site |

### Artigos

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/api/articles/raw` | Lista artigos originais recolhidos |
| `GET` | `/api/articles/processed` | Lista artigos traduzidos e processados |

### Descoberta

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/api/discovered` | Lista sites encontrados automaticamente |

### Executar a API Localmente

```bash
export PYTHONPATH=$(pwd)/src
python src/api/app.py
```

---

## Testes

```bash
# Instalar dependências de teste
pip install pytest pytest-mock pytest-asyncio

# Executar todos os testes
pytest tests/

# Testes específicos
pytest tests/test_article_fetcher.py
pytest tests/test_article_processor.py
```

### Teste Manual de Ingestão

```bash
python src/ingestion/test_fetcher_manual.py
```

---

## Solução de Problemas

| Problema | Causa provável | Solução |
|---|---|---|
| `ImportError: cannot import name 'get_gateway'` | Função definida dentro de uma classe por engano | Corrigido — `get_gateway` é agora função de módulo em `ai_gateway.py` |
| `Erro ao conectar ao banco` | Container `postgres` não está saudável | `docker-compose ps` e verifique os logs do postgres |
| `Modelo de IA falhando (Ollama)` | Modelo ainda a ser descarregado | Aguarde o primeiro arranque do Ollama; o modelo é descarregado automaticamente |
| `OpenRouter API key not configured` | `OPENROUTER_API_KEY` vazia | Defina a variável no `.env` |
| `ModuleNotFoundError` | `src/` não está no `PYTHONPATH` | Execute `export PYTHONPATH=$(pwd)/src` antes de correr scripts |
| `crawl4ai` sync não disponível | Aviso de deprecação da versão síncrona | Instale `crawl4ai[sync]` ou ignore — o async está funcional |
