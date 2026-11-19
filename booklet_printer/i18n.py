"""User-facing strings in English and French.

The language follows the operating system by default and can be forced with
``set_language("en" | "fr")`` (saved in the settings by the GUI) or the
``BOOKLET_LANG`` environment variable.
"""

from __future__ import annotations

import locale
import os
import sys
from typing import Optional

LANGUAGES = {"en": "English", "fr": "Français"}
DEFAULT = "en"

EN: dict[str, str] = {
    # ---- core errors
    "err.no_pages": "The document has no pages.",
    "err.unknown_paper": "Unknown paper size: {paper}",
    "conv.powerpoint_no_pdf": "PowerPoint did not produce a PDF.",
    "conv.no_converter": (
        "Neither LibreOffice nor Microsoft PowerPoint is available to convert this file ({error}). "
        "Install LibreOffice (https://www.libreoffice.org) or export the presentation to PDF first."
    ),
    "conv.no_libreoffice": (
        "LibreOffice was not found. It is needed to convert {ext} files. Install it "
        "(https://www.libreoffice.org) or export your presentation to PDF from PowerPoint first."
    ),
    "conv.timeout": "The LibreOffice conversion took too long.",
    "conv.failed": "The LibreOffice conversion failed:\n{details}",
    "conv.unsupported": "Unsupported file type: {ext}",
    "prn.nothing": "Nothing to print.",
    "prn.no_lp": "The 'lp' command (CUPS) was not found.",
    "prn.failed": "Printing failed. {error}",
    "prn.no_pywin32": "pywin32 and Pillow are required to print on Windows.",
    "upd.no_release": "No release found on GitHub.",
    "upd.http_error": "GitHub answered with HTTP {code}.",
    "upd.unreachable": "Cannot reach GitHub: {error}",
    "upd.no_asset": "Release {tag} does not contain {asset}.",
    "upd.download_failed": "Download failed: {error}",
    "upd.incomplete": "The downloaded file looks incomplete.",
    "upd.windows_only": "Automatic updates are only available for the Windows executable.",
    # ---- command line
    "cli.description": "Lay out a PDF or PPTX as a saddle-stitched booklet and print it.",
    "cli.input": "source file (.pdf, .pptx, ...)",
    "cli.output": "imposed PDF to write (command-line mode)",
    "cli.print": "print directly",
    "cli.printer": "printer name (default: system default printer)",
    "cli.margin": "margin in mm (default 5)",
    "cli.gutter": "extra space at the fold in mm (default 0)",
    "cli.pages": 'page order, e.g. "1-4,blank,6,5,8-,7:r90"',
    "cli.keep_back_cover": "keep the last page on the back cover",
    "cli.fold_marks": "add fold marks",
    "cli.split": "with -o: also write -fronts.pdf and -backs.pdf",
    "cli.export_pages": "also write the edited pages in reading order",
    "cli.lang": "interface language",
    "cli.missing_input": "Error: missing source file.",
    "cli.error": "Error: {error}",
    "cli.summary": "{pages} pages -> {sheets} sheet(s), {blanks} blank page(s) added, binding {binding}",
    "cli.written": "Written: {path}",
    "cli.sent": "Sent to the printer (double-sided, flip on short edge).",
    # ---- general
    "page.blank": "Blank page",
    "page.source": "Original p. {n}",
    "page.booklet": "Page {n}",
    "side.front": "front",
    "side.back": "back",
    "binding.auto": "Automatic",
    "binding.left": "Left (classic)",
    "binding.right": "Right (right-to-left reading)",
    "binding.top": "Top (calendar, great for slides)",
    "binding.short.auto": "automatic",
    "binding.short.left": "on the left",
    "binding.short.right": "on the right",
    "binding.short.top": "at the top",
    "appearance.system": "System theme",
    "appearance.light": "Light",
    "appearance.dark": "Dark",
    "file.suffix_booklet": "-booklet.pdf",
    "file.suffix_edited": "-edited.pdf",
    # ---- header / welcome
    "btn.open": "Open a file",
    "label.no_file": "No document open",
    "label.pages": "{n} pages",
    "welcome.title": "Turn any document into a booklet",
    "welcome.subtitle": (
        "Open a PDF or a PowerPoint presentation. Booklet Printer puts the pages in the right order, "
        "shows you the booklet exactly as it will look, and prints it ready to fold."
    ),
    "welcome.button": "Open a PDF or PowerPoint",
    "welcome.step1": "Open",
    "welcome.step1_text": "PDF, PPTX, PPT, ODP, DOCX…",
    "welcome.step2": "Check & adjust",
    "welcome.step2_text": "Leaf through the booklet, reorder or fix any page.",
    "welcome.step3": "Print & fold",
    "welcome.step3_text": "Double-sided, then fold the stack in half and staple.",
    "welcome.formats": "PowerPoint files are converted with LibreOffice (or PowerPoint on Windows).",
    # ---- tabs
    "tab.book": "Booklet",
    "tab.pages": "Pages",
    "tab.sheets": "Printed sheets",
    # ---- book view
    "book.title": "Your booklet",
    "book.subtitle": "Click a page or use ← → to turn pages · double-click to edit it",
    "book.cover": "Front cover",
    "book.back_cover": "Back cover",
    "book.spread": "Pages {a} – {b}",
    "book.blank_added": "Blank page (added)",
    "book.chip": "Page {page} · {what}\nPrinted on sheet {sheet}, {side}",
    # ---- sheets view
    "sheets.title": "Printed sheets",
    "sheets.front": "FRONT",
    "sheets.back": "BACK",
    "sheets.flip": "flip the sheet\non its short edge",
    "sheets.summary": "Sheet {n} of {total}: printed on both sides, it carries booklet pages {pages}.",
    "sheets.caption": "Sheet {n} / {total}",
    "sheets.guide_title": "After printing",
    "sheets.guide": (
        "1. Keep the sheets in the order they come out (sheet 1 is the cover).\n"
        "2. Nest them: sheet 1 outside, the last sheet in the middle.\n"
        "3. Fold the stack in half along the line and staple on the fold."
    ),
    # ---- organizer
    "org.title": "Pages",
    "org.subtitle": "Drag to reorder · Ctrl/Shift-click to select several · right-click for more",
    "org.dragging": "Moving {count} page(s)",
    "edit.undo": "↩",
    "edit.redo": "↪",
    "edit.up": "←",
    "edit.down": "→",
    "edit.move_to": "Move to…",
    "edit.rotate_left": "↺",
    "edit.rotate_right": "↻",
    "edit.blank_before": "+ Blank before",
    "edit.blank_after": "+ Blank after",
    "edit.duplicate": "Duplicate",
    "edit.delete": "✕ Delete",
    "edit.restore": "Original",
    "tip.undo": "Undo the last change (Ctrl+Z)",
    "tip.redo": "Redo (Ctrl+Y)",
    "tip.up": "Move the selected pages one place earlier",
    "tip.down": "Move the selected pages one place later",
    "tip.move_to": "Move the selected pages to a given page number",
    "tip.rotate_left": "Rotate 90° counter-clockwise",
    "tip.rotate_right": "Rotate 90° clockwise",
    "tip.blank_before": "Insert a blank page before the selection",
    "tip.blank_after": "Insert a blank page after the selection",
    "tip.duplicate": "Duplicate the selected pages (Ctrl+D)",
    "tip.delete": "Remove the selected pages from the booklet (Del)",
    "tip.restore": "Go back to the original order with no adjustments",
    "menu.show_in_book": "Show in the booklet",
    "menu.rotate_left": "Rotate left",
    "menu.rotate_right": "Rotate right",
    "menu.undo": "Undo",
    "menu.redo": "Redo",
    "menu.restore": "Restore the original document",
    "adj.crop": "cropped",
    "adj.offset": "moved",
    "insp.none": "No page selected",
    "insp.multi": "{count} pages selected",
    "insp.help": "Draw a rectangle on the page to keep only that part.",
    "insp.crop": "Crop (mm)",
    "insp.left": "Left",
    "insp.top": "Top",
    "insp.right": "Right",
    "insp.bottom": "Bottom",
    "insp.clear_crop": "Remove crop",
    "insp.size": "Size",
    "insp.position": "Position",
    "insp.offset_value": "Horizontal {x} mm · vertical {y} mm",
    "insp.apply_all": "Apply to all pages",
    "insp.reset": "Reset this page",
    # ---- side panel
    "panel.summary": "Summary",
    "stat.pages": "pages",
    "stat.sheets": "sheets",
    "stat.blanks": "blank added",
    "info.binding": "Binding {binding}.",
    "info.edited": "{count} page(s) adjusted.",
    "frame.layout": "Layout",
    "frame.print": "Printing",
    "label.paper": "Paper",
    "label.binding": "Binding",
    "label.margin_value": "Margin: {mm} mm",
    "label.gutter_value": "Space at the fold: {mm} mm",
    "check.back_cover": "Last page on the back cover",
    "check.fold_marks": "Fold marks",
    "label.printer": "Printer",
    "label.no_printer": "Default printer",
    "label.copies": "Copies",
    "switch.auto_duplex": "My printer prints double-sided",
    "hint.auto_duplex": "Printed double-sided, flipped on the short edge, at 100 % scale.",
    "hint.manual_duplex": "Fronts first, then you turn the stack over and the backs are printed.",
    "check.reverse_backs": "Reverse the order of the backs",
    "btn.print": "Print the booklet",
    "btn.save_imposed": "Save as PDF (ready to print)",
    "btn.export_pages": "Export the edited pages",
    # ---- menus / dialogs / status
    "menu.lang_auto": "Auto language",
    "menu.check_updates": "Check for updates",
    "menu.auto_update": "Check for updates at start-up",
    "menu.how_to": "How to print a booklet",
    "menu.about": "About",
    "dlg.open_title": "Choose a document",
    "dlg.documents": "Documents",
    "dlg.all": "All files",
    "dlg.open_error": "Cannot open the file",
    "dlg.error": "Error",
    "dlg.print_error": "Cannot print",
    "dlg.move_to": "New position of the selected pages (1–{count}):",
    "dlg.restore_confirm": "Discard every change made to the pages and go back to the original document?",
    "dlg.manual_title": "Manual double-sided printing",
    "dlg.manual_body": (
        "The fronts are being printed.\n\n"
        "When it is done, take the stack WITHOUT changing the order of the sheets, turn it over "
        "by flipping it on the SHORT edge, and put it back in the tray.\n\n"
        "Click OK to print the backs.\n\n"
        "Tip: if the backs come out in the wrong order, turn on “Reverse the order of the backs” next time."
    ),
    "dlg.about": "Booklet Printer {version}\n\nLays out a PDF or PPTX as a saddle-stitched booklet and prints it double-sided.\n\nhttps://github.com/{repo}",
    "dlg.update_title": "Update",
    "dlg.up_to_date": "You are using the latest version ({version}).",
    "dlg.update_available": "Update available",
    "dlg.update_link": "Version {version} is available:\n{url}",
    "dlg.update_ask": "Version {version} is available (you have {current}).\n\n{notes}\n\nInstall it now? The application will restart.",
    "help.long": (
        "1. Open a PDF or PowerPoint file.\n"
        "2. Leaf through the booklet. If a page is wrong, double-click it to fix it: move, rotate, crop, "
        "resize, delete or add blank pages.\n"
        "3. Print: double-sided, flip on the SHORT edge, 100 % scale (set automatically).\n"
        "4. Nest the sheets (sheet 1 outside), fold in half and staple on the fold."
    ),
    "status.loading": "Opening {name}…",
    "status.loading_convert": "Converting {name} to PDF…",
    "status.loaded": "{name}: {pages} pages",
    "status.applied_all": "Applied to all pages",
    "status.undone": "Undone",
    "status.redone": "Redone",
    "status.saved": "Saved: {path}",
    "status.sent": "Sent to the printer",
    "status.backs_sent": "Backs sent to the printer",
    "status.downloading": "Downloading the update…{pct}",
}

