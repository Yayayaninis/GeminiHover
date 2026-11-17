"""Communication avec l'API Google Gemini (aucune dépendance externe : seulement la bibliothèque standard)."""

import base64  # encode les fichiers binaires (images, PDF) en texte pour les mettre dans du JSON
import json  # construit le corps des requêtes et lit les réponses de l'API
import os  # nom, taille et extension des fichiers de contexte
import re  # expressions régulières, pour extraire le numéro de version d'un nom de modèle
import urllib.error  # exceptions réseau / HTTP
import urllib.request  # envoi des requêtes HTTP

# Adresse qui liste tous les modèles accessibles avec la clé (200 par page, assez pour tout avoir).
LIST_URL = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200"
# Adresse qui génère une réponse ; {model} est remplacé par le nom du modèle choisi.
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiError(Exception):
    """Erreur « propre » dont le message est affiché tel quel à l'utilisateur dans la popup."""
    pass


def extract_text(payload):
    """Récupère le texte de la réponse JSON renvoyée par Gemini."""
    try:
        # La réponse ressemble à {"candidates": [{"content": {"parts": [{"text": "..."}]}}]}.
        parts = payload["candidates"][0]["content"]["parts"]
        # Une réponse peut être découpée en plusieurs morceaux : on les recolle.
        return "".join(p.get("text", "") for p in parts).strip()
    except (KeyError, IndexError, TypeError):
        # Pas de candidat : en général la question a été bloquée (filtre de sécurité…).
        reason = (payload.get("promptFeedback") or {}).get("blockReason")
        raise GeminiError(f"Réponse vide ou bloquée ({reason or 'inconnu'}).")


# Mots qui signalent un modèle spécialisé (image, voix…) qu'on ne veut pas utiliser pour du texte.
_SKIP = ("lite", "image", "tts", "live", "audio", "embedding", "thinking", "robotics", "computer", "learnlm")


def _version(name):
    """Numéro de version d'un nom de modèle : "gemini-2.5-flash" -> 2.5 (0 si aucun)."""
    nums = re.findall(r"\d+(?:\.\d+)?", name)
    return float(nums[0]) if nums else 0.0


def rank_models(models):
    """Modèles flash utilisables, du préféré au moins préféré.

    Ordre : flash stables récents, puis flash-lite stables, puis previews.
    """
    # Garde seulement le nom court ("models/gemini-2.5-flash" -> "gemini-2.5-flash")
    # des modèles capables de générer du texte.
    names = [
        m["name"].split("/")[-1]
        for m in models
        if "generateContent" in m.get("supportedGenerationMethods", [])
    ]
    # Garde les modèles "flash" (rapides et gratuits) qui ne sont pas spécialisés.
    # "lite" est toléré ici : les flash-lite servent de solution de secours.
    flash = [n for n in names if "flash" in n and not any(w in n for w in _SKIP if w != "lite")]
    if not flash:
        raise GeminiError("Aucun modèle flash disponible pour cette clé.")

    def score(n):
        # Python compare les tuples élément par élément : d'abord stable, puis non-lite,
        # puis la version la plus haute, puis un nom précis plutôt qu'un alias "latest".
        stable = "preview" not in n and "exp" not in n
        return (stable, "lite" not in n, _version(n), "latest" not in n)

    # reverse=True : le meilleur score en premier.
    return sorted(flash, key=score, reverse=True)


def list_models(api_key, timeout=30):
    """Demande à l'API la liste brute des modèles disponibles."""
    req = urllib.request.Request(LIST_URL, headers={"x-goog-api-key": api_key})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp).get("models", [])


# Codes qui justifient d'essayer le modèle suivant : introuvable, surchargé, quota.
_RETRY_CODES = (404, 429, 500, 503)
# Dernier modèle qui a répondu ; essayé en premier la fois suivante (gardé en mémoire).
_working_model = None


def build_parts(question, image_png=None):
    """Morceaux ("parts") d'un message : le texte de la question, plus l'image éventuelle."""
    parts = [{"text": question}]
    if image_png:
        # Les fichiers binaires sont envoyés encodés en base64 avec leur type MIME.
        parts.append({"inline_data": {"mime_type": "image/png",
                                      "data": base64.b64encode(image_png).decode("ascii")}})
    return parts


# Types envoyés tels quels à Gemini ; les autres fichiers sont lus comme du texte.
_BINARY_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
    ".heic": "image/heic", ".heif": "image/heif", ".pdf": "application/pdf",
}
MAX_CONTEXT_FILE = 15 * 1024 * 1024  # l'API refuse les requêtes de plus de 20 Mo
# Phrase placée avant le contexte pour que Gemini comprenne à quoi il sert.
CONTEXT_INTRO = "Contexte fourni par l'utilisateur, à utiliser pour répondre :"


