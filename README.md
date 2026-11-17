# GeminiHover

A small Windows tray app that sends questions to Google Gemini and shows the answer when you hover over its icon.
It runs in the background, has no main window, and works from any application.

## Features

### Asking questions

- **`Ctrl+Alt+G` on selected text**: select text in any app (browser, Word, PDF reader…) and press
  `Ctrl+Alt+G`. The selection is copied and sent to Gemini.
- **`Ctrl+Alt+G` on a screenshot**: if no text is selected but the clipboard holds an image
  (e.g. a capture taken with `Win+Shift+S`, an image copied from a browser, or an image file copied in the
  Explorer), the image is sent instead. A dialog asks for your question about it; leave it empty to let
  Gemini answer the question visible on the capture.
- **Type a question**: *Poser une question* in the tray menu opens a dialog.
- **Send the clipboard**: *Envoyer le presse-papier* sends what you already copied (image first, otherwise text),
  without needing a selection.

### Context (files and texts)

Under the **Contexte** tray menu:

| Menu item                 | What it does |
|---------------------------|--------------|
| *Ajouter des fichiers…*   | Pick one or more files. Text files (`.txt`, `.md`, `.csv`, `.json`, source code…), images (`.png`, `.jpg`, `.webp`, `.heic`) and PDFs are supported, up to 15 MB each. Binary files such as `.exe` or `.docx` are rejected with a message. |
| *Ajouter un texte…*       | Opens a large text box to paste or write a text. `Ctrl+Enter` adds it, `Esc` cancels. |
| *Voir le contexte*        | Lists the files and texts currently in context. |
| *Vider le contexte*       | Removes everything from the context. |

Context items are sent with **every** question until you clear them. Starting a new conversation keeps them.
When context is present, Gemini is given up to 60 seconds to answer (instead of 20) since large files take longer.

### Conversation memory

Gemini remembers the previous questions and answers, so you can ask follow-ups ("explain the second point").
The memory lasts until you choose *Nouvelle discussion* or quit the app. The popup title shows how many
messages the conversation contains.

### The answer popup

- **Hover the tray icon**: shows the last question and answer; it hides again when the mouse leaves
  both the icon and the popup.
- **Left-click the tray icon** (or *Afficher la dernière réponse*): opens the popup and keeps it open.
- After a question, the popup opens by itself, first with "Réflexion en cours…" and then with the answer.
  It stays open until you click **✕**.
- It appears at the bottom of the screen, near the mouse. It comes to the front once, then behaves like a normal
  window that other windows can cover.
- Long answers can be scrolled; the text can be selected and copied.
- It is semi-transparent, and its background takes the average color of the area around it
  (150 px on each side by default), with light or dark text to stay readable. Both can be changed in *Paramètres*.
- The title shows the model used, the number of messages in the conversation and the number of context items.
- Errors (missing key, no network, quota reached, blocked answer…) are shown in the popup, prefixed with ⚠.

### Automatic model choice

With `"model": "auto"`, the app lists the models available for your key and picks a Gemini **flash** model:
recent stable versions first, then *flash-lite*, then previews. If a model is overloaded, out of quota,
unavailable or does not answer in time, the next one is tried automatically. The model that worked last is
tried first the next time, even after a restart.

### Settings panel

*Paramètres…* in the tray menu opens a window with two tabs. Changes apply as soon as you click
**Enregistrer** (no restart needed) and are saved in `config.json`. **Valeurs par défaut** resets every field
except the API key.

| Tab       | Setting                 | Description |
|-----------|-------------------------|-------------|
| Gemini    | Clé API                 | Your API key (hidden; tick *Afficher* to see it). |
| Gemini    | Modèle                  | `auto`, or a model picked from the list (*Actualiser la liste* fetches the models available for your key). |
| Gemini    | Délai de réponse        | Seconds to wait for an answer (at least 60 when context is present). |
| Gemini    | Raccourci               | Global shortcut, e.g. `Ctrl+Alt+G` or `Ctrl+Shift+F2` (Ctrl, Alt, Shift, Win + a letter, digit or F1–F12). |
| Gemini    | Instructions permanentes | Instructions applied to every answer, e.g. "Réponds en français, en 3 phrases maximum." |
| Fenêtre   | Opacité                 | From 20 % (very transparent) to 100 % (opaque). |
| Fenêtre   | Fond                    | Color of the area around the popup, or a fixed color of your choice. |
| Fenêtre   | Zone analysée           | Size in pixels of the area around the popup used for the automatic color. |
| Fenêtre   | Taille du texte, Largeur, Hauteur max | Font size, width in characters, and number of lines before scrolling. |

