import json
import asyncio
from typing import Dict, Any, Optional
import httpx

from config.logging_setup import get_logger

logger = get_logger("ai_engine.openrouter")


class OpenRouterGateway:
    """Gateway para a API OpenRouter com retry automático em caso de rate limit (429).

    Suporta múltiplos providers (Ollama / OpenRouter) e devolve JSON
    quando possível, ou {'text': content} em caso contrário.
    """

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 120, max_tokens: int = 2048):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens

    def chat(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        url = f"{self.base_url}/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://monetizationfeed.app",
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": self.max_tokens,
        }

        max_retries = 4
        backoff = 10  # segundos iniciais de espera

        import time
        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(url, json=payload, headers=headers)

                    if resp.status_code == 429:
                        wait = backoff * (2 ** attempt)
                        logger.warning(
                            "OpenRouter rate limit (429). Tentativa %d/%d — aguardando %ds...",
                            attempt + 1, max_retries, wait
                        )
                        time.sleep(wait)
                        continue

                    resp.raise_for_status()
                    result = resp.json()

                    choices = result.get("choices") or []
                    if choices:
                        content = choices[0].get("message", {}).get("content", "")
                    else:
                        content = result.get("output", "")

                    try:
                        return json.loads(content)
                    except json.JSONDecodeError:
                        return {"text": content}

            except httpx.HTTPStatusError:
                raise
            except Exception as exc:
                logger.error("OpenRouter error: %s", exc)
                raise

        raise RuntimeError(f"OpenRouter rate limit persistente após {max_retries} tentativas para modelo {self.model}")
