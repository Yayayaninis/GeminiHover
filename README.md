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
- It is slightly transparent, and its background takes the average color of the area around it
  (150 px on each side), with light or dark text to stay readable.
- The title shows the model used, the number of messages in the conversation and the number of context items.
- Errors (missing key, no network, quota reached, blocked answer…) are shown in the popup, prefixed with ⚠.

### Automatic model choice

With `"model": "auto"`, the app lists the models available for your key and picks a Gemini **flash** model:
recent stable versions first, then *flash-lite*, then previews. If a model is overloaded, out of quota,
unavailable or does not answer in time, the next one is tried automatically. The model that worked last is
tried first the next time, even after a restart.

### Tray menu summary

| Menu item                     | Action |
|-------------------------------|--------|
| *Afficher la dernière réponse* | Show the last answer (also left-click) |
| *Nouvelle discussion*         | Forget the conversation (context is kept) |
| *Poser une question*          | Type a question |
| *Envoyer le presse-papier*    | Send the clipboard (image or text) |
| *Contexte*                    | Add files or text, view or clear the context |
| *Quitter*                     | Quit the app |

## Getting a Gemini API key

1. Go to [Google AI Studio](https://aistudio.google.com/apikey) and sign in with your Google account.
2. Click **Create API key** (create or pick a Google Cloud project if asked).
3. Copy the key. It looks like `AIza...`.

The free tier is enough for personal use. Keep the key private: never commit it or share it.
If it leaks, delete it in AI Studio and create a new one.

## Configuration

Next to `GeminiHover.exe`, create a file named `config.json` (you can copy `config.example.json`):

```json
{
  "api_key": "YOUR_GEMINI_API_KEY",
  "model": "auto"
}
```

| Field     | Description |
|-----------|-------------|
| `api_key` | Your Gemini API key. If empty, the `GEMINI_API_KEY` environment variable is used instead. |
| `model`   | `auto` (recommended) to pick an available flash model automatically, or an exact model name such as `gemini-3.5-flash-lite`. |

The app also creates `last_model.txt` next to the exe to remember which model worked last.
Delete it to let `auto` try the newest models first again.

To set the key as an environment variable instead (PowerShell):

```powershell
setx GEMINI_API_KEY "YOUR_GEMINI_API_KEY"
```

## Troubleshooting

- **"Raccourci Ctrl+Alt+G déjà utilisé"**: another application already uses this shortcut. Close it, or use
  the tray menu (*Poser une question*, *Envoyer le presse-papier*) instead.
- **"Clé API absente"**: `config.json` is missing, is not next to the exe, or has an empty `api_key`.
- **Nothing is sent when pressing `Ctrl+Alt+G`**: some apps block simulated copying. Copy manually with
  `Ctrl+C`, then use *Envoyer le presse-papier*.

## Project structure

| File                   | Role |
|------------------------|------|
| `app.py`               | Tray icon, global shortcut, popup, dialogs and context management (Tkinter + pystray). |
| `gemini.py`            | Gemini API calls: model ranking and fallback, conversation history, context files. Standard library only. |
| `tests/`               | Unit tests for `gemini.py` and the popup color detection. |
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
