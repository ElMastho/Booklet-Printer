"""Colours, fonts and small helpers shared by the widgets."""

from __future__ import annotations

import customtkinter as ctk

# (light, dark) pairs, as CustomTkinter expects.
BG = ("#F3F4FA", "#14151B")
SURFACE = ("#FFFFFF", "#1E1F28")
SURFACE_2 = ("#ECEEF8", "#2A2C38")
BORDER = ("#DFE2EF", "#323446")
TEXT = ("#1B1D29", "#ECEDF5")
MUTED = ("#6B6F85", "#9A9EB5")
PRIMARY = ("#5B5BD6", "#7B7BF0")
PRIMARY_HOVER = ("#4848C2", "#6565DD")
PRIMARY_SOFT = ("#E7E7FB", "#2D2E55")
SELECTED = ("#D2D2FA", "#4B4BB0")
SELECTED_HOVER = ("#C2C2F4", "#5656BE")
ACCENT = ("#FF6B4A", "#FF7A5C")
ACCENT_HOVER = ("#E8573A", "#F0664A")
SUCCESS = ("#1F9D6B", "#36C08B")
WARNING = ("#E8A317", "#F2B83A")
DANGER = ("#E5484D", "#F2555A")

# Stage (canvas) colours, picked at draw time.
STAGE = ("#E2E5F3", "#0E0F14")
STAGE_TEXT = ("#4A4E66", "#B7BAD0")

# Badge colours for the PIL-rendered pages (RGB)
BADGE_BG = (91, 91, 214)
BADGE_BLANK = (150, 154, 175)
BADGE_TEXT = (255, 255, 255)
HIGHLIGHT = (255, 176, 0)

RADIUS = 14
FONT_FAMILY = "Segoe UI"  # falls back to the Tk default when missing


def pick(pair: tuple[str, str]) -> str:
    """Resolve a (light, dark) pair for widgets that are not CTk (tk.Canvas)."""
    return pair[1] if ctk.get_appearance_mode() == "Dark" else pair[0]


def font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)


def setup() -> None:
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")


def primary_button(master, **kw) -> ctk.CTkButton:
    kw.setdefault("height", 36)
    kw.setdefault("corner_radius", 10)
    kw.setdefault("font", font(13, "bold"))
    return ctk.CTkButton(master, fg_color=PRIMARY, hover_color=PRIMARY_HOVER, **kw)


def accent_button(master, **kw) -> ctk.CTkButton:
    kw.setdefault("height", 46)
    kw.setdefault("corner_radius", 12)
    kw.setdefault("font", font(15, "bold"))
    return ctk.CTkButton(master, fg_color=ACCENT, hover_color=ACCENT_HOVER, **kw)


def ghost_button(master, **kw) -> ctk.CTkButton:
    kw.setdefault("height", 32)
    kw.setdefault("corner_radius", 10)
    kw.setdefault("font", font(12))
    return ctk.CTkButton(
        master, fg_color=SURFACE_2, hover_color=PRIMARY_SOFT, text_color=TEXT, border_width=0, **kw
    )


def card(master, **kw) -> ctk.CTkFrame:
    kw.setdefault("corner_radius", RADIUS)
    kw.setdefault("fg_color", SURFACE)
    kw.setdefault("border_width", 1)
    kw.setdefault("border_color", BORDER)
    return ctk.CTkFrame(master, **kw)


def section_title(master, text: str) -> ctk.CTkLabel:
    return ctk.CTkLabel(master, text=text.upper(), font=font(11, "bold"), text_color=MUTED, anchor="w")
