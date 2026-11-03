import ctypes
import io
import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
from ctypes import wintypes
from tkinter import simpledialog

import pystray
from PIL import Image, ImageDraw, ImageGrab

import gemini

HOTKEY_ID = 1
MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x1, 0x2, 0x4000
VK_G = 0x47
WM_HOTKEY = 0x0312
KEYEVENTF_KEYUP = 0x2
VK_CONTROL, VK_MENU, VK_SHIFT, VK_C = 0x11, 0x12, 0x10, 0x43
MAX_LINES = 22
MAX_IMAGE_SIDE = 2048
IMAGE_PROMPT = "Réponds à la question visible sur cette capture d'écran."

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32


def app_dir():
    base = sys.executable if getattr(sys, "frozen", False) else __file__
    return os.path.dirname(os.path.abspath(base))


def load_config():
    cfg = {"api_key": "", "model": "auto"}
    path = os.path.join(app_dir(), "config.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg.update(json.load(f))
    cfg["api_key"] = cfg["api_key"] or os.environ.get("GEMINI_API_KEY", "")
    return cfg


def last_model_path():
    return os.path.join(app_dir(), "last_model.txt")


def load_last_model():
    try:
        with open(last_model_path(), encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def save_last_model(name):
    try:
        with open(last_model_path(), "w", encoding="utf-8") as f:
            f.write(name)
    except OSError:
        pass


def make_icon_image():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, 60, 60), fill=(66, 133, 244, 255))
    d.polygon([(32, 14), (38, 26), (50, 32), (38, 38), (32, 50), (26, 38), (14, 32), (26, 26)], fill="white")
    return img


class NOTIFYICONIDENTIFIER(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("guidItem", ctypes.c_byte * 16),
    ]


def icon_rect(icon):
    """Rectangle écran de l'icône de notification, ou None."""
    ident = NOTIFYICONIDENTIFIER()
    ident.cbSize = ctypes.sizeof(ident)
    ident.hWnd = icon._hwnd
    ident.uID = id(icon) & 0xFFFFFFFF
    rect = wintypes.RECT()
    if shell32.Shell_NotifyIconGetRect(ctypes.byref(ident), ctypes.byref(rect)) != 0:
        return None
    return rect.left, rect.top, rect.right, rect.bottom


def cursor_pos():
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def inside(pt, rect, margin=0):
    return rect[0] - margin <= pt[0] <= rect[2] + margin and rect[1] - margin <= pt[1] <= rect[3] + margin


def screen_colors():
    """(fond, texte, bordure) : couleur majoritaire de l'écran, blanc si la capture échoue."""
    try:
        img = ImageGrab.grab().convert("RGB").resize((96, 54))
        # Regroupe les teintes proches pour qu'un dégradé compte comme une seule couleur.
        quant = img.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
        palette = quant.getpalette()
        _, idx = max(quant.getcolors())
        r, g, b = palette[idx * 3: idx * 3 + 3]
    except Exception:
        r, g, b = 255, 255, 255
    dark = 0.299 * r + 0.587 * g + 0.114 * b < 140
    bg = f"#{r:02x}{g:02x}{b:02x}"
    return bg, ("#f1f3f4" if dark else "#202124"), ("#8ab4f8" if dark else "#4285f4")


def clipboard_image_png():
    """Octets PNG de l'image du presse-papier (capture Win+Shift+S, image copiée…), ou None."""
    try:
        img = ImageGrab.grabclipboard()
    except Exception:
        return None
    if isinstance(img, list):  # fichiers copiés depuis l'Explorateur : prend la première image
        img = next((_open_image(p) for p in img if _open_image(p)), None)
    if not isinstance(img, Image.Image):
        return None
    img = img.convert("RGB")
    img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _open_image(path):
    try:
        return Image.open(path)
    except Exception:
        return None


def key(vk, up=False):
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP if up else 0, 0)


def send_copy():
    for vk in (VK_MENU, VK_SHIFT, VK_CONTROL):  # relâche le raccourci avant d'envoyer Ctrl+C
        key(vk, up=True)
    time.sleep(0.05)
    key(VK_CONTROL)
    key(VK_C)
    key(VK_C, up=True)
    key(VK_CONTROL, up=True)
    time.sleep(0.15)


