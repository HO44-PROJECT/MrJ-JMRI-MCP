*[English](CONDUCTOR.en.md)*

# 🚂 Conducteur

**Le chemin simple.** Tu veux juste faire rouler des trains.

Tu peux être un visiteur en exposition, un enfant qui essaie pour la première fois, ou le
propriétaire du réseau qui veut conduire sans se soucier des adresses DCC ou des
détails de JMRI. Tu parles (ou tapes) à l'assistant en langage naturel, et il conduit.

Cette page liste les phrases qui fonctionnent aujourd'hui. Donne le nom de la locomotive
si tu le connais ("l'Autorail") — l'assistant le résout vers la bonne adresse DCC pour
toi.

Pour les outils derrière ces phrases, voir [mcp-tools.md](mcp-tools.md). Pour les
restrictions à appliquer en session exposition/démo par-dessus cette page (limite de
vitesse, marche avant seulement, pas de contrôle de l'alimentation), voir la carte
[#56 Exhibition mode](https://github.com/HO44-PROJECT/MrJ-JMRI-MCP-backlog/issues/56) —
cette page documente ce que tu peux *dire*, pas ce qu'une session donnée a le *droit* de
faire.

---

## Préparer une locomotive

> "Prépare l'Autorail" · "prépare la 3"

Prend le contrôle de la locomotive, la met en marche avant, allume ses lumières — un seul
appel, prête à conduire.

## Conduire

> "Mets la 3 à 40%"
> "Arrête l'Autorail"
> "Fais demi-tour à la 3" (inverse la direction)
> "Avance l'Autorail pendant 10 secondes"
> "Freine l'Autorail pendant 5 secondes" · "Arrête la 3 en douceur sur 5 secondes"

Une durée ("pendant 10 secondes") fait gérer l'attente et l'arrêt par l'assistant tout
seul — pas besoin de lui redemander de s'arrêter ensuite. "Freine ... pendant N secondes"
ralentit progressivement jusqu'à l'arrêt au lieu de stopper net.

## Lumières

> "Allume les lumières de l'Autorail"
> "Éteins le phare de la 3"

## Ranger

> "Éteins l'Autorail" · "coupe la 3"

Arrêt en douceur, lumières éteintes, contrôle relâché — la façon correcte de terminer une
session avec une locomotive.

## Tout arrêter, immédiatement

> "Arrête tout !"

Arrêt d'urgence immédiat de toutes les locomotives en cours de conduite. C'est un arrêt de
mouvement, pas une coupure d'alimentation — voir [TINKERER.fr.md](TINKERER.fr.md) si tu as
besoin de couper le courant sur tout le réseau.

## Jour et nuit

> "Mode nuit" — allume d'un coup tout l'éclairage du réseau et les lumières de toutes les
> locomotives en cours de conduite.
> "Mode jour" — pareil, mais éteint.

## Quelles locomotives ai-je ?

> "Quelles sont mes locomotives ?"
> "Quelles fonctions a l'Autorail ?"

Utile avant de nommer une fonction par son effet ("allume les lumières de cabine") plutôt
que par son numéro.

## Qu'est-ce qui se passe ?

> "Donne-moi l'état du layout"
> "Tout est prêt ?"

Vue d'ensemble en un appel : JMRI est-il joignable, quelles locomotives roulent, à quelle
vitesse.

---

Envie de plus de contrôle — aiguillages, éclairage du réseau, alimentation, signaux ? Voir
[TINKERER.fr.md](TINKERER.fr.md). Envie de la référence complète outil par outil, ou de
scripter/automatiser le réseau ? Voir [ENGINEER.fr.md](ENGINEER.fr.md).
