import os
import glob
import random
import wave
import uuid
from pathlib import Path
from piper.voice import PiperVoice
from config.logging_setup import get_logger
from storage.media_storage import MediaStorage
from config.settings import AppConfig

logger = get_logger("ai_engine.tts")

class TTSService:
    def __init__(self, media_storage: MediaStorage, cfg: AppConfig):
        self.media_storage = media_storage
        self.cfg = cfg
        # Resolve to server/data/piper_voices robustly
        base_dir = Path(__file__).resolve().parents[3]
        self.voices_dir = base_dir / "data" / "piper_voices"
        self.voices_dir.mkdir(parents=True, exist_ok=True)
        
        # Load available voices
        self.available_models = self._discover_models()
        self.loaded_voices = {} # Cache for loaded PiperVoice instances

    def _discover_models(self):
        """Procura todos os ficheiros .onnx no diretório de vozes (incluindo subpastas)."""
        pattern = str(self.voices_dir / "**/*.onnx")
        models = glob.glob(pattern, recursive=True)
        if not models:
            logger.warning(f"Nenhum modelo Piper encontrado em {self.voices_dir}")
        else:
            logger.info(f"Modelos Piper encontrados: {len(models)}")
        return models

    def _get_random_voice(self):
        """Seleciona um modelo aleatório, suportando assim multi-vozes dinâmicas."""
        self.available_models = self._discover_models() # refresh
        if not self.available_models:
            raise ValueError("Não existem modelos Piper instalados.")
        
        model_path = random.choice(self.available_models)
        
        if model_path not in self.loaded_voices:
            logger.info(f"A carregar novo modelo Piper: {model_path}")
            self.loaded_voices[model_path] = PiperVoice.load(model_path)
            
        return self.loaded_voices[model_path]

    def generate_audio(self, text: str, prefix: str = "audio") -> str:
        """
        Gera o áudio usando Piper, faz upload para o MinIO e retorna o URL seguro.
        """
        voice = self._get_random_voice()
        temp_filename = f"/tmp/{prefix}_{uuid.uuid4().hex}.wav"
        
        logger.info(f"A sintetizar áudio para o texto ({len(text)} chars)...")
        with wave.open(temp_filename, "wb") as wav_file:
            voice.synthesize_wav(text, wav_file)
        # Upload para o MinIO
        with open(temp_filename, "rb") as audio_data:
            data = audio_data.read()
            object_key = self.media_storage.upload_raw_bytes(
                article_id=uuid.uuid4(),
                filename=os.path.basename(temp_filename),
                data=data,
                content_type="audio/wav"
            )
            
        # Limpar ficheiro temporário
        os.remove(temp_filename)
        return object_key
