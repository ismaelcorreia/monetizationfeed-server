# NewsEngine

Motor de recolha, tratamento e publicação de notícias.  
Stack: Python · PostgreSQL · MinIO · Anthropic Claude · APScheduler · Docker

---

## Arquitectura

```
news_engine/
├── config/
│   ├── settings.py            # Configurações centrais (env vars)
│   └── logging_setup.py       # Logger único e consistente
│
├── models/
│   └── entities.py            # Entidades de domínio puras (dataclasses)
│
├── migrations/
│   └── 001_initial_schema.sql # DDL: 5 tabelas + índices
│
├── storage/
│   ├── database.py            # Pools sync (psycopg2) e async (asyncpg)
│   ├── source_repository.py   # CRUD de fontes
│   ├── article_repository.py  # CRUD de artigos raw + processed
│   └── media_storage.py       # Upload/download MinIO
│
├── ingestion/
│   ├── article_fetcher.py     # Newspaper3k wrapper
│   ├── language_detector.py   # Detecção de idioma
│   ├── topic_classifier.py    # Classificação offline por keywords
│   └── ingestion_pipeline.py  # Orquestra: fetch → classify → media → persist
│
├── ai_agent/
│   ├── article_processor.py   # Chama Anthropic API (tradução + tratamento)
│   └── processing_pipeline.py # Loop async: drena fila pending, um a um
│
├── discovery/
│   └── source_discovery.py    # DuckDuckGo → descobre novas fontes
│
├── scheduler/
│   └── job_scheduler.py       # APScheduler: cron diário + semanal
│
├── core/
│   └── orchestrator.py        # Wiring geral + API pública do motor
│
├── main.py                    # Entrypoint do serviço
├── cli.py                     # Comandos manuais
├── requirements.txt
├── .env.example
└── docker/
    ├── Dockerfile
    └── docker-compose.yml
```

---

## Fluxo de dados

```
[Scheduler / CLI]
       │
       ▼
Orchestrator.run_ingestion()
       │
       ▼
IngestionPipeline.ingest_source(source)
  ├── ArticleFetcher.fetch_source_urls()   → lista de URLs
  ├── ArticleFetcher.fetch(url)            → texto, imagens, metadata
  ├── LanguageDetector.detect()            → ISO 639-1
  ├── TopicClassifier.classify()           → categoria
  ├── MediaStorage.upload_media_from_url() → MinIO key
  └── ArticleRepository.insert_raw_article()
       │
       ▼
[raw_articles] STATUS = pending
       │
       ▼
ProcessingPipeline.run_continuous()
  └── ArticleRepository.get_next_pending()  → 1 artigo
      ArticleProcessor.process(article)
        └── Anthropic API → traduz + trata
      ArticleRepository.insert_processed()
      raw_articles.status = processed
       │
       ▼
[processed_articles] STATUS = published

[Scheduler semanal]
       │
       ▼
SourceDiscovery.run_discovery()
  ├── DuckDuckGo.text(search_term)
  ├── TopicClassifier.classify()
  └── SourceRepository.upsert_discovered()
       │
       ▼
[discovered_sources] promoted = false
```

---

## Tabelas PostgreSQL

| Tabela               | Descrição                                      |
|----------------------|------------------------------------------------|
| `news_sources`       | Fontes activas (URL, locale, tópico, estado)   |
| `raw_articles`       | Artigos crus (pending → processed)             |
| `processed_articles` | Artigos traduzidos/tratados (published)        |
| `discovered_sources` | Fontes encontradas automaticamente             |
| `ingestion_log`      | Auditoria de cada ciclo de ingestão            |

---

## MinIO — organização de media

```
bucket: news-media
└── {article_id}/
    ├── a1b2c3d4.jpg   (top image)
    ├── e5f6g7h8.jpg
    └── ...
```

---

## Operação

### Iniciar stack completa
```bash
cp .env.example .env
# editar .env com credenciais reais
docker compose -f docker/docker-compose.yml up -d
```

### Comandos manuais (CLI)
```bash
# Ingestão imediata
docker compose -f docker/docker-compose.yml run --rm --profile cli cli ingest

# Processar artigos pendentes com IA
docker compose -f docker/docker-compose.yml run --rm --profile cli cli process

# Descoberta de novas fontes
docker compose -f docker/docker-compose.yml run --rm --profile cli cli discover

# Adicionar fonte manualmente
docker compose -f docker/docker-compose.yml run --rm --profile cli cli \
  add-source https://example.com "Nome da Fonte" pt-AO economy
```

### Schedules automáticos
| Job        | Cron (UTC)  | Descrição                          |
|------------|-------------|------------------------------------|
| Ingestão   | `0 6 * * *` | Diário às 06h00 UTC                |
| Descoberta | `0 2 * * 0` | Semanalmente (domingo às 02h00)    |
| AI loop    | contínuo    | Polling a cada 300s (configurável) |

---

## Princípios de design

- **Single Responsibility** — cada ficheiro tem uma função declarada no docstring
- **Dependency Injection** — o `Orchestrator` monta o grafo; os módulos não se importam entre si directamente
- **Separação sync/async** — ingestão é síncrona (threaded); AI pipeline é async
- **Sem lógica no entrypoint** — `main.py` e `cli.py` apenas delegam ao `Orchestrator`
- **Schema versionado** — migrations em SQL puro, executadas na ordem do nome do ficheiro
- **Media isolada por artigo** — cada `article_id` tem o seu prefixo no MinIO
