from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import httpx
import json

from config.logging_setup import get_logger
from config.settings import AIConfig

from .openrouter_gateway import OpenRouterGateway
from .google_gateway import GoogleGateway
from .groq_gateway import GroqGateway

logger = get_logger("ai_engine.gateway")

class AIGateway(ABC):
    @abstractmethod
    def chat(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """Envia uma mensagem para a IA e retorna uma resposta estruturada (JSON)."""
        pass


def get_gateway(cfg: AIConfig) -> AIGateway:
    """Retorna uma implementação de gateway com base no provider configurado.

    Providers suportados:
      - 'groq'      → Groq AI Studio (Groq) — recomendado para dev
      - 'google'      → Google AI Studio (Gemini) — recomendado para dev
      - 'openrouter'  → OpenRouter API
      - 'ollama'      → Ollama local (padrão para produção)
    """
    provider = getattr(cfg, "provider", "groq")


    if provider == "google":
        return GoogleGateway(
            api_key=cfg.google_api_key,
            model=cfg.model,
            timeout=cfg.request_timeout,
            max_tokens=cfg.max_tokens,
        )

    if provider == "openrouter":
        return OpenRouterGateway(
            cfg.openrouter_base_url,
            cfg.openrouter_api_key,
            cfg.model,
            timeout=cfg.request_timeout,
            max_tokens=cfg.max_tokens,
        )

    # Default: Groq
    return GroqGateway(
            api_key=cfg.groq_api_key,
            model=cfg.model,
            max_tokens=cfg.max_tokens,
        )