FR: dict[str, str] = {
    "err.no_pages": "Le document ne contient aucune page.",
    "err.unknown_paper": "Format de papier inconnu : {paper}",
    "conv.powerpoint_no_pdf": "PowerPoint n'a pas produit de PDF.",
    "conv.no_converter": (
        "Ni LibreOffice ni Microsoft PowerPoint ne sont disponibles pour convertir ce fichier ({error}). "
        "Installez LibreOffice (https://www.libreoffice.org) ou exportez d'abord la présentation en PDF."
    ),
    "conv.no_libreoffice": (
        "LibreOffice est introuvable : il est nécessaire pour convertir les fichiers {ext}. Installez-le "
        "(https://www.libreoffice.org) ou exportez d'abord la présentation en PDF depuis PowerPoint."
    ),
    "conv.timeout": "La conversion LibreOffice a pris trop de temps.",
    "conv.failed": "Échec de la conversion LibreOffice :\n{details}",
    "conv.unsupported": "Format non pris en charge : {ext}",
    "prn.nothing": "Rien à imprimer.",
    "prn.no_lp": "La commande « lp » (CUPS) est introuvable.",
    "prn.failed": "Échec de l'impression. {error}",
    "prn.no_pywin32": "pywin32 et Pillow sont nécessaires pour imprimer sous Windows.",
    "upd.no_release": "Aucune version publiée sur GitHub.",
    "upd.http_error": "GitHub a répondu avec le code HTTP {code}.",
    "upd.unreachable": "Impossible de joindre GitHub : {error}",
    "upd.no_asset": "La version {tag} ne contient pas {asset}.",
    "upd.download_failed": "Téléchargement impossible : {error}",
    "upd.incomplete": "Le fichier téléchargé semble incomplet.",
    "upd.windows_only": "La mise à jour automatique n'est disponible que pour l'exécutable Windows.",
    "cli.description": "Met en page un PDF ou un PPTX en livret (cahier piqué) et l'imprime.",
    "cli.input": "fichier source (.pdf, .pptx, …)",
    "cli.output": "PDF imposé à écrire (mode ligne de commande)",
    "cli.print": "imprimer directement",
    "cli.printer": "nom de l'imprimante (défaut : imprimante par défaut)",
    "cli.margin": "marge en mm (défaut 5)",
    "cli.gutter": "espace au pli en mm (défaut 0)",
    "cli.pages": "ordre des pages, ex. « 1-4,blank,6,5,8-,7:r90 »",
    "cli.keep_back_cover": "garder la dernière page en 4e de couverture",
    "cli.fold_marks": "ajouter des traits de pliage",
    "cli.split": "avec -o : écrire aussi -fronts.pdf et -backs.pdf",
    "cli.export_pages": "écrire aussi les pages modifiées dans l'ordre de lecture",
    "cli.lang": "langue de l'interface",
    "cli.missing_input": "Erreur : fichier source manquant.",
    "cli.error": "Erreur : {error}",
    "cli.summary": "{pages} pages -> {sheets} feuille(s), {blanks} page(s) blanche(s) ajoutée(s), reliure {binding}",
    "cli.written": "Écrit : {path}",
    "cli.sent": "Envoyé à l'imprimante (recto-verso, bord court).",
    "page.blank": "Page blanche",
    "page.source": "Original p. {n}",
    "page.booklet": "Page {n}",
    "side.front": "recto",
    "side.back": "verso",
    "binding.auto": "Automatique",
    "binding.left": "À gauche (classique)",
    "binding.right": "À droite (lecture droite → gauche)",
    "binding.top": "En haut (calendrier, idéal diapos)",
    "binding.short.auto": "automatique",
    "binding.short.left": "à gauche",
    "binding.short.right": "à droite",
    "binding.short.top": "en haut",
    "appearance.system": "Thème du système",
    "appearance.light": "Clair",
    "appearance.dark": "Sombre",
    "file.suffix_booklet": "-livret.pdf",
    "file.suffix_edited": "-modifie.pdf",
    "btn.open": "Ouvrir un fichier",
    "label.no_file": "Aucun document ouvert",
    "label.pages": "{n} pages",
    "welcome.title": "Transformez n'importe quel document en livret",
    "welcome.subtitle": (
        "Ouvrez un PDF ou une présentation PowerPoint. Booklet Printer remet les pages dans le bon ordre, "
        "vous montre le livret tel qu'il sera, et l'imprime prêt à plier."
    ),
    "welcome.button": "Ouvrir un PDF ou un PowerPoint",
    "welcome.step1": "Ouvrir",
    "welcome.step1_text": "PDF, PPTX, PPT, ODP, DOCX…",
    "welcome.step2": "Vérifier et ajuster",
    "welcome.step2_text": "Feuilletez le livret, réordonnez ou corrigez une page.",
    "welcome.step3": "Imprimer et plier",
    "welcome.step3_text": "Recto-verso, puis pliez la pile en deux et agrafez.",
    "welcome.formats": "Les fichiers PowerPoint sont convertis avec LibreOffice (ou PowerPoint sous Windows).",
    "tab.book": "Livret",
    "tab.pages": "Pages",
    "tab.sheets": "Feuilles imprimées",
    "book.title": "Votre livret",
    "book.subtitle": "Cliquez sur une page ou utilisez ← → pour tourner · double-clic pour la modifier",
    "book.cover": "Couverture",
    "book.back_cover": "4ᵉ de couverture",
    "book.spread": "Pages {a} – {b}",
    "book.blank_added": "Page blanche (ajoutée)",
    "book.chip": "Page {page} · {what}\nImprimée sur la feuille {sheet}, {side}",
    "sheets.title": "Feuilles imprimées",
    "sheets.front": "RECTO",
    "sheets.back": "VERSO",
    "sheets.flip": "retourner la feuille\nsur le bord court",
    "sheets.summary": "Feuille {n} sur {total} : imprimée des deux côtés, elle porte les pages {pages} du livret.",
    "sheets.caption": "Feuille {n} / {total}",
    "sheets.guide_title": "Après l'impression",
    "sheets.guide": (
        "1. Gardez les feuilles dans l'ordre de sortie (la feuille 1 porte la couverture).\n"
        "2. Imbriquez-les : la feuille 1 à l'extérieur, la dernière au centre.\n"
        "3. Pliez la pile en deux sur le trait et agrafez au pli."
    ),
    "org.title": "Pages",
    "org.subtitle": "Glissez pour réordonner · Ctrl/Maj-clic pour en sélectionner plusieurs · clic droit pour plus",
    "org.dragging": "Déplacement de {count} page(s)",
    "edit.undo": "↩",
    "edit.redo": "↪",
    "edit.up": "←",
    "edit.down": "→",
    "edit.move_to": "Déplacer vers…",
    "edit.rotate_left": "↺",
    "edit.rotate_right": "↻",
    "edit.blank_before": "+ Blanche avant",
    "edit.blank_after": "+ Blanche après",
    "edit.duplicate": "Dupliquer",
    "edit.delete": "✕ Supprimer",
    "edit.restore": "Original",
    "tip.undo": "Annuler la dernière modification (Ctrl+Z)",
    "tip.redo": "Rétablir (Ctrl+Y)",
    "tip.up": "Avancer les pages sélectionnées d'une place",
    "tip.down": "Reculer les pages sélectionnées d'une place",
    "tip.move_to": "Déplacer les pages sélectionnées à un numéro de page",
    "tip.rotate_left": "Pivoter de 90° vers la gauche",
    "tip.rotate_right": "Pivoter de 90° vers la droite",
    "tip.blank_before": "Insérer une page blanche avant la sélection",
    "tip.blank_after": "Insérer une page blanche après la sélection",
    "tip.duplicate": "Dupliquer les pages sélectionnées (Ctrl+D)",
    "tip.delete": "Retirer les pages sélectionnées du livret (Suppr)",
    "tip.restore": "Revenir à l'ordre d'origine, sans aucun réglage",
    "menu.show_in_book": "Voir dans le livret",
    "menu.rotate_left": "Pivoter à gauche",
    "menu.rotate_right": "Pivoter à droite",
    "menu.undo": "Annuler",
    "menu.redo": "Rétablir",
    "menu.restore": "Revenir au document d'origine",
    "adj.crop": "recadrée",
    "adj.offset": "déplacée",
    "insp.none": "Aucune page sélectionnée",
    "insp.multi": "{count} pages sélectionnées",
    "insp.help": "Tracez un rectangle sur la page pour n'en garder que cette partie.",
    "insp.crop": "Recadrage (mm)",
    "insp.left": "Gauche",
    "insp.top": "Haut",
    "insp.right": "Droite",
    "insp.bottom": "Bas",
    "insp.clear_crop": "Retirer le recadrage",
    "insp.size": "Taille",
    "insp.position": "Position",
    "insp.offset_value": "Horizontal {x} mm · vertical {y} mm",
    "insp.apply_all": "Appliquer à toutes les pages",
    "insp.reset": "Réinitialiser cette page",
    "panel.summary": "Résumé",
    "stat.pages": "pages",
    "stat.sheets": "feuilles",
    "stat.blanks": "blanches ajoutées",
    "info.binding": "Reliure {binding}.",
    "info.edited": "{count} page(s) ajustée(s).",
    "frame.layout": "Mise en page",
    "frame.print": "Impression",
    "label.paper": "Papier",
    "label.binding": "Reliure",
    "label.margin_value": "Marge : {mm} mm",
    "label.gutter_value": "Espace au pli : {mm} mm",
    "check.back_cover": "Dernière page en 4ᵉ de couverture",
    "check.fold_marks": "Traits de pliage",
    "label.printer": "Imprimante",
    "label.no_printer": "Imprimante par défaut",
    "label.copies": "Exemplaires",
    "switch.auto_duplex": "Mon imprimante fait le recto-verso",
    "hint.auto_duplex": "Impression recto-verso, retournement sur le bord court, échelle 100 %.",
    "hint.manual_duplex": "Les rectos d'abord, puis vous retournez la pile et les versos s'impriment.",
    "check.reverse_backs": "Inverser l'ordre des versos",
    "btn.print": "Imprimer le livret",
    "btn.save_imposed": "Enregistrer en PDF (prêt à imprimer)",
    "btn.export_pages": "Exporter les pages modifiées",
    "menu.lang_auto": "Langue auto",
    "menu.check_updates": "Rechercher des mises à jour",
    "menu.auto_update": "Vérifier au démarrage",
    "menu.how_to": "Comment imprimer un livret",
    "menu.about": "À propos",
    "dlg.open_title": "Choisir un document",
    "dlg.documents": "Documents",
    "dlg.all": "Tous les fichiers",
    "dlg.open_error": "Impossible d'ouvrir le fichier",
    "dlg.error": "Erreur",
    "dlg.print_error": "Impression impossible",
    "dlg.move_to": "Nouvelle position des pages sélectionnées (1–{count}) :",
    "dlg.restore_confirm": "Abandonner toutes les modifications des pages et revenir au document d'origine ?",
    "dlg.manual_title": "Recto-verso manuel",
    "dlg.manual_body": (
        "Les rectos sont en cours d'impression.\n\n"
        "Quand c'est terminé, reprenez la pile SANS changer l'ordre des feuilles, retournez-la "
        "en la faisant pivoter sur le BORD COURT, et remettez-la dans le bac.\n\n"
        "Cliquez sur OK pour imprimer les versos.\n\n"
        "Astuce : si les versos sortent dans le mauvais ordre, activez « Inverser l'ordre des versos » la prochaine fois."
    ),
    "dlg.about": "Booklet Printer {version}\n\nMet en page un PDF ou un PPTX en livret (cahier piqué) et l'imprime en recto-verso.\n\nhttps://github.com/{repo}",
    "dlg.update_title": "Mise à jour",
    "dlg.up_to_date": "Vous utilisez la dernière version ({version}).",
    "dlg.update_available": "Mise à jour disponible",
    "dlg.update_link": "La version {version} est disponible :\n{url}",
    "dlg.update_ask": "La version {version} est disponible (vous avez la {current}).\n\n{notes}\n\nL'installer maintenant ? L'application va redémarrer.",
    "help.long": (
        "1. Ouvrez un PDF ou un fichier PowerPoint.\n"
        "2. Feuilletez le livret. Si une page ne va pas, double-cliquez dessus pour la corriger : déplacer, "
        "pivoter, recadrer, redimensionner, supprimer ou ajouter des pages blanches.\n"
        "3. Imprimez : recto-verso, retournement sur le bord COURT, échelle 100 % (réglé automatiquement).\n"
        "4. Imbriquez les feuilles (la feuille 1 à l'extérieur), pliez en deux et agrafez au pli."
    ),
    "status.loading": "Ouverture de {name}…",
    "status.loading_convert": "Conversion de {name} en PDF…",
    "status.loaded": "{name} : {pages} pages",
    "status.applied_all": "Appliqué à toutes les pages",
    "status.undone": "Annulé",
    "status.redone": "Rétabli",
    "status.saved": "Enregistré : {path}",
    "status.sent": "Envoyé à l'imprimante",
    "status.backs_sent": "Versos envoyés à l'imprimante",
    "status.downloading": "Téléchargement de la mise à jour…{pct}",
}

