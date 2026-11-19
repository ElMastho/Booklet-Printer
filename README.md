# Booklet Printer

Outil de bureau qui transforme un **PDF** ou une présentation **PowerPoint (PPTX)** en
**livret** (cahier piqué), avec un aperçu, puis l'imprime correctement en recto-verso :
il suffit de plier la pile de feuilles en deux et d'agrafer au pli.

![CI](https://github.com/ElMastho/booklet-printer/actions/workflows/ci.yml/badge.svg)

## Téléchargement (Windows)

Téléchargez `BookletPrinter.exe` depuis la
[dernière release](https://github.com/ElMastho/booklet-printer/releases/latest) et lancez-le.
Aucune installation n'est nécessaire.

* L'exécutable n'est pas signé : Windows SmartScreen peut afficher « Windows a protégé
  votre ordinateur ». Cliquez sur **Informations complémentaires → Exécuter quand même**.
* Placez l'exe dans un dossier où vous avez les droits d'écriture (Bureau, Documents…),
  pas dans `Program Files`, pour que la mise à jour automatique puisse le remplacer.

## Utilisation

1. **Ouvrir un PDF / PPTX…**
2. Vérifier l'aperçu :
   * **Feuilles à imprimer** : recto et verso de chaque feuille, avec en bleu le numéro de la
     page source placée à chaque emplacement ;
   * **Livret plié** : le livret tel qu'on le lira (couverture, doubles pages, 4ᵉ de couverture).
3. Régler si besoin : format de papier, reliure, marge, gouttière, 4ᵉ de couverture, traits de pliage.
4. **Imprimer** (ou **Enregistrer le PDF imposé…** pour l'imprimer depuis un autre logiciel).
5. Imbriquer les feuilles (la feuille 1 à l'extérieur), plier en deux, agrafer au pli.

### Ce que fait l'imposition

* Le nombre de pages est complété avec des pages blanches jusqu'au multiple de 4 suivant
  (à la fin, ou juste avant la dernière page si « Dernière page en 4ᵉ de couverture » est cochée).
* Deux pages par face, quatre par feuille, dans l'ordre du cahier piqué. Pour 8 pages :
  feuille 1 = recto 8 | 1, verso 2 | 7 ; feuille 2 = recto 6 | 3, verso 4 | 5.
* Les pages sont mises à l'échelle en conservant leurs proportions et centrées dans leur demi-feuille.
* **Reliure** :
  * *À gauche* : livret classique, feuille A4 paysage → livret A5 portrait ;
  * *À droite* : lecture de droite à gauche (manga, arabe, hébreu) ;
  * *En haut* (calendrier) : feuille A4 portrait, deux pages paysage l'une au-dessus de l'autre →
    idéal pour des diapositives 16:9 qui restent grandes ;
  * *Automatique* : « en haut » si la majorité des pages sont en paysage (diapos), sinon « à gauche ».

### Réglages d'impression

L'impression se fait toujours en **recto-verso, retournement sur le bord court, échelle 100 %**.

* **Windows** : l'application pilote l'imprimante directement (GDI) et force ces réglages
  (orientation, format, recto-verso bord court, nombre d'exemplaires).
* **macOS / Linux** : envoi via CUPS (`lp -o sides=two-sided-short-edge`).
* **Imprimante sans recto-verso** : choisissez « Recto-verso manuel ». Les rectos s'impriment,
  puis l'application vous demande de retourner la pile (sur le bord court) et imprime les versos.
  Si les versos sortent dans le mauvais ordre avec votre imprimante, cochez « Inverser l'ordre des versos ».
* Si vous imprimez le PDF imposé depuis un autre logiciel : *Recto-verso → Retourner sur le bord court*,
  *Taille réelle / 100 %* (pas « Ajuster »).

## Fichiers PowerPoint

Les fichiers `.pptx`, `.ppt`, `.odp` (et `.docx`, `.odt`) sont d'abord convertis en PDF :

1. avec **LibreOffice** s'il est installé (recommandé, gratuit : <https://www.libreoffice.org>) ;
2. sinon, sous Windows, avec **Microsoft PowerPoint** s'il est installé.

Le chemin de LibreOffice est détecté automatiquement ; on peut aussi le forcer avec la
variable d'environnement `BOOKLET_SOFFICE`. Pour un rendu identique à PowerPoint,
exporter la présentation en PDF depuis PowerPoint reste l'option la plus fidèle.

## Mise à jour automatique

Au démarrage, l'exécutable Windows vérifie la dernière
[release GitHub](https://github.com/ElMastho/booklet-printer/releases). Si une version plus récente
existe, il propose de l'installer : il télécharge le nouvel exe, se ferme, se remplace et redémarre.
Menu **Aide → Rechercher des mises à jour** pour vérifier à la demande, et **Aide → Vérifier au
démarrage** pour désactiver la vérification automatique.

## Ligne de commande

```bash
BookletPrinter.exe                         # interface graphique
BookletPrinter.exe document.pptx           # interface graphique avec le fichier ouvert
python -m booklet_printer doc.pdf -o livret.pdf [--paper A4] [--binding auto|left|right|top]
                          [--margin 5] [--gutter 0] [--keep-back-cover] [--fold-marks] [--split]
python -m booklet_printer doc.pdf --print [--printer "Nom"] [--copies 2]
```

`--split` écrit aussi `livret-rectos.pdf` et `livret-versos.pdf` pour un recto-verso manuel.

## Développement

```bash
python -m venv .venv && . .venv/bin/activate      # Windows : .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m pytest
python -m booklet_printer                          # lance l'interface
pyinstaller --onefile --windowed --name BookletPrinter run_app.py   # construit l'exe
```

Structure :

| Module | Rôle |
| --- | --- |
| `booklet_printer/imposition.py` | Ordre des pages, géométrie, génération du PDF imposé (PyMuPDF) |
| `booklet_printer/convert.py` | Conversion PPTX → PDF (LibreOffice, ou PowerPoint sous Windows) |
| `booklet_printer/printing.py` | Impression (GDI sous Windows, CUPS ailleurs) |
| `booklet_printer/updater.py` | Mise à jour automatique via GitHub Releases |
| `booklet_printer/gui.py` | Interface Tkinter avec aperçu |
| `booklet_printer/cli.py` | Point d'entrée (interface ou ligne de commande) |

### Publier une version

1. Mettre à jour `__version__` dans `booklet_printer/__init__.py`.
2. Commit et push sur `main`.
3. Dans [Actions → CI → Run workflow](https://github.com/ElMastho/booklet-printer/actions/workflows/ci.yml),
   cocher « Publier une release » (ou pousser un tag `vX.Y.Z` identique à la version).
4. La CI lance les tests (Linux et Windows), construit `BookletPrinter.exe`, le teste,
   puis crée la release GitHub avec l'exe : les installations existantes se mettent à jour d'elles-mêmes.

## Licence

MIT
