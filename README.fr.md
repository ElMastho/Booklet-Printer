# Booklet Printer

Français · [English](README.md)

Application de bureau qui transforme un **PDF** ou une présentation **PowerPoint (PPTX)** en
**livret** (cahier piqué) : vous feuilletez le livret tel qu'il sera, vous corrigez les pages
qui ne vont pas, puis vous l'imprimez en recto-verso. Il ne reste qu'à plier la pile en deux
et à agrafer au pli.

## Téléchargement (Windows)

Téléchargez `BookletPrinter.exe` depuis la
[dernière version](https://github.com/ElMastho/booklet-printer/releases/latest) et lancez-le.
Aucune installation n'est nécessaire.

* L'exécutable n'est pas signé : Windows SmartScreen peut afficher « Windows a protégé votre
  ordinateur ». Cliquez sur **Informations complémentaires → Exécuter quand même**.
* Placez l'exe dans un dossier où vous pouvez écrire (Bureau, Documents…), pas dans
  `Program Files`, pour que la mise à jour automatique puisse le remplacer.

## Utilisation

1. **Ouvrir un fichier** (PDF, PPTX, PPT, ODP, DOCX…).
2. Vue **Livret** : le livret plié, page après page. Cliquez sur une page ou utilisez ← → pour
   tourner les pages. Chaque page affiche son numéro en bas à gauche, et la barre du dessous
   indique sur quelle feuille, recto ou verso, elle sera imprimée.
3. Vue **Pages** : corrigez ce qui ne va pas.
   * glissez-déposez les pages pour les réordonner (Ctrl/Maj-clic pour en sélectionner plusieurs) ;
   * avancer/reculer, déplacer à une position, dupliquer, supprimer ;
   * insérer des pages blanches, pivoter de 90° ;
   * recadrer une page en traçant un rectangle dessus (ou en saisissant les marges en mm) ;
   * réduire une page et la décaler dans sa demi-feuille ;
   * appliquer le même réglage à toutes les pages, réinitialiser une page, annuler/rétablir.
   Double-cliquez sur une page du livret ou des feuilles imprimées pour l'ouvrir ici.
4. Vue **Feuilles imprimées** : chaque feuille, recto et verso, avec les numéros de pages qu'elle porte.
5. **Imprimer le livret**, ou enregistrer le PDF prêt à imprimer.
6. Imbriquez les feuilles (la feuille 1 à l'extérieur), pliez en deux et agrafez au pli.

L'interface existe en **français et en anglais**. Elle suit la langue de l'ordinateur et se
change depuis l'en-tête. Thèmes clair et sombre disponibles.

### Réglages d'impression

L'impression se fait toujours en **recto-verso, retournement sur le bord court, échelle 100 %**.
Sous Windows, l'application impose ces réglages à l'imprimante. Si l'imprimante ne fait pas le
recto-verso, désactivez « Mon imprimante fait le recto-verso » : les rectos s'impriment, puis
l'application vous demande de retourner la pile sur le bord court avant d'imprimer les versos.

### Fichiers PowerPoint

Ils sont convertis en PDF avec **LibreOffice** s'il est installé (<https://www.libreoffice.org>),
sinon, sous Windows, avec **Microsoft PowerPoint**.

### Mise à jour automatique

Au démarrage, l'exécutable vérifie la dernière version publiée sur GitHub et propose de
l'installer : il se remplace et redémarre tout seul.

La documentation complète (ligne de commande, développement, publication) est dans le
[README anglais](README.md).
