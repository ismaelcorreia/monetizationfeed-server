import json
from typing import Dict, Any

from groq import Groq

from config.logging_setup import get_logger

logger = get_logger("ai_engine.groq")


class GroqGateway:
    """
    Gateway síncrono para Groq (OpenAI-compatible SDK).
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ):
        self.client = Groq(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> Dict[str, Any]:

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

        content = response.choices[0].message.content
        print(f"\n\n\nAI RESPONSE::: {content}\n\n\n")
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"text": content}