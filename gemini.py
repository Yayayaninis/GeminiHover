import base64
import json
import re
import urllib.error
import urllib.request

LIST_URL = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200"
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiError(Exception):
    pass


def extract_text(payload):
    try:
        parts = payload["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip()
    except (KeyError, IndexError, TypeError):
        reason = (payload.get("promptFeedback") or {}).get("blockReason")
        raise GeminiError(f"Réponse vide ou bloquée ({reason or 'inconnu'}).")


_SKIP = ("lite", "image", "tts", "live", "audio", "embedding", "thinking", "robotics", "computer", "learnlm")


def _version(name):
    nums = re.findall(r"\d+(?:\.\d+)?", name)
    return float(nums[0]) if nums else 0.0


def rank_models(models):
    """Modèles flash utilisables, du préféré au moins préféré.

    Ordre : flash stables récents, puis flash-lite stables, puis previews.
    """
    names = [
        m["name"].split("/")[-1]
        for m in models
        if "generateContent" in m.get("supportedGenerationMethods", [])
    ]
    flash = [n for n in names if "flash" in n and not any(w in n for w in _SKIP if w != "lite")]
    if not flash:
        raise GeminiError("Aucun modèle flash disponible pour cette clé.")

    def score(n):
        stable = "preview" not in n and "exp" not in n
        return (stable, "lite" not in n, _version(n), "latest" not in n)

    return sorted(flash, key=score, reverse=True)


def list_models(api_key, timeout=30):
    req = urllib.request.Request(LIST_URL, headers={"x-goog-api-key": api_key})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp).get("models", [])


# Codes qui justifient d'essayer le modèle suivant : introuvable, surchargé, quota.
_RETRY_CODES = (404, 429, 500, 503)
_working_model = None


def build_parts(question, image_png=None):
    parts = [{"text": question}]
    if image_png:
        parts.append({"inline_data": {"mime_type": "image/png",
                                      "data": base64.b64encode(image_png).decode("ascii")}})
    return parts


def _generate(question, api_key, model, timeout, image_png=None):
    body = json.dumps({"contents": [{"parts": build_parts(question, image_png)}]}).encode("utf-8")
    req = urllib.request.Request(
        API_URL.format(model=model),
        data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return extract_text(json.load(resp))


def _http_message(e):
    try:
        return json.load(e)["error"]["message"]
    except Exception:
        return e.reason


def ask(question, api_key, model, timeout=20, image_png=None, preferred=None):
    """Renvoie (réponse, modèle utilisé).

    image_png : capture optionnelle (octets PNG). preferred : modèle à essayer en premier en mode auto.
    """
    global _working_model
    if not api_key:
        raise GeminiError("Clé API absente : renseigne api_key dans config.json ou GEMINI_API_KEY.")
    try:
        if model and model != "auto":
            candidates = [model]
        else:
            ranked = rank_models(list_models(api_key))
            first = _working_model or preferred
            if first in ranked:
                ranked.remove(first)
                ranked.insert(0, first)
            candidates = ranked
    except urllib.error.HTTPError as e:
        raise GeminiError(f"Impossible de lister les modèles ({e.code}) : {_http_message(e)}")
    except urllib.error.URLError as e:
        raise GeminiError(f"Réseau indisponible : {e.reason}")
    except TimeoutError:
        raise GeminiError("L'API ne répond pas (liste des modèles).")

    last = None
    for name in candidates:
        try:
            text = _generate(question, api_key, name, timeout, image_png)
            _working_model = name
            return text, name
        except urllib.error.HTTPError as e:
            last = f"Erreur API {e.code} ({name}) : {_http_message(e)}"
            if e.code not in _RETRY_CODES:
                break
        except TimeoutError:
            # Un modèle saturé peut ne jamais répondre au lieu de renvoyer 503 : on passe au suivant.
            last = f"Délai dépassé ({name}) : le modèle ne répond pas."
        except urllib.error.URLError as e:
            if isinstance(e.reason, TimeoutError):
                last = f"Délai dépassé ({name}) : le modèle ne répond pas."
                continue
            raise GeminiError(f"Réseau indisponible : {e.reason}")
    raise GeminiError(last or "Aucun modèle n'a répondu.")
