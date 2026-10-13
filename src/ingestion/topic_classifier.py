"""
TopicClassifier — keyword-based topic inference.
Single responsibility: assign a topic category to an article.
No external API calls — runs entirely offline.
"""
from __future__ import annotations

import re

TOPIC_RULES: dict[str, list[str]] = {
    "politics":   ["government", "election", "parliament", "president", "minister",
                   "política", "governo", "eleição", "presidente"],
    "economy":    ["economy", "gdp", "inflation", "market", "trade", "investment",
                   "economia", "mercado", "inflação", "investimento", "kwanza"],
    "technology": ["technology", "ai", "software", "startup", "digital", "cyber",
                   "tecnologia", "inteligência artificial", "dados"],
    "health":     ["health", "hospital", "disease", "vaccine", "medicine",
                   "saúde", "hospital", "doença", "vacina", "médico"],
    "sports":     ["football", "soccer", "basketball", "athlete", "championship",
                   "futebol", "desporto", "campeonato", "atleta"],
    "environment":["climate", "environment", "energy", "carbon", "renewable",
                   "clima", "ambiente", "energia", "sustentável"],
    "africa":     ["angola", "africa", "nigeria", "kenya", "ghana", "namibia",
                   "luanda", "maputo", "nairobi", "africa"],
}


class TopicClassifier:

    def classify(self, title: str, text: str, keywords: list[str]) -> str:
        """Return the best-matching topic category or 'general'."""
        corpus = " ".join([title, text[:500], *keywords]).lower()
        scores: dict[str, int] = {}

        for topic, terms in TOPIC_RULES.items():
            score = sum(1 for term in terms if re.search(r"\b" + re.escape(term) + r"\b", corpus))
            if score:
                scores[topic] = score

        if not scores:
            return "general"

        return max(scores, key=lambda t: scores[t])
