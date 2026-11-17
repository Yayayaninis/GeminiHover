"""Paramètres de l'application : valeurs par défaut, lecture / écriture de config.json et fenêtre de réglages."""

import json
import os
import sys
import tkinter as tk
from tkinter import colorchooser, messagebox, ttk

import gemini

# Valeurs utilisées quand config.json ne précise rien.
DEFAULTS = {
    "api_key": "",
    "model": "auto",
    "timeout": 20,  # secondes d'attente d'une réponse (60 au minimum avec du contexte)
    "instructions": "",  # consignes permanentes envoyées à Gemini (langue, ton, longueur…)
    "hotkey": "Ctrl+Alt+G",
    "opacity": 0.5,  # 1 = opaque, 0 = invisible
    "color_mode": "auto",  # "auto" : couleur de la zone autour ; "fixed" : fixed_color
    "fixed_color": "#202124",
    "around": 150,  # marge (pixels) autour de la popup pour la couleur moyenne
    "font_size": 10,
    "width": 60,  # largeur de la popup, en caractères
    "max_lines": 22,  # au-delà, barre de défilement
}

# Codes Windows des touches modificatrices pour RegisterHotKey.
MODIFIERS = {"CTRL": 0x2, "ALT": 0x1, "SHIFT": 0x4, "WIN": 0x8}


def app_dir():
    """Dossier de l'exe (version compilée) ou du script (version Python)."""
    base = sys.executable if getattr(sys, "frozen", False) else __file__
    return os.path.dirname(os.path.abspath(base))


def config_path():
    return os.path.join(app_dir(), "config.json")


