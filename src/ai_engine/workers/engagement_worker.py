import json
import random
from uuid import UUID
from datetime import datetime, timedelta, timezone

from config.logging_setup import get_logger
from ai_engine.gateway.ai_gateway import get_gateway
from storage.database import sync_connection, sync_cursor

logger = get_logger("ai_engine.workers.engagement")

class EngagementWorker:
    def __init__(self, ai_config, tts_service=None):
        self.ai_gateway = get_gateway(ai_config)
        self.tts_service = tts_service

    def analyze_and_engage(self):
        """
        Analisa o calor dos posts publicados recentemente e interage se estiverem muito frios ou muito quentes.
        """
        logger.info("A iniciar EngagementWorker: Análise de calor de posts...")
        
        try:
            with sync_connection() as conn:
                with sync_cursor(conn) as cur:
                    # Busca posts publicados nos últimos 3 dias
                    cur.execute("""
                        SELECT id, title_pt, body_pt, published_at
                        FROM processed_articles 
                        WHERE status = 'published'
                        AND published_at >= NOW() - INTERVAL '3 days'
                    """)
                    posts = cur.fetchall()

                    for post in posts:
                        self._process_post_engagement(post, cur, conn)

        except Exception as e:
            logger.error(f"Erro no EngagementWorker: {e}", exc_info=True)


    def _process_post_engagement(self, post, cur, conn):
        post_id = str(post["id"])
        
        # Obter todos os comentários do post
        cur.execute("""
            SELECT id, author, content, created_at, is_ai 
            FROM comments 
            WHERE post_id = %s
            ORDER BY created_at ASC
        """, (post_id,))
        comments = cur.fetchall()

        num_comments = len(comments)
        now = datetime.now(timezone.utc)
        
        # O datetime vindo do PG normalmente pode não ter timezone, vamos garantir a comparação
        published_at = post["published_at"]
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
            
        age_hours = (now - published_at).total_seconds() / 3600

        # CASO 1: POST MUITO FRIO
        # Se tem mais de 24 horas e nenhum comentário, a IA entra com um comentário provocante
        if num_comments == 0 and age_hours > 24:
            logger.info(f"Post {post_id} está FRIO (0 comentários em >24h). A gerar provocação...")
            self._generate_cold_provocation(post_id, post["title_pt"], post["body_pt"], cur, conn)
        
        # CASO 2: POST MUITO QUENTE
        # Se tem mais de 5 comentários e a IA não foi a última a comentar
        elif num_comments >= 5:
            last_comment = comments[-1]
            if not last_comment["is_ai"]:
                # Medir calor: se o último comentário foi feito nas últimas 6 horas, consideramos quente
                last_comment_time = last_comment["created_at"]
                if last_comment_time.tzinfo is None:
                    last_comment_time = last_comment_time.replace(tzinfo=timezone.utc)
                
                if (now - last_comment_time).total_seconds() / 3600 < 6:
                    logger.info(f"Post {post_id} está QUENTE ({num_comments} comentários recentes). A participar na discussão...")
                    # Escolhe aleatoriamente um comentário humano para responder (preferência ao último)
                    human_comments = [c for c in comments if not c["is_ai"]]
                    if human_comments:
                        target_comment = human_comments[-1] # Responder ao mais recente
                        self._generate_hot_reply(post_id, target_comment["id"], post["title_pt"], post["body_pt"], target_comment["content"], cur, conn)


    def _generate_cold_provocation(self, post_id, title, body, cur, conn):
        system_prompt = (
            "És o 'Analista AI', um especialista sénior e comentador no mercado angolano. "
            "A tua tarefa é iniciar uma discussão num artigo que não teve comentários. "
            "Faz um comentário provocante, com um ponto de vista forte (talvez um pouco polémico ou questionador) "
            "sobre o tema do artigo para incentivar os leitores a discordar ou concordar contigo. "
            "Máximo 3 frases. Português de Angola. APENAS o texto da resposta, sem aspas."
        )
        
        user_prompt = f"TÍTULO: {title}\nCONTEÚDO: {body[:1500]}...\nEscreve o teu comentário:"
        self._dispatch_ai_and_save(post_id, None, system_prompt, user_prompt, cur, conn)

    
    def _generate_hot_reply(self, post_id, parent_id, title, body, user_comment, cur, conn):
        system_prompt = (
            "És o 'Analista AI', um analista macroeconómico e de investimentos sénior angolano. "
            "O artigo está a gerar muita discussão e deves responder de forma incisiva, "
            "desafiando ou validando o ponto de vista do utilizador com dados lógicos. "
            "Máximo 3 frases. Português de Angola. APENAS o texto da resposta, sem aspas."
        )
        
        user_prompt = (
            f"TÍTULO: {title}\n"
            f"CONTEÚDO: {body[:1000]}...\n\n"
            f"COMENTÁRIO DO UTILIZADOR: {user_comment}\n\n"
            "Escreve a tua resposta ao comentário:"
        )
        self._dispatch_ai_and_save(post_id, parent_id, system_prompt, user_prompt, cur, conn)

    def _dispatch_ai_and_save(self, post_id, parent_id, system_prompt, user_prompt, cur, conn):
        try:
            response = self.ai_gateway.chat(system_prompt, user_prompt)
            
            ai_content = ""
            if isinstance(response, dict) and "text" in response:
                ai_content = response["text"]
            elif isinstance(response, dict):
                ai_content = response.get("content", str(response))
            else:
                ai_content = str(response)

            ai_content = ai_content.strip().strip('"').strip("'")

            audio_url = None
            if self.tts_service:
                try:
                    import uuid
                    audio_url = self.tts_service.generate_audio(ai_content, prefix=f"comment_{uuid.uuid4().hex[:8]}")
                except Exception as tts_e:
                    logger.error(f"Erro ao gerar áudio para o comentário: {tts_e}")

            cur.execute(
                """
                INSERT INTO comments (post_id, parent_id, author, avatar, content, is_ai, audio_url, is_audio)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    post_id, 
                    parent_id, 
                    "Analista AI", 
                    "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=100&h=100&fit=crop", 
                    ai_content, 
                    True,
                    audio_url,
                    bool(audio_url)
                )
            )
            conn.commit()
            logger.info(f"Comentário gerado pela IA inserido no post {post_id}.")
        except Exception as e:
            logger.error(f"Falha ao gerar/salvar comentário IA: {e}")
            conn.rollback()