CATALOGS = {"en": EN, "fr": FR}

_current: Optional[str] = None


def system_language() -> str:
    """Language of the operating system, as a supported code."""
    candidates: list[str] = []
    if sys.platform.startswith("win"):
        try:
            import ctypes

            langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            primary = langid & 0x3FF
            candidates.append({0x0C: "fr", 0x09: "en"}.get(primary, ""))
        except Exception:  # noqa: BLE001
            pass
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        if os.environ.get(var):
            candidates.append(os.environ[var])
    try:
        candidates.append(locale.getlocale()[0] or "")
    except ValueError:
        pass
    for c in candidates:
        code = c.strip().lower()[:2]
        if code in CATALOGS:
            return code
    return DEFAULT


def _configured() -> str:
    env = os.environ.get("BOOKLET_LANG", "").lower()
    if env in CATALOGS:
        return env
    try:
        from .config import get_setting

        saved = str(get_setting("language", "auto")).lower()
    except Exception:  # noqa: BLE001
        saved = "auto"
    return saved if saved in CATALOGS else system_language()


def current_language() -> str:
    global _current
    if _current is None:
        _current = _configured()
    return _current


def set_language(code: Optional[str]) -> str:
    """Force a language ("en", "fr") or follow the system ("auto"/None)."""
    global _current
    code = (code or "auto").lower()
    _current = code if code in CATALOGS else system_language()
    return _current


def t(key: str, **kwargs) -> str:
    text = CATALOGS[current_language()].get(key) or EN.get(key) or key
    return text.format(**kwargs) if kwargs else text
