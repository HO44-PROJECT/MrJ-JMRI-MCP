*[English](ENGINEER.en.md)*

# 🛠️ Ingénieur

**Veut voir comment ça marche, et repousser les limites.** Tu scriptes des sessions, tu
t'intéresses à ce qui se passe quand JMRI se comporte mal, et tu veux la surface complète
des outils plutôt que le recueil de phrases sélectionnées.

Tout ce qui est dans [CONDUCTOR.fr.md](CONDUCTOR.fr.md) et
[TINKERER.fr.md](TINKERER.fr.md) reste valable — celle-ci ajoute les outils bas niveau,
le CLI, et les comportements que tu rencontreras une fois sorti du langage naturel.

---

## Référence complète des outils

Les 47 outils MCP, par signature : **[mcp-tools.md](mcp-tools.md)**.

Justification de conception pour chacun — pourquoi un outil est fait ainsi, quelle
bizarrerie JMRI il contourne : **[docs/architecture.md](docs/architecture.md)**.

## Interface en ligne de commande

`jmri-cli` donne accès à la capacité de chaque outil sans passer par un LLM — contrôle
direct, scripting, automatisation, et l'outil de choix pour tester/déboguer contre un
JMRI réel ou simulé. Voir **[docs/cli.md](docs/cli.md)**.

## Contrôle bas niveau des locomotives

Au-delà de `set_speed`/`set_direction`, il y a `set_speed_ramped` (changement de vitesse
progressif avec des durées de montée/maintien/descente indépendantes — la primitive
derrière l'arrêt en douceur de `park_locomotive`), `set_function` (n'importe quelle
fonction décodeur F0-F28 par numéro, pas seulement les lumières), et
`acquire_throttle`/`release_throttle` si tu veux gérer explicitement le cycle de vie du
throttle JMRI plutôt que de compter sur l'acquisition automatique.

## Ce qui ne marche pas comme on l'imaginerait

- **JMRI n'envoie aucune réponse quand la valeur demandée correspond déjà à l'état
  actuel** — un véritable no-op silencieux, pas un message perdu. Chaque setter
  throttle/power/turnout/light de ce projet vérifie un cache mis à jour en direct avant
  d'envoyer, spécifiquement pour éviter de rester bloqué là-dessus.
- **Re-poster un état d'alimentation que JMRI rapporte déjà peut faire basculer le
  système en `UNKNOWN`** — un vrai bug DCC++, pas une bizarrerie de réponse transitoire.
  `set_power` relit toujours l'état actuel en premier et saute le POST s'il est déjà
  correct.
- **Un power-ON qui atterrit en `UNKNOWN` ne se rétablit pas tout seul** — `set_power`
  détecte ce cas et retente une fois via un cycle complet OFF → attente 2s → ON avant
  d'abandonner et de rapporter honnêtement `confirmed: false`.
- **Un throttle JMRI n'a de sens que sur la connexion qui l'a acquis** — le libérer laisse
  le décodeur continuer sur sa dernière vitesse commandée, il ne s'arrête pas tout seul.
  Le serveur MCP garde une connexion longue durée précisément pour cette raison ; les
  commandes ponctuelles de `jmri-cli` ont leur propre limite documentée à ce sujet, voir
  `docs/cli.md`.
- **L'état peut changer en dehors de ta session** — un autre panneau JMRI, PanelPro, ou
  une seconde session MCP/CLI peut faire bouger une locomotive que tu observes. Chaque
  lecture que ce projet t'affiche est en direct, jamais un cache auto-référentiel limité
  à tes propres commandes.

Voir `docs/architecture.md` pour le détail complet derrière chacun de ces points, y
compris comment ils sont testés.

## Tests et sécurité

Les fixtures simulées (`fake_jmri`) couvrent toute la suite de tests ; les tests en
direct contre une vraie instance JMRI sont optionnels et protégés, voir
**[docs/testing.md](docs/testing.md)**. Si tu scriptes quoi que ce soit qui fait bouger
une vraie locomotive ou touche à l'alimentation réelle, fais comme les contributeurs de
ce projet : confirme l'instance JMRI ciblée avant d'exécuter quoi que ce soit, et ne
suppose jamais qu'une autorisation précédente vaut pour la commande suivante.

## Contribuer

Conventions, organisation des modules, comment proposer un changement :
**[CONTRIBUTING.md](CONTRIBUTING.md)**.

---

Envie juste de conduire un train ? [CONDUCTOR.fr.md](CONDUCTOR.fr.md). Gérer le réseau
sans les détails internes du protocole ? [TINKERER.fr.md](TINKERER.fr.md).