def read_config_file():
    """Contenu brut de config.json ({} s'il est absent ou illisible)."""
    try:
        with open(config_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load_config():
    """Paramètres complets : valeurs par défaut, remplacées par celles de config.json."""
    cfg = dict(DEFAULTS)
    cfg.update(read_config_file())
    # Clé absente du fichier : on essaie la variable d'environnement.
    cfg["api_key"] = cfg["api_key"] or os.environ.get("GEMINI_API_KEY", "")
    return cfg


def save_config(cfg):
    """Écrit les paramètres dans config.json (lisible et modifiable à la main)."""
    data = dict(cfg)
    # Ne recopie pas dans le fichier une clé qui vient seulement de la variable d'environnement.
    if data["api_key"] == os.environ.get("GEMINI_API_KEY") and not read_config_file().get("api_key"):
        data["api_key"] = ""
    with open(config_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def parse_hotkey(text):
    """"Ctrl+Alt+G" -> (modificateurs, code de touche Windows). Lève ValueError si invalide."""
    keys = [k.strip().upper() for k in text.split("+") if k.strip()]
    if len(keys) < 2:
        raise ValueError("Il faut au moins une touche modificatrice et une touche, ex. Ctrl+Alt+G.")
    *mods, key = keys
    unknown = [m for m in mods if m not in MODIFIERS]
    if unknown:
        raise ValueError(f"Modificateur inconnu : {unknown[0]} (Ctrl, Alt, Shift ou Win).")
    mask = 0
    for m in mods:
        mask |= MODIFIERS[m]
    if len(key) == 1 and key.isalnum():  # lettre ou chiffre : le code Windows est le code ASCII
        return mask, ord(key)
    if key.startswith("F") and key[1:].isdigit() and 1 <= int(key[1:]) <= 12:
        return mask, 0x70 + int(key[1:]) - 1  # F1 = 0x70
    raise ValueError(f"Touche non prise en charge : {key} (lettre, chiffre ou F1 à F12).")


def readable_text(bg):
    """(texte, bordure) lisibles sur la couleur de fond bg ("#rrggbb")."""
    r, g, b = (int(bg[i:i + 2], 16) for i in (1, 3, 5))
    dark = 0.299 * r + 0.587 * g + 0.114 * b < 140  # luminosité perçue
    return ("#f1f3f4", "#8ab4f8") if dark else ("#202124", "#4285f4")


class SettingsWindow:
    """Fenêtre de réglages. on_save(cfg) est appelé avec les nouveaux paramètres."""

    def __init__(self, root, cfg, on_save):
        self.cfg = cfg
        self.on_save = on_save
        win = self.win = tk.Toplevel(root)
        win.title("Gemini — Paramètres")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        win.bind("<Escape>", lambda _e: win.destroy())

        tabs = ttk.Notebook(win)
        tabs.pack(fill="both", expand=True, padx=10, pady=(10, 0))
        self.build_gemini_tab(tabs)
        self.build_popup_tab(tabs)

        buttons = ttk.Frame(win)
        buttons.pack(fill="x", padx=10, pady=10)
        ttk.Button(buttons, text="Annuler", command=win.destroy).pack(side="right")
        ttk.Button(buttons, text="Enregistrer", command=self.save).pack(side="right", padx=6)
        ttk.Button(buttons, text="Valeurs par défaut", command=self.reset).pack(side="left")
        win.focus_force()

    # --- construction des onglets --------------------------------------------
    @staticmethod
    def row(parent, r, label, widget, hint=""):
        """Place une ligne « libellé : champ (aide) » dans une grille."""
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", pady=4, padx=(0, 10))
        widget.grid(row=r, column=1, sticky="we", pady=4)
        if hint:
            ttk.Label(parent, text=hint, foreground="gray").grid(row=r, column=2, sticky="w", padx=(8, 0))

    def build_gemini_tab(self, tabs):
        f = ttk.Frame(tabs, padding=12)
        tabs.add(f, text="Gemini")
        c = self.cfg

        key_box = ttk.Frame(f)
        self.api_key = tk.StringVar(value=c["api_key"])
        self.key_entry = ttk.Entry(key_box, textvariable=self.api_key, show="•", width=42)
        self.key_entry.pack(side="left", fill="x", expand=True)
        self.show_key = tk.BooleanVar(value=False)
        ttk.Checkbutton(key_box, text="Afficher", variable=self.show_key,
                        command=lambda: self.key_entry.config(show="" if self.show_key.get() else "•")
                        ).pack(side="left", padx=(6, 0))
        self.row(f, 0, "Clé API", key_box)

        model_box = ttk.Frame(f)
        self.model = tk.StringVar(value=c["model"])
        self.model_combo = ttk.Combobox(model_box, textvariable=self.model, width=32,
                                        values=["auto"] if c["model"] == "auto" else ["auto", c["model"]])
        self.model_combo.pack(side="left", fill="x", expand=True)
        ttk.Button(model_box, text="Actualiser la liste", command=self.refresh_models).pack(side="left", padx=(6, 0))
        self.row(f, 1, "Modèle", model_box, "auto = choix automatique")

        self.timeout = tk.IntVar(value=c["timeout"])
        self.row(f, 2, "Délai de réponse", ttk.Spinbox(f, from_=5, to=300, textvariable=self.timeout, width=6),
                 "secondes")

        self.hotkey = tk.StringVar(value=c["hotkey"])
        self.row(f, 3, "Raccourci", ttk.Entry(f, textvariable=self.hotkey, width=20),
                 "ex. Ctrl+Alt+G, Ctrl+Shift+F2")

        ttk.Label(f, text="Instructions permanentes pour Gemini (langue, ton, longueur des réponses…) :"
                  ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(10, 4))
        self.instructions = tk.Text(f, width=60, height=6, wrap="word", font=("Segoe UI", 9))
        self.instructions.insert("1.0", c["instructions"])
        self.instructions.grid(row=5, column=0, columnspan=3, sticky="we")
        f.columnconfigure(1, weight=1)

    def build_popup_tab(self, tabs):
        f = ttk.Frame(tabs, padding=12)
        tabs.add(f, text="Fenêtre")
        c = self.cfg

        # Opacité : curseur + valeur en pourcentage à côté.
        op_box = ttk.Frame(f)
        self.opacity = tk.DoubleVar(value=c["opacity"])
        op_label = ttk.Label(op_box, width=5)

        def show_opacity(*_):
            op_label.config(text=f"{round(self.opacity.get() * 100)} %")

        ttk.Scale(op_box, from_=0.2, to=1.0, variable=self.opacity, command=show_opacity, length=220
                  ).pack(side="left")
        op_label.pack(side="left", padx=(6, 0))
        show_opacity()
        self.row(f, 0, "Opacité", op_box)

        # Couleur de fond : automatique (zone autour) ou couleur fixe choisie.
        color_box = ttk.Frame(f)
        self.color_mode = tk.StringVar(value=c["color_mode"])
        self.fixed_color = tk.StringVar(value=c["fixed_color"])
        ttk.Radiobutton(color_box, text="Couleur de la zone autour", value="auto",
                        variable=self.color_mode).pack(anchor="w")
        fixed_line = ttk.Frame(color_box)
        fixed_line.pack(anchor="w", pady=(2, 0))
        ttk.Radiobutton(fixed_line, text="Couleur fixe", value="fixed", variable=self.color_mode).pack(side="left")
        self.swatch = tk.Label(fixed_line, width=3, relief="solid", borderwidth=1, bg=c["fixed_color"])
        self.swatch.pack(side="left", padx=6)
        ttk.Button(fixed_line, text="Choisir…", command=self.pick_color).pack(side="left")
        self.row(f, 1, "Fond", color_box)

        self.around = tk.IntVar(value=c["around"])
        self.row(f, 2, "Zone analysée", ttk.Spinbox(f, from_=0, to=1000, increment=10,
                                                    textvariable=self.around, width=6),
                 "pixels autour de la fenêtre (mode automatique)")

        self.font_size = tk.IntVar(value=c["font_size"])
        self.row(f, 3, "Taille du texte", ttk.Spinbox(f, from_=7, to=24, textvariable=self.font_size, width=6))

        self.width = tk.IntVar(value=c["width"])
        self.row(f, 4, "Largeur", ttk.Spinbox(f, from_=30, to=200, increment=5, textvariable=self.width, width=6),
                 "caractères")

        self.max_lines = tk.IntVar(value=c["max_lines"])
        self.row(f, 5, "Hauteur max", ttk.Spinbox(f, from_=5, to=80, textvariable=self.max_lines, width=6),
                 "lignes, ensuite défilement")

    # --- actions -------------------------------------------------------------
    def pick_color(self):
        _rgb, hex_color = colorchooser.askcolor(self.fixed_color.get(), parent=self.win, title="Couleur de fond")
        if hex_color:  # None si annulé
            self.fixed_color.set(hex_color)
            self.swatch.config(bg=hex_color)
            self.color_mode.set("fixed")

    def refresh_models(self):
        """Remplit la liste déroulante avec les modèles flash accessibles avec la clé saisie."""
        self.win.config(cursor="watch")
        self.win.update()
        try:
            names = gemini.rank_models(gemini.list_models(self.api_key.get().strip(), timeout=15))
            self.model_combo.config(values=["auto"] + names)
            self.model_combo.event_generate("<Button-1>")  # ouvre la liste
        except Exception as e:
            messagebox.showerror("Gemini", f"Impossible de récupérer les modèles :\n{e}", parent=self.win)
        finally:
            self.win.config(cursor="")

    def reset(self):
        """Remet tous les champs aux valeurs par défaut (la clé API est conservée)."""
        d = DEFAULTS
        for var, name in ((self.model, "model"), (self.timeout, "timeout"), (self.hotkey, "hotkey"),
                          (self.opacity, "opacity"), (self.color_mode, "color_mode"),
                          (self.fixed_color, "fixed_color"), (self.around, "around"),
                          (self.font_size, "font_size"), (self.width, "width"),
                          (self.max_lines, "max_lines")):
            var.set(d[name])
        self.swatch.config(bg=d["fixed_color"])
        self.instructions.delete("1.0", "end")

    def save(self):
        try:
            cfg = {
                "api_key": self.api_key.get().strip(),
                "model": self.model.get().strip() or "auto",
                "timeout": int(self.timeout.get()),
                "instructions": self.instructions.get("1.0", "end").strip(),
                "hotkey": self.hotkey.get().strip(),
                "opacity": round(float(self.opacity.get()), 2),
                "color_mode": self.color_mode.get(),
                "fixed_color": self.fixed_color.get(),
                "around": int(self.around.get()),
                "font_size": int(self.font_size.get()),
                "width": int(self.width.get()),
                "max_lines": int(self.max_lines.get()),
            }
            parse_hotkey(cfg["hotkey"])  # vérifie le raccourci avant d'enregistrer
        except (tk.TclError, ValueError) as e:  # TclError : champ numérique vide ou non numérique
            messagebox.showerror("Gemini", f"Paramètre invalide :\n{e}", parent=self.win)
            return
        try:
            save_config(cfg)
        except OSError as e:
            messagebox.showerror("Gemini", f"Impossible d'écrire config.json :\n{e}", parent=self.win)
            return
        self.on_save(cfg)
        self.win.destroy()
