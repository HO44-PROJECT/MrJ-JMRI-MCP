*[English](TINKERER.en.md)*

# 🔧 Gestionnaire de réseau

**Gère le réseau, pas seulement les trains.** Tu prépares les sessions, gères
l'alimentation, actionnes les aiguillages, et prépares le réseau avant de le confier à un
conducteur — ou tu opères seul et veux plus que "conduire la loco".

Cette page liste les phrases qui fonctionnent aujourd'hui. Tout ce qui est dans
[CONDUCTOR.fr.md](CONDUCTOR.fr.md) reste valable ; celle-ci ajoute la couche gestion du
réseau par-dessus.

---

## Alimentation

> "Coupe le courant" · "coupe tout"
> "Allume tout"
> "Allume le système Ohara"

`power_off_all`/`power_on_all` sont les vrais boutons "tout arrêter absolument" et "tout
restaurer" — ils coupent l'alimentation de chaque système DCC, atteignant chaque
locomotive quel que soit qui la conduit (un panneau JMRI, une autre session, pas
seulement celle-ci). Nommer le courant/l'alimentation route toujours ici, jamais vers
l'arrêt d'urgence qui n'agit que sur le mouvement — "coupe le courant" et "arrête tout"
ne sont PAS la même demande.

> "Quel est l'état de l'alimentation ?"

## Aiguillages

> "Mets l'aiguillage 5 en position droite"
> "Bascule l'aiguillage près du dépôt"
> "Ferme tous les aiguillages"
> "Bascule tous les aiguillages"

La formulation "tous/toutes" met *chaque* aiguillage dans le même état en un seul appel —
ce n'est pas une restauration individuelle vers une position précédente.

## Éclairage du réseau

Éclairage du dépôt, de rue, des signaux — les objets `Light` propres à JMRI, distincts
des phares d'une locomotive (voir [CONDUCTOR.fr.md](CONDUCTOR.fr.md) pour ceux-là).

> "Allume l'éclairage de rue"
> "Allume toutes les lumières" (aucune locomotive nommée → ceci, pas les lumières d'une
> loco)

## Signaux

> "Mets le signal du bloc 3 au jaune"
> "Que montre le signal de la gare ?"

## Modes globaux du réseau

Le mode jour/nuit est couvert dans [CONDUCTOR.fr.md](CONDUCTOR.fr.md) — c'est une commande
d'ambiance simple, accessible à tous. Voici la couche gestion de session autour :

> "Je range tout, sécurise le layout" — arrêt en douceur de chaque locomotive en marche,
> lumières éteintes, éclairage du réseau éteint, contrôles relâchés : la commande de fin
> de session "tout ranger".
> "Libère les locos" — rend le contrôle (à un panneau JMRI ou une autre session) sans rien
> changer à leur état actuel.

`secure_layout` est délibérément plus doux que `power_off_all` (qui atteint aussi les
locomotives que personne ici ne conduit) et plus complet que `emergency_stop_all` (juste
le mouvement, pas de lumières, pas de relâchement).

## Mode exposition

> "Mode exposition" · "passe en mode démo"

Un mode à sécurité restreinte pour les démonstrations publiques — enfants ou grand
public qui essaient le contrôle vocal. Tant qu'il est actif : l'alimentation ne peut
pas être remise sous tension (la couper reste possible, comme coupure d'urgence),
chaque locomotive avance uniquement à une vitesse fixe et modérée quelle que soit la
demande, et seules les adresses DCC autorisées (si tu en as configuré) peuvent être
conduites. Les lumières et fonctions ne sont pas restreintes — un visiteur qui allume
un phare ou une sonnette fait partie de l'animation, pas un risque de sécurité.

> "Sors du mode exposition"

Nécessite le mot de passe configuré à l'installation — voir
[docs/exhibition.md](docs/exhibition.md) pour la configuration et les détails complets.

---

Envie de la référence complète des 50 outils, des détails de scripting de session, ou des
détails internes JMRI/protocole ? Voir [ENGINEER.fr.md](ENGINEER.fr.md) et
[mcp-tools.md](mcp-tools.md). Envie juste de conduire un train ?
[CONDUCTOR.fr.md](CONDUCTOR.fr.md).