### Tray menu summary

| Menu item                     | Action |
|-------------------------------|--------|
| *Afficher la dernière réponse* | Show the last answer (also left-click) |
| *Nouvelle discussion*         | Forget the conversation (context is kept) |
| *Poser une question*          | Type a question |
| *Envoyer le presse-papier*    | Send the clipboard (image or text) |
| *Contexte*                    | Add files or text, view or clear the context |
| *Paramètres…*                 | Open the settings panel |
| *Quitter*                     | Quit the app |

## Getting a Gemini API key

1. Go to [Google AI Studio](https://aistudio.google.com/apikey) and sign in with your Google account.
2. Click **Create API key** (create or pick a Google Cloud project if asked).
3. Copy the key. It looks like `AIza...`.

The free tier is enough for personal use. Keep the key private: never commit it or share it.
If it leaks, delete it in AI Studio and create a new one.

## Configuration

The easiest way is the **settings panel** (*Paramètres…*): paste your API key and click *Enregistrer*.
It creates `config.json` next to `GeminiHover.exe`.

You can also write `config.json` by hand (you can copy `config.example.json`). Only `api_key` is required;
missing fields use the defaults below.

```json
{
  "api_key": "YOUR_GEMINI_API_KEY",
  "model": "auto"
}
```

| Field          | Default      | Description |
|----------------|--------------|-------------|
| `api_key`      | `""`         | Your Gemini API key. If empty, the `GEMINI_API_KEY` environment variable is used instead. |
| `model`        | `auto`       | `auto` (recommended) to pick an available flash model automatically, or an exact model name such as `gemini-3.5-flash-lite`. |
| `timeout`      | `20`         | Seconds to wait for an answer. |
| `instructions` | `""`         | Permanent instructions sent to Gemini with every question. |
| `hotkey`       | `Ctrl+Alt+G` | Global shortcut. |
| `opacity`      | `0.5`        | Popup opacity, from `0.2` to `1`. |
| `color_mode`   | `auto`       | `auto` (color of the area around the popup) or `fixed`. |
| `fixed_color`  | `#202124`    | Background color used when `color_mode` is `fixed`. |
| `around`       | `150`        | Pixels around the popup used for the automatic color. |
| `font_size`    | `10`         | Popup text size. |
| `width`        | `60`         | Popup width, in characters. |
| `max_lines`    | `22`         | Lines shown before a scroll bar appears. |

The app also creates `last_model.txt` next to the exe to remember which model worked last.
Delete it to let `auto` try the newest models first again.

To set the key as an environment variable instead (PowerShell):

```powershell
setx GEMINI_API_KEY "YOUR_GEMINI_API_KEY"
```

## Troubleshooting

- **"Raccourci … déjà utilisé"**: another application already uses this shortcut. Pick another one in
  *Paramètres*, or use the tray menu (*Poser une question*, *Envoyer le presse-papier*) instead.
- **"Clé API absente"**: `config.json` is missing, is not next to the exe, or has an empty `api_key`.
- **Nothing is sent when pressing `Ctrl+Alt+G`**: some apps block simulated copying. Copy manually with
  `Ctrl+C`, then use *Envoyer le presse-papier*.

## Project structure

| File                   | Role |
|------------------------|------|
| `app.py`               | Tray icon, global shortcut, popup, dialogs and context management (Tkinter + pystray). |
| `gemini.py`            | Gemini API calls: model ranking and fallback, conversation history, context files. Standard library only. |
| `settings.py`          | Default settings, reading and writing `config.json`, shortcut parsing and the settings window. |
| `tests/`               | Unit tests for `gemini.py`, `settings.py` and the popup color detection. |
| `config.example.json`  | Configuration template. |
| `GeminiHover.spec`     | PyInstaller build settings. |

## Building from source

Requires Python 3 on Windows.

```powershell
pip install -r requirements.txt
python -m PyInstaller --onefile --noconsole --name GeminiHover app.py
```

The executable is created in `dist\GeminiHover.exe`. Put your `config.json` in the same folder and run it.

## Tests

```powershell
python -m unittest discover tests
```