def file_context_part(path):
    """Part Gemini pour un fichier de contexte (texte, image ou PDF)."""
    name = os.path.basename(path)  # "C:\dossier\cours.pdf" -> "cours.pdf"
    try:
        size = os.path.getsize(path)
        if size > MAX_CONTEXT_FILE:
            raise GeminiError(f"{name} est trop gros ({size // (1024 * 1024)} Mo, maximum 15 Mo).")
        with open(path, "rb") as f:  # "rb" : lecture en octets bruts, quel que soit le type
            data = f.read()
    except OSError as e:  # fichier supprimé, droits insuffisants…
        raise GeminiError(f"Impossible de lire {name} : {e.strerror or e}")
    # Type MIME d'après l'extension (en minuscules) ; None si ce n'est ni une image ni un PDF.
    mime = _BINARY_MIME.get(os.path.splitext(name)[1].lower())
    if mime:
        return {"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode("ascii")}}
    # Un octet nul est le signe d'un fichier binaire (exe, zip, docx…) : impossible à lire en texte.
    if b"\0" in data[:8192]:
        raise GeminiError(f"{name} : type de fichier non pris en charge (texte, image ou PDF uniquement).")
    try:
        text = data.decode("utf-8-sig")  # UTF-8, en ignorant l'éventuelle signature BOM
    except UnicodeDecodeError:
        # Vieux fichiers Windows (Bloc-notes ancien, Excel CSV…) : encodage cp1252.
        text = data.decode("cp1252", errors="replace")
    # Le nom du fichier est indiqué pour que Gemini puisse y faire référence.
    return {"text": f"[Fichier : {name}]\n{text}"}


def text_context_part(text):
    """Part Gemini pour un texte collé par l'utilisateur."""
    return {"text": f"[Texte]\n{text}"}


def build_contents(question, image_png=None, history=None, context=None):
    """Messages précédents de la discussion suivis de la nouvelle question.

    context : parts (voir file_context_part / text_context_part) jointes à la nouvelle question.
    Elles ne sont pas gardées dans l'historique : elles sont renvoyées à chaque question.
    """
    parts = build_parts(question, image_png)
    if context:
        # Message final : intro, éléments de contexte, puis la question elle-même.
        parts = [{"text": CONTEXT_INTRO}] + list(context) + [{"text": "Question :"}] + parts
    # list(...) crée une copie : on ne modifie pas l'historique de l'appelant.
    return list(history or []) + [{"role": "user", "parts": parts}]


def add_turn(history, question, answer, image_png=None):
    """Ajoute un échange question/réponse à l'historique (modifié en place)."""
    history.append({"role": "user", "parts": build_parts(question, image_png)})
    history.append({"role": "model", "parts": [{"text": answer}]})


def _generate(question, api_key, model, timeout, image_png=None, history=None, context=None):
    """Envoie une requête à UN modèle précis et renvoie le texte de sa réponse."""
    body = json.dumps({"contents": build_contents(question, image_png, history, context)}).encode("utf-8")
    req = urllib.request.Request(
        API_URL.format(model=model),
        data=body,  # avec un corps, urllib envoie une requête POST
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return extract_text(json.load(resp))


def _http_message(e):
    """Message d'erreur lisible fourni par l'API, ou à défaut la raison HTTP standard."""
    try:
        return json.load(e)["error"]["message"]
    except Exception:
        return e.reason


def ask(question, api_key, model, timeout=20, image_png=None, preferred=None, history=None, context=None):
    """Renvoie (réponse, modèle utilisé).

    image_png : capture optionnelle (octets PNG). preferred : modèle à essayer en premier en mode auto.
    history : échanges précédents (voir add_turn), pour garder le fil de la discussion.
    context : fichiers / textes de contexte (parts) joints à la question.
    """
    global _working_model  # on va modifier la variable du module, pas en créer une locale
    if not api_key:
        raise GeminiError("Clé API absente : renseigne api_key dans config.json ou GEMINI_API_KEY.")

    # 1) Liste des modèles à essayer, dans l'ordre.
    try:
        if model and model != "auto":
            candidates = [model]  # modèle imposé dans config.json
        else:
            ranked = rank_models(list_models(api_key))
            # Remonte en tête le modèle qui a marché la dernière fois (cette session ou la précédente).
            first = _working_model or preferred
            if first in ranked:
                ranked.remove(first)
                ranked.insert(0, first)
            candidates = ranked
    except urllib.error.HTTPError as e:  # l'API a répondu avec un code d'erreur (clé invalide…)
        raise GeminiError(f"Impossible de lister les modèles ({e.code}) : {_http_message(e)}")
    except urllib.error.URLError as e:  # pas de connexion
        raise GeminiError(f"Réseau indisponible : {e.reason}")
    except TimeoutError:
        raise GeminiError("L'API ne répond pas (liste des modèles).")

    # 2) Essaie les modèles un par un jusqu'à ce que l'un réponde.
    last = None  # dernière erreur rencontrée, affichée si tous échouent
    for name in candidates:
        try:
            text = _generate(question, api_key, name, timeout, image_png, history=history, context=context)
            _working_model = name
            return text, name
        except urllib.error.HTTPError as e:
            last = f"Erreur API {e.code} ({name}) : {_http_message(e)}"
            # Une erreur qui ne dépend pas du modèle (ex. 400 requête invalide) : inutile d'insister.
            if e.code not in _RETRY_CODES:
                break
        except TimeoutError:
            # Un modèle saturé peut ne jamais répondre au lieu de renvoyer 503 : on passe au suivant.
            last = f"Délai dépassé ({name}) : le modèle ne répond pas."
        except urllib.error.URLError as e:
            # Selon les cas, urllib emballe le délai dépassé dans une URLError.
            if isinstance(e.reason, TimeoutError):
                last = f"Délai dépassé ({name}) : le modèle ne répond pas."
                continue
            raise GeminiError(f"Réseau indisponible : {e.reason}")
    raise GeminiError(last or "Aucun modèle n'a répondu.")