class App:
    def __init__(self):
        self.cfg = load_config()
        self.events = queue.Queue()
        self.answer = "Aucune question pour l'instant.\nSélectionne du texte puis Ctrl+Alt+G."
        self.question = ""
        self.root = tk.Tk()
        self.root.withdraw()
        self.popup = None
        self.hovering = False
        self.sticky = False  # ouverte par une question ou un clic : reste jusqu'à la croix
        self.model_used = ""
        self.popup_body = None
        self.icon = pystray.Icon(
            "gemini-hover",
            make_icon_image(),
            "Gemini",
            menu=pystray.Menu(
                pystray.MenuItem("Afficher la dernière réponse", lambda: self.events.put(("reopen",)),
                                 default=True),  # aussi déclenché par le clic gauche
                pystray.MenuItem("Poser une question", lambda: self.events.put(("ask",))),
                pystray.MenuItem("Envoyer le presse-papier", lambda: self.events.put(("clipboard",))),
                pystray.MenuItem("Quitter", lambda: self.events.put(("quit",))),
            ),
        )

    # --- popup -----------------------------------------------------------
    def build_popup(self):
        p = tk.Toplevel(self.root)
        p.withdraw()
        p.overrideredirect(True)
        p.configure(highlightthickness=1)
        header = tk.Frame(p)
        header.pack(fill="x")
        self.popup_title = tk.Label(header, font=("Segoe UI", 8), anchor="w", padx=10, pady=4)
        self.popup_title.pack(side="left", fill="x", expand=True)
        close = tk.Label(header, text="✕", font=("Segoe UI", 11), padx=10, cursor="hand2")
        close.pack(side="right")
        close.bind("<Button-1>", lambda _e: self.hide_popup())
        body = tk.Frame(p)
        body.pack(fill="both", expand=True, padx=(10, 2), pady=(0, 8))
        self.popup_scroll = tk.Scrollbar(body)
        self.popup_body = tk.Text(body, font=("Segoe UI", 10), wrap="word", width=60, height=4,
                                  relief="flat", borderwidth=0, highlightthickness=0, padx=0, pady=2,
                                  yscrollcommand=self.popup_scroll.set, cursor="arrow")
        self.popup_scroll.config(command=self.popup_body.yview)
        self.popup_body.pack(side="left", fill="both", expand=True)
        self.popup_widgets = (p, header, body, self.popup_title, close, self.popup_body)
        self.popup = p

    def apply_colors(self):
        bg, fg, border = screen_colors()
        for w in self.popup_widgets:
            w.configure(bg=bg)
        for w in self.popup_widgets[3:]:
            w.configure(fg=fg)
        self.popup_body.configure(insertbackground=fg, selectbackground=border)
        self.popup.configure(highlightbackground=border, highlightcolor=border)

    def refresh_popup(self):
        head = f"Q : {self.question[:300]}\n\n" if self.question else ""
        b = self.popup_body
        b.config(state="normal")
        b.delete("1.0", "end")
        b.insert("1.0", head + self.answer)
        # Hauteur adaptée au texte, plafonnée ; au-delà, barre de défilement.
        b.update_idletasks()
        lines = b.count("1.0", "end", "displaylines")[0] or 1
        b.config(height=min(lines, MAX_LINES), state="disabled")  # lecture seule mais sélectionnable
        if lines > MAX_LINES:
            self.popup_scroll.pack(side="right", fill="y")
        else:
            self.popup_scroll.pack_forget()
        self.popup_title.config(text=f"Gemini · {self.model_used}" if self.model_used else "Gemini")

    def show_popup(self, sticky=False):
        was_visible = self.popup_visible()
        self.sticky = self.sticky or sticky
        if not was_visible:
            self.apply_colors()  # capture avant affichage pour ne pas mesurer la popup elle-même
        self.refresh_popup()
        self.popup.update_idletasks()
        w, h = self.popup.winfo_reqwidth(), self.popup.winfo_reqheight()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        if not was_visible:
            self.anchor_x = cursor_pos()[0]
        x = min(self.anchor_x - w // 2, sw - w - 8)
        self.popup.geometry(f"+{max(x, 8)}+{max(sh - h - 56, 8)}")
        self.popup.deiconify()
        # Passe devant une fois, puis redevient une fenêtre normale qu'on peut recouvrir.
        self.popup.attributes("-topmost", True)
        self.popup.lift()
        self.popup.after(200, lambda: self.popup.attributes("-topmost", False))

    def hide_popup(self):
        self.sticky = False
        self.popup.withdraw()

    def popup_visible(self):
        return self.popup.state() == "normal"

    def popup_rect(self):
        p = self.popup
        return p.winfo_rootx(), p.winfo_rooty(), p.winfo_rootx() + p.winfo_width(), p.winfo_rooty() + p.winfo_height()

    # --- thèmes de fond --------------------------------------------------
    def hover_loop(self):
        while True:
            time.sleep(0.12)
            rect = icon_rect(self.icon)
            pt = cursor_pos()
            if rect and inside(pt, rect):
                self.events.put(("hover", True))
            else:
                self.events.put(("hover", False))

    def hotkey_loop(self):
        if not user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_G):
            self.events.put(("error", "Raccourci Ctrl+Alt+G déjà utilisé par une autre application."))
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                self.events.put(("hotkey",))

    def query(self, text, image_png=None, label=None):
        self.question = label or text
        self.answer = "Réflexion en cours…"
        self.events.put(("show",))

        def work():
            try:
                self.answer, self.model_used = gemini.ask(
                    text, self.cfg["api_key"], self.cfg["model"], image_png=image_png,
                    preferred=load_last_model())
                save_last_model(self.model_used)
            except gemini.GeminiError as e:
                self.answer = f"⚠ {e}"
            except Exception as e:
                self.answer = f"⚠ Erreur inattendue : {e}"
            self.events.put(("show",))

        threading.Thread(target=work, daemon=True).start()

    def query_image(self, image_png):
        text = simpledialog.askstring(
            "Gemini — capture d'écran",
            "Ta question sur la capture (laisser vide = répondre à la question visible) :",
            parent=self.root)
        if text is None:  # Annuler
            return
        text = text.strip()
        self.query(text or IMAGE_PROMPT, image_png,
                   label=f"[capture d'écran] {text}".strip())

    def clipboard_text(self):
        try:
            return self.root.clipboard_get().strip()
        except tk.TclError:
            return ""

    def grab_selection(self):
        """Copie la sélection. Renvoie (texte, None), (None, image) ou (None, None).

        On ne vide pas le presse-papier avant Ctrl+C pour ne pas effacer une capture :
        le numéro de séquence dit si quelque chose de nouveau a été copié.
        """
        before = user32.GetClipboardSequenceNumber()
        send_copy()
        if user32.GetClipboardSequenceNumber() != before:
            text = self.clipboard_text()
            if text:
                return text, None
        return None, clipboard_image_png()

    # --- boucle principale (thread Tk) -------------------------------------
    def pump(self):
        hovering = self.hovering
        try:
            while True:
                ev = self.events.get_nowait()
                kind = ev[0]
                if kind == "hover":
                    hovering = self.hovering = ev[1]
                    if hovering and not self.popup_visible():
                        self.show_popup()
                elif kind == "show":
                    self.show_popup(sticky=True)
                elif kind == "reopen":
                    self.show_popup(sticky=True)
                elif kind == "hotkey":
                    text, image = self.grab_selection()
                    if text:
                        self.query(text)
                    elif image:
                        self.query_image(image)
                    else:
                        self.question = ""
                        self.answer = "Aucun texte sélectionné ni capture dans le presse-papier."
                        self.show_popup(sticky=True)
                elif kind == "clipboard":
                    image = clipboard_image_png()
                    text = self.clipboard_text()
                    if image:
                        self.query_image(image)
                    elif text:
                        self.query(text)
                elif kind == "ask":
                    text = simpledialog.askstring("Gemini", "Ta question :", parent=self.root)
                    if text and text.strip():
                        self.query(text.strip())
                elif kind == "error":
                    self.answer = f"⚠ {ev[1]}"
                elif kind == "quit":
                    self.icon.stop()
                    self.root.destroy()
                    return
        except queue.Empty:
            pass
        self.update_visibility(hovering)
        self.root.after(80, self.pump)

    def update_visibility(self, hovering):
        if not self.popup_visible() or self.sticky:
            return
        if not (hovering or inside(cursor_pos(), self.popup_rect(), 4)):
            self.hide_popup()

    def run(self):
        self.build_popup()
        self.icon.run_detached()
        threading.Thread(target=self.hover_loop, daemon=True).start()
        threading.Thread(target=self.hotkey_loop, daemon=True).start()
        self.root.after(80, self.pump)
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
