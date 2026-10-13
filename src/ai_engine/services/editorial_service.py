from typing import Optional, Dict, Any, List
from uuid import UUID
import json

from ai_engine.gateway.ai_gateway import AIGateway
from ai_engine.models.pipeline_models import NormalizedNews, EnrichedNews
from config.logging_setup import get_logger

logger = get_logger("ai_engine.services")

class EditorialService:
    def __init__(self, ai_gateway: AIGateway):
        self.ai = ai_gateway

    def normalize(self, raw_title: str, raw_text: str) -> Dict[str, Any]:
        """Normaliza, detecta idioma e limpa o conteúdo."""
        system_prompt = """
        És um editor de notícias sénior. O teu objetivo é limpar, normalizar e detetar o idioma da notícia.
        Responde APENAS em JSON com os campos: title, content, language (ISO code), topics (lista), is_valid (bool), word_count (int).
        Se o conteúdo for lixo ou publicidade, define is_valid como false.
        """
        user_prompt = f"Título: {raw_title}\n\nConteúdo: {raw_text}"
        
        return self.ai.chat(system_prompt, user_prompt)

    def enrich(self, title: str, content: str) -> Dict[str, Any]:
        """Enriquece a notícia com análise profunda, tradução para PT (se necessário) e insights."""
        system_prompt = """
        És um analista de inteligência económica e editor editorial. 
        Analisa a notícia e extrai insights profundos. Se a notícia não for em Português (PT), traduz os factos mas foca-te em gerar o output em Português.
        Responde APENAS em JSON com os seguintes campos exatos:
        - summary_pt: Resumo executivo em português.
        - editorial_title: Título otimizado editorialmente sem alterar os factos.
        - keywords: Lista de palavras-chave.
        - entities: Objeto com listas de 'people', 'organizations', 'locations'.
        - sentiment: 'positive', 'neutral' ou 'negative'.
        - relevance_score: De 0.0 a 1.0.
        - impact_economic: Descrição do impacto económico.
        - impact_social: Descrição do impacto social.
        - opportunities: Oportunidades detetadas.
        - risks: Riscos detetados.
        - sector: Setor económico predominante.
        - region: Região afetada.
        - stakeholders: Lista de partes interessadas.
        """
        user_prompt = f"Título: {title}\n\nConteúdo: {content}"
        
        return self.ai.chat(system_prompt, user_prompt)

    def generate_post(self, cluster_data: Dict[str, Any]) -> Dict[str, Any]:
        """Gera um post editorial a partir de um cluster de notícias."""
        system_prompt = """
        És um editor de conteúdo premium. Cria um post unificado e coerente a partir das notícias relacionadas fornecidas.
        Evita redundâncias. O tom deve ser profissional e informativo.
        Responde em JSON: title, subtitle, body, executive_summary, keywords, insights.
        """
        user_prompt = f"Dados do Cluster: {json.dumps(cluster_data)}"
        return  self.ai.chat(system_prompt, user_prompt)

    def ai_editional_pipeline(self, raw_title: str, raw_text: str) -> Optional[EnrichedNews]:
        """Pipeline completa de normalização e enriquecimento editorial."""

        """Enriquece a notícia com análise profunda, tradução para PT (se necessário) e insights."""
        system_prompt = """
        És um editor de de conteúdo premium e analista de inteligência económica, investimentos e um consultor de oportunidades. 
        Analisa a notícia e extrai insights profundos. Se a notícia não for em Português (PT), traduz os factos mas foca-te em gerar o output em Português de portugal. 
        O tom deve ser profissional e informativo. Evita redundâncias.
        Responde APENAS em JSON com os seguintes campos exatos:
        - summary_pt: Resumo executivo em português.
        - enriched_content: Conteúdo enriquecido e otimizado em português.
        - editorial_title: Título otimizado editorialmente sem alterar os factos.
        - keywords: Lista de palavras-chave.
        - entities: Objeto com listas de 'people', 'organizations', 'locations'.
        - stakeholders: Lista de partes interessadas.
        - sentiment: 'positive', 'neutral' ou 'negative'.
        - relevance_score: De 0.0 a 10.
        - insights: KPIs relevantes com valores numéricos no formato {kpi: str, value: float}.
        - impact_economic: Descrição do impacto económico.
        - impact_social: Descrição do impacto social.
        - opportunities: Oportunidades detetadas.
        - risks: Riscos detetados.
        - sector: Setor económico predominante.
        - region: Região afetada.
        - country: País afetado.
        """
        user_prompt = f"Título: {raw_title}\n\nConteúdo: {raw_text}"
        

        try:
            edited_post = self.ai.chat(system_prompt, user_prompt)
            return EnrichedNews(
                title=edited_post["editorial_title"],
                content=edited_post["enriched_content"],
                summary_pt=edited_post["summary_pt"],
                keywords=edited_post["keywords"],
                entities=edited_post["entities"],
                sentiment=edited_post["sentiment"],
                relevance_score=edited_post["relevance_score"],
                impact_economic=edited_post["impact_economic"],
                impact_social=edited_post["impact_social"],
                opportunities=edited_post["opportunities"],
                risks=edited_post["risks"],
                sector=edited_post["sector"],
                region=edited_post["region"],
                stakeholders=edited_post["stakeholders"]
            )
        except Exception as e:
            logger.error(f"Erro na pipeline editorial: {e}")
            return None