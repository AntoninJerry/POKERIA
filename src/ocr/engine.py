# src/ocr/engine.py
from __future__ import annotations
import re
import os
import numpy as np
from typing import Optional, Dict, Any, List, Tuple

class EasyOCREngine:
    """
    Enveloppe EasyOCR avec utilitaires:
      - read_text(img_rgb, allowlist=None) → (txt, conf, raw)
      - read_amount(img_rgb, prefer_rightmost=True) → dict {text,value,conf,raw,joined}
      - read_amount_from_variants(variants) → garde le meilleur des prétraitements
      - warmup() → charge les poids une fois (évite le pic à la 1ère requête)
    """
    def __init__(self, gpu: bool | None = None, langs: List[str] = ("en",)):
        # Choix GPU automatique si demandé + dispo
        if gpu is None:
            use_env = os.getenv("POKERIA_OCR_GPU", "auto")  # "1"/"0"/"auto"
            if use_env in {"1", "true", "TRUE"}:
                try:
                    import torch
                    gpu = bool(getattr(torch, "cuda", None) and torch.cuda.is_available())
                except Exception:
                    gpu = False
            elif use_env in {"0", "false", "FALSE"}:
                gpu = True
            else:
                try:
                    import torch
                    gpu = bool(getattr(torch, "cuda", None) and torch.cuda.is_available())
                except Exception:
                    gpu = True
        # Import tardif → charge les poids seulement si nécessaire
        import easyocr
        self.reader = easyocr.Reader(
            list(langs), gpu=bool(gpu), download_enabled=True, model_storage_directory='models/'
        )

    # ─────────── helpers parsing ───────────
    @staticmethod
    def _postfix_common_ocr_errors(s: str) -> str:
        """Corrections simples pour confusions fréquentes."""
        return (
            s.replace('O', '0')
             .replace('o', '0')
             .replace('S', '5')
             .replace('€', '')
             .replace(' ', '')
        )

    @staticmethod
    def _parse_amount(txt: str) -> Optional[float]:
        """'1.234,56' → 1234.56 ; '12,3' → 12.3 ; '12.3' → 12.3"""
        if not txt:
            return None
        t = EasyOCREngine._postfix_common_ocr_errors(txt)
        t = re.sub(r'[^0-9\.,]', '', t)  # garde chiffres/.,

        if ',' in t and '.' in t:
            # style EU avec milliers: 1.234,56 → 1234.56
            t = t.replace('.', '').replace(',', '.')
        elif ',' in t:
            t = t.replace(',', '.')

        try:
            return float(t)
        except Exception:
            return None

    # ─────────── API OCR générique ───────────
    def read_text(self, img_rgb, allowlist: Optional[str] = None) -> Tuple[str, float, list]:
        """Retourne (texte_concaténé, confiance_moyenne, résultats_bruts)."""
        kw = dict(detail=1, paragraph=False)
        if allowlist is not None:
            kw["allowlist"] = allowlist
        results = self.reader.readtext(img_rgb, **kw)
        if not results:
            return "", 0.0, []
        texts = [t for (_b, t, _c) in results if t]
        confs = [float(c) for (_b, _t, c) in results] or [0.0]
        return " ".join(texts), float(np.mean(confs)), results

    # ─────────── OCR montants (avec heuristiques) ───────────
    def read_amount(self, img_rgb, prefer_rightmost: bool = True) -> Dict[str, Any]:
        """
        Lit un montant en € dans une zone.
        Heuristique de choix:
          1) token avec décimales (xx,y / xx.y) prioritaire
          2) parmi ceux-ci, le plus à droite (souvent pot/stack)
          3) sinon, meilleure confiance
        Retour dict: {"text","value","conf","raw","joined"}.
        """
        results = self.reader.readtext(
            img_rgb, detail=1, paragraph=False, allowlist="0123456789€,."
        )
        joined = " ".join([t for (_box, t, _c) in results]) if results else ""

        candidates = []
        for (box, t, conf) in results:
            raw_t = t or ""
            t = self._postfix_common_ocr_errors(raw_t)
            t = re.sub(r"[^0-9\.,]", "", t)
            if not t:
                continue

            has_dec = bool(re.search(r"\d+[\.,]\d{1,2}$", t))  # finit par décimales (1 ou 2)
            tt = t
            if "," in tt and "." in tt:
                tt = tt.replace(".", "").replace(",", ".")
            elif "," in tt:
                tt = tt.replace(",", ".")

            try:
                val = float(tt)
            except Exception:
                continue

            xs = [p[0] for p in box]  # x-coords
            x_center = float(sum(xs) / max(1, len(xs)))
            candidates.append({
                "raw": raw_t, "clean": t, "value": val,
                "conf": float(conf), "x": x_center, "has_dec": has_dec
            })

        if candidates:
            candidates.sort(key=lambda d: (
                not d["has_dec"],
                -d["x"] if prefer_rightmost else d["x"],
                -d["conf"]
            ))
            best = candidates[0]
            return {
                "text": best["raw"],
                "value": best["value"],
                "conf": best["conf"],
                "raw": results,
                "joined": joined
            }

        # fallback: concat global
        txt, conf, raw = self.read_text(img_rgb, allowlist="0123456789€+.,-")
        val = self._parse_amount(txt)
        return {"text": txt, "value": val, "conf": conf, "raw": raw, "joined": txt}

    def read_amount_from_variants(self, variants: List[np.ndarray], prefer_rightmost: bool = True) -> Dict[str, Any]:
        """Donne plusieurs versions prétraitées → renvoie la meilleure lecture."""
        best: Dict[str, Any] = {"conf": -1.0, "value": None}
        for v in variants:
            out = self.read_amount(v, prefer_rightmost=prefer_rightmost)
            score = (1 if out.get("value") is not None else 0, float(out.get("conf", 0.0)))
            if score > (1 if best.get("value") is not None else 0, float(best.get("conf", 0.0))):
                best = out
        if best["conf"] < 0:  # rien lu
            return {"text": "", "value": None, "conf": 0.0, "raw": [], "joined": ""}
        return best

    # ─────────── Warmup ───────────
    def warmup(self):
        try:
            import numpy as np
            dummy = np.zeros((20, 80, 3), dtype=np.uint8)
            self.read_text(dummy, allowlist="0123456789TJQKAhdsc€.,-")
        except Exception:
            pass