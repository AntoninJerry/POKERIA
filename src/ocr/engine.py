import re
import cv2
import numpy as np
from typing import Optional, Dict, Any, List

class EasyOCREngine:
    def __init__(self, gpu: bool = False, langs: List[str] = ['en']):
        # import tardif pour éviter les coûts si non utilisé
        import easyocr
        self.reader = easyocr.Reader(
            langs, gpu=gpu, download_enabled=True, model_storage_directory='models/'
        )

    @staticmethod
    def _postfix_common_ocr_errors(s: str) -> str:
        # corrections courantes
        s = s.replace('O', '0')
        s = s.replace('o', '0')
        s = s.replace('S', '5')
        s = s.replace('€', '')
        s = s.replace(' ', '')
        return s

    @staticmethod
    def _parse_amount(txt: str) -> Optional[float]:
        if not txt:
            return None
        t = EasyOCREngine._postfix_common_ocr_errors(txt)
        # garder seulement chiffres .,,
        t = re.sub(r'[^0-9\.,]', '', t)

        # cas EU: "1.234,56" → "1234.56"
        if ',' in t and '.' in t:
            t = t.replace('.', '').replace(',', '.')
        elif ',' in t:
            t = t.replace(',', '.')
        try:
            return float(t)
        except Exception:
            return None

    def read_text(self, img_rgb, allowlist: Optional[str] = None):
        """
        Retourne (text_concat, conf_moy, raw_results).
        """
        kw = dict(detail=1, paragraph=False)
        if allowlist is not None:
            kw["allowlist"] = allowlist
        results = self.reader.readtext(img_rgb, **kw)
        if not results:
            return "", 0.0, []
        texts = [t for (_, t, _) in results]
        confs = [float(c) for (_, _, c) in results]
        return " ".join(texts), float(np.mean(confs)), results

    def read_amount(self, img_rgb, prefer_rightmost: bool = True):
        import re
        results = self.reader.readtext(
            img_rgb, detail=1, paragraph=False, allowlist="0123456789€,."
        )
        joined = " ".join([t for (_, t, _) in results]) if results else ""

        # extraire des candidats par token
        cands = []
        for (box, t, conf) in results:
            raw = t
            t = self._postfix_common_ocr_errors(t)
            t = re.sub(r"[^0-9\.,]", "", t)
            if not t:
                continue

            # marqueur "a un séparateur décimal"
            has_dec = bool(re.search(r"\d+[\.,]\d{1,2}$", t))

            # normalisation EU -> float
            tt = t
            if "," in tt and "." in tt:
                tt = tt.replace(".", "").replace(",", ".")
            elif "," in tt:
                tt = tt.replace(",", ".")

            try:
                val = float(tt)
            except Exception:
                continue

            xs = [p[0] for p in box]
            x_center = float(sum(xs) / len(xs))
            cands.append({
                "raw": raw, "clean": t, "value": val,
                "conf": float(conf), "x": x_center, "has_dec": has_dec
            })

        if cands:
            # Règle: (1) préfère un token avec décimales, (2) le plus à droite, (3) meilleure confiance
            cands.sort(key=lambda d: (not d["has_dec"], -d["x"] if prefer_rightmost else d["x"], -d["conf"]))
            best = cands[0]
            return {"text": best["raw"], "value": best["value"], "conf": best["conf"], "raw": results, "joined": joined}

        # fallback concaténé (rare)
        txt, conf, raw = self.read_text(img_rgb, allowlist="0123456789€,.")
        val = self._parse_amount(txt)
        return {"text": txt, "value": val, "conf": conf, "raw": raw, "joined": txt}

