# src/ocr/engine_singleton.py
from typing import Optional
from src.ocr.engine import EasyOCREngine

_ENGINE: Optional[EasyOCREngine] = None

def get_engine() -> EasyOCREngine:
    global _ENGINE
    if _ENGINE is None:
        # un seul Reader EasyOCR en mémoire
        _ENGINE = EasyOCREngine(gpu=False)
    return _ENGINE
