"""
ArticleProcessor — AI agent que traduz e trata artigos via Ollama (local, free).
Single responsibility: chamar Ollama REST API e mapear resposta para ProcessedArticle.
Processa UM artigo de cada vez.
"""
from __future__ import annotations

import json
import re
from typing import Optional

import httpx

from config.logging_setup import get_logger
from config.settings import AIConfig
from ai_engine.gateway.ai_gateway import get_gateway
from models.entities import ArticleStatus, ProcessedArticle, RawArticle

logger = get_logger("ai_agent.article_processor")

_SYSTEM_PROMPT = """\
És um editor de conteúdo premium, analista de inteligência económica e consultor de oportunidades sénior. 
O teu objetivo é analisar a notícia (proveniente de diversas fontes globais), extrair insights profundos e adaptá-la para o público de língua portuguesa (foco Angola/África). O tom deve ser profissional e informativo. Evita redundâncias.

Responde APENAS em JSON com os seguintes campos exatos:
- summary_pt: Resumo executivo em português.
- enriched_content: Conteúdo enriquecido e otimizado em português. Deve limitar-se a um máximo aproximado de 4000 caracteres.
- editorial_title: Título otimizado editorialmente sem alterar os factos.
- keywords: Lista de palavras-chave.
- entities: Objeto com listas de 'people', 'organizations', 'locations'.
- stakeholders: Lista de partes interessadas.
- sentiment: 'positive', 'neutral' ou 'negative'.
- relevance_score: De 0.0 a 10.0.
- impact_economic: Descrição do impacto económico.
- impact_social: Descrição do impacto social.
- opportunities: Oportunidades detetadas.
- risks: Riscos detetados.
- sector: Setor económico predominante.
- region: Região afetada.

Regras obrigatórias:
- Nunca alteres factos, números, datas ou nomes próprios.
- Responde APENAS com o JSON, sem texto adicional, sem markdown, sem backticks.
"""


class ArticleProcessor:

    def __init__(self, cfg: AIConfig, gateway=None) -> None:
        self._cfg = cfg
        self._model = cfg.model
        self._max_tokens = cfg.max_tokens
        self._timeout = cfg.request_timeout
        # Allow injecting a custom gateway for testing; otherwise build from config
        self._gateway = gateway or get_gateway(cfg)

    def process(self, article: RawArticle) -> Optional[ProcessedArticle]:
        """Traduz e trata um artigo. Devolve None em caso de falha."""
        try:
            prompt = self._build_prompt(article)
            # Use gateway.chat which is synchronous
            result = self._gateway.chat(_SYSTEM_PROMPT, prompt)

            if isinstance(result, dict) and "text" in result:
                parsed = self._parse_response(result["text"])
            elif isinstance(result, dict):
                parsed = result
            else:
                parsed = self._parse_response(str(result))
            return self._build_processed(article, parsed)
        except json.JSONDecodeError as exc:
            logger.error("JSON parse falhou para artigo %s: %s", article.id, exc)
            return None
        except httpx.TimeoutException:
            logger.error("Timeout ao processar artigo %s (modelo: %s)", article.id, self._model)
            return None
        except Exception as exc:
            logger.error("Erro inesperado ao processar artigo %s: %s", article.id, exc)
            return None

    def health_check(self) -> bool:
        """Basic health check depending on provider. For Ollama checks tags endpoint; for OpenRouter checks API key presence."""
        try:
            if getattr(self._cfg, "provider", "ollama") == "openrouter":
                # For development using OpenRouter, ensure API key is present
                key = getattr(self._cfg, "openrouter_api_key", "")
                if not key:
                    logger.warning("OpenRouter API key not configured")
                    return False
                # Optionally ping the OpenRouter health endpoint (not guaranteed), just return True for now
                return True
            else:
                base_url = self._cfg.ollama_base_url.rstrip("/")
                with httpx.Client(timeout=10) as client:
                    resp = client.get(f"{base_url}/api/tags")
                    resp.raise_for_status()
                    models = [m["name"] for m in resp.json().get("models", [])]
                    available = any(self._model in m for m in models)
                    if not available:
                        logger.warning(
                            "Modelo '%s' não encontrado no Ollama. Disponíveis: %s",
                            self._model, models,
                        )
                    return available
        except Exception as exc:
            logger.error("AI provider inacessível: %s", exc)
            return False

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_prompt(self, article: RawArticle) -> str:
        # Passa o artigo original (com um limite muito largo apenas para evitar erros de limite de tokens da API)
        text_excerpt = article.raw_text[:25000]
        return (
            f"{_SYSTEM_PROMPT}\n\n"
            f"TÍTULO ORIGINAL: {article.title}\n\n"
            f"TÓPICO: {article.topic}\n\n"
            f"IDIOMA ORIGINAL: {article.language_detected}\n\n"
            f"CORPO DO ARTIGO ORIGINAL:\n{text_excerpt}"
        )

    def _call_ollama(self, prompt: str) -> str:
        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": self._max_tokens,
                "temperature": 0.3,   # baixa para manter factos
                "top_p": 0.9,
            },
        }
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(f"{self._base_url}/api/generate", json=payload)
            resp.raise_for_status()
            return resp.json()["response"]

    @staticmethod
    def _parse_response(raw: str) -> dict:
        # Limpa eventuais markdown fences que o modelo possa incluir
        clean = re.sub(r"```json|```", "", raw).strip()
        # Tenta extrair JSON mesmo que haja texto à volta
        match = re.search(r"\{.*\}", clean, re.DOTALL)
        if match:
            clean = match.group(0)
        return json.loads(clean)

    @staticmethod
    def _build_processed(article: RawArticle, parsed: dict) -> ProcessedArticle:
        body = parsed.get("enriched_content", "")
        word_count = len(body.split())
        reading_time = round(word_count / 200, 2)

        # Montar os ganchos baseados nos insights se existirem
        hooks = []
        if parsed.get("impact_economic"): hooks.append(f"Impacto Económico: {parsed['impact_economic']}")
        if parsed.get("opportunities"): hooks.append(f"Oportunidades: {parsed['opportunities']}")
        if parsed.get("risks"): hooks.append(f"Riscos: {parsed['risks']}")

        # Extrair tudo o que for de enriquecimento
        metadata = {
            "summary_pt": parsed.get("summary_pt"),
            "keywords": parsed.get("keywords", []),
            "entities": parsed.get("entities", {}),
            "stakeholders": parsed.get("stakeholders", []),
            "sentiment": parsed.get("sentiment"),
            "relevance_score": parsed.get("relevance_score"),
            "impact_economic": parsed.get("impact_economic"),
            "impact_social": parsed.get("impact_social"),
            "opportunities": parsed.get("opportunities"),
            "risks": parsed.get("risks"),
            "sector": parsed.get("sector"),
            "region": parsed.get("region"),
        }

        return ProcessedArticle(
            raw_article_id=article.id,
            title_pt=parsed.get("editorial_title", article.title),
            body_pt=body,
            topic=parsed.get("sector", article.topic),
            persuasion_hooks=hooks,
            word_count=word_count,
            reading_time_minutes=reading_time,
            status=ArticleStatus.PUBLISHED,
            metadata=metadata
        )