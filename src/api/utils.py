import dataclasses
from uuid import UUID
from datetime import datetime
from enum import Enum

def dataclass_to_dict(obj):
    """Converte dataclasses e tipos especiais para formatos JSON-serializáveis."""
    if dataclasses.is_dataclass(obj):
        return {k: dataclass_to_dict(v) for k, v in dataclasses.asdict(obj).items()}
    elif isinstance(obj, dict):
        return {k: dataclass_to_dict(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [dataclass_to_dict(i) for i in obj]
    elif isinstance(obj, (UUID, datetime)):
        return str(obj)
    elif isinstance(obj, Enum):
        return obj.value
    return obj
