"""
GoogleGateway — integração com Google AI Studio (Gemini API).

Endpoint: https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
Auth: ?key=API_KEY (query param)
Modelo padrão: gemini-2.0-flash (gratuito, 1500 req/dia, 1M tokens contexto)
"""
import asyncio
import json
import re
from typing import Any, Dict, Optional

import httpx

from config.logging_setup import get_logger

logger = get_logger("ai_engine.google")

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GoogleGateway:
    """Gateway para Google AI Studio com retry automático em rate limit."""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash", timeout: int = 120, max_tokens: int = 2048):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens

    def chat(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        url = f"{_BASE_URL}/{self.model}:generateContent"
        params = {"key": self.api_key}

        payload = {
            "system_instruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}]
                }
            ],
            "generationConfig": {
                "maxOutputTokens": self.max_tokens,
                "temperature": 0.3,
                "responseMimeType": "application/json",
            },
        }

        max_retries = 4
        backoff = 5  # segundos iniciais

        import time
        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(url, json=payload, params=params)

                    # Rate limit ou servidor indisponível → retry com backoff
                    if resp.status_code in (429, 503):
                        wait = backoff * (2 ** attempt)
                        logger.warning(
                            "Google AI rate limit (%d). Tentativa %d/%d — aguardando %ds...",
                            resp.status_code, attempt + 1, max_retries, wait
                        )
                        time.sleep(wait)
                        continue

                    resp.raise_for_status()
                    return self._parse_response(resp.json())

            except httpx.HTTPStatusError:
                raise
            except Exception as exc:
                logger.error("Google AI Gateway error: %s", exc)
                raise

        raise RuntimeError(
            f"Google AI rate limit persistente após {max_retries} tentativas (modelo: {self.model})"
        )

    # ── Private ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_response(result: dict) -> Dict[str, Any]:
        """Extrai texto da resposta Gemini e tenta parsear como JSON."""
        try:
            candidates = result.get("candidates", [])
            if not candidates:
                raise ValueError(f"Sem candidatos na resposta Gemini: {result}")

            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                raise ValueError("Resposta Gemini sem partes de conteúdo")

            raw_text = parts[0].get("text", "")

            # Tenta parsear directamente (quando responseMimeType=application/json funciona)
            try:
                return json.loads(raw_text)
            except json.JSONDecodeError:
                pass

            # Fallback: extrai JSON de dentro de markdown fences
            clean = re.sub(r"```json|```", "", raw_text).strip()
            match = re.search(r"\{.*\}", clean, re.DOTALL)
            if match:
                return json.loads(match.group(0))

            # Último recurso: devolve como texto
            return {"text": raw_text}

        except Exception as exc:
            logger.error("Erro ao parsear resposta Gemini: %s | Resposta: %s", exc, result)
            raise
