# GeminiHover

Petite application Windows dans la zone de notification qui envoie une question à Gemini
et affiche la réponse au survol de l'icône.

- `Ctrl+Alt+G` : envoie le texte sélectionné, ou la capture d'écran du presse-papier (`Win+Shift+S`).
- Clic gauche sur l'icône : réaffiche la dernière réponse.
- Clic droit : poser une question, envoyer le presse-papier, quitter.

## Installation

```
pip install -r requirements.txt
python -m PyInstaller --onefile --noconsole --name GeminiHover app.py
```

Copier `config.example.json` en `config.json` à côté de `dist\GeminiHover.exe` et y mettre sa clé API
(ou définir la variable d'environnement `GEMINI_API_KEY`).

## Tests

```
python -m unittest discover tests
```
