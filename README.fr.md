# MrJ JMRI AI Assistant

*[English version](README.md)*

[![PyPI - jmri-mcp](https://img.shields.io/pypi/v/jmri-mcp?label=jmri-mcp)](https://pypi.org/project/jmri-mcp/)
[![PyPI - jmri-cli](https://img.shields.io/pypi/v/jmri-cli?label=jmri-cli)](https://pypi.org/project/jmri-cli/)
[![PyPI - jmri-core](https://img.shields.io/pypi/v/jmri-core?label=jmri-core)](https://pypi.org/project/jmri-core/)
[![Downloads](https://img.shields.io/pypi/dm/jmri-mcp)](https://pypi.org/project/jmri-mcp/)
[![GitHub Release](https://img.shields.io/github/v/release/HO44-PROJECT/MrJ-JMRI-MCP)](https://github.com/HO44-PROJECT/MrJ-JMRI-MCP/releases/latest)

> **Licence et attribution — à lire avant toute réutilisation.**
> Ce projet est © HO44 PROJECT (MrJ) et publié sous licence **AGPL-3.0-or-later** (voir [LICENSE](LICENSE)).
> Si vous redistribuez, modifiez ou republiez tout ou partie de ce projet — `jmri-core`, `jmri-cli`, `jmri-mcp`,
> les bundles `.mcpb`/`.codex.zip`, ou la documentation — **sur ce dépôt ou ailleurs** (un fork, une autre
> plateforme, un registre de paquets, une vidéo, un article), vous **devez** :
> - conserver le crédit de l'auteur original (**MrJ / HO44 PROJECT**) et un lien vers
>   [ce dépôt](https://github.com/HO44-PROJECT/MrJ-JMRI-MCP), et
> - conserver la même licence AGPL-3.0-or-later sur toute version redistribuée ou modifiée.
>
> Retirer ou masquer cette attribution n'est pas qu'une question de savoir-vivre — au regard de l'AGPL-3.0,
> c'est une **violation de licence**, et elle sera traitée comme telle. Voir [NOTICE.md](NOTICE.md) pour le détail.
>
> Questions ou discussion générale : [GitHub Discussions](https://github.com/HO44-PROJECT/MrJ-JMRI-MCP/discussions).
> Bugs et demandes de fonctionnalités : [Issues](https://github.com/HO44-PROJECT/MrJ-JMRI-MCP/issues).

**Parlez à votre réseau ferroviaire miniature.**

Apportez l'IA à votre réseau [JMRI](https://www.jmri.org/). Connectez votre assistant IA préféré et contrôlez votre réseau miniature [DCC](https://www.nmra.com/digital-command-control-dcc) en langage naturel, à la voix ou par chat.

Faites rouler des locomotives, commandez des aiguillages, actionnez des signaux, gérez les accessoires du réseau, et bien plus — simplement en demandant.

Compatible avec les clients MCP tels que [Claude Desktop](https://claude.ai/download), [Claude Code](https://claude.com/claude-code), [xiaozhi](https://github.com/78/xiaozhi-esp32), et tout autre assistant IA compatible MCP.

## Fonctionnalités

**MrJ JMRI AI Assistant fournit :**

- Un package prêt à l'emploi, facile à installer
- Une documentation complète avec guides d'installation et exemples d'utilisation
- Un serveur MCP (Model Context Protocol) complet pour l'intégration JMRI
- Une interface en ligne de commande (`jmri-cli`) pour le contrôle direct, le scripting et l'automatisation
- 50 outils MCP couvrant les principales fonctions de JMRI :
  - Gestion de l'alimentation
  - Locomotives : vitesse, direction, fonctions
  - Gestion du roster (parc de locomotives)
  - Aiguillages
  - Capteurs
  - Éclairages du réseau
  - Signaux
  - Cantons (blocks)
  - Modes de fonctionnement
  - Outils transversaux (vue d'ensemble de l'état, modes sécurisé/nuit/jour)

Consultez la référence complète des outils MCP dans [mcp-tools.md](mcp-tools.md).

L'objectif est simple : rendre le contrôle JMRI avancé accessible à tout modéliste ferroviaire, du simple opérateur à l'amateur d'automatisation.

### Conçu sur du matériel réel, pas seulement sur la doc JMRI

Ce projet a été développé sur un réseau DCC++ réel, avec plusieurs postes de commande,
et plusieurs de ses comportements existent précisément parce que le matériel réel ne se
comporte pas toujours comme la documentation de l'API JMRI le laisse penser :

- **Auto-guérison des états d'alimentation UNKNOWN.** Renvoyer l'état d'alimentation
  *déjà en cours* d'un poste de commande (un naïf "allume" alors que c'est déjà allumé)
  est un piège connu de JMRI/DCC++ : au lieu d'être un no-op sûr, cela fait basculer le
  système dans un état UNKNOWN. Chaque commande d'alimentation relit d'abord l'état
  actuel et évite les POST redondants — et si une vraie demande d'allumage atterrit
  quand même en UNKNOWN, une récupération automatique s'enclenche via une séquence
  OFF → attente → ON, plutôt que de laisser le réseau bloqué.
- **Affinité poste de commande par locomotive.** Sur un réseau avec plusieurs connexions
  DCC, envoyer les commandes d'une locomotive au mauvais poste de commande ne déclenche
  aucune erreur — c'est simplement inaudible pour le décodeur, en silence. Les entrées du
  roster peuvent déclarer sur quelle connexion elles roulent normalement via un attribut
  personnalisé `DccSystem` (renseigné dans JMRI, onglet Roster Entry → Edit →
  Attributes, ex. `DccSystem` = `T`), lu automatiquement par l'acquisition de la
  manette pour cibler le bon poste.
- **Connexion DCC et adresse matérielle affichées pour chaque aiguillage, éclairage et
  signal.** Lister un aiguillage, un éclairage ou un signal indique quelle connexion DCC
  le pilote réellement (résolu à partir de son nom système JMRI, ex. `OT23` →
  `ohara (turnouts)`), ainsi que son adresse matérielle brute quand JMRI l'expose
  (aiguillages et éclairages ; les mâts de signalisation n'exposent la leur via aucune
  API JMRI à ce jour, ce champ est donc honnêtement rapporté comme inconnu plutôt que
  deviné).
- **Chaque écriture est confirmée par une relecture de l'état réel, jamais en faisant
  confiance à la réponse.** Les commandes d'alimentation, d'aiguillage, d'éclairage et de
  signal relisent toutes l'état réel de JMRI après action, et rapportent exactement ce
  qui a été observé — y compris quand cela ne correspond pas à ce qui était demandé —
  plutôt que de supposer qu'une réponse 200 signifie que le réseau a fait ce qui était
  demandé.
- **L'état des manettes reste à jour même piloté depuis ailleurs.** JMRI diffuse chaque
  changement de manette (vitesse, direction, fonctions) à tous les clients qui détiennent
  cette locomotive — y compris d'autres panneaux JMRI ou une seconde session MCP — et le
  cache de manette de ce projet reste continuellement synchronisé avec ce flux, pas
  seulement avec ses propres commandes, si bien qu'il ne rapporte jamais un état périmé
  après qu'quelqu'un d'autre a piloté le train.

## Que puis-je dire ?

Choisissez la page qui correspond à ce que vous voulez faire — chacune renvoie vers la
suivante. Disponible en français et en anglais :

- **🚂 Conducteur** — vous voulez juste faire rouler des trains ? Commencez ici.
  [Français](CONDUCTOR.fr.md) · [English](CONDUCTOR.en.md)
- **🔧 Bricoleur** — gestion de l'alimentation, des aiguillages, des signaux, et de tout le réseau.
  [Français](TINKERER.fr.md) · [English](TINKERER.en.md)
- **🛠️ Ingénieur** — référence complète des outils, CLI, scripting et internals JMRI.
  [Français](ENGINEER.fr.md) · [English](ENGINEER.en.md)

Le découpage conducteur/bricoleur/ingénieur est emprunté à [DCC-EX](https://dcc-ex.com/begin/levels.html), qui a inventé cette approche en premier.

## Installation

Le démarrage est conçu pour être simple.

Voir le [guide d'installation](INSTALL.md) pour toutes les combinaisons d'installation (CLI, `.mcpb` Claude Desktop, pont Kira), la configuration et les premières commandes.

Vous préférez un guide pas-à-pas avec captures d'écran ? Voir l'Instructable
de la communauté (en anglais) : [Control Your JMRI Railroad by Chatting With Claude](https://www.instructables.com/Control-Your-JMRI-Railroad-by-Chatting-With-Claude/).

## Configuration de l'assistant IA

- [Claude Desktop et Claude Code](docs/llm-setup-claude.md)
- [xiaozhi / Kira](docs/llm-setup-xiaozhi.md)

## Interface en ligne de commande

`jmri-cli` est un client en ligne de commande complet pour votre réseau, qui parle
directement à JMRI sans nécessiter d'assistant IA ni de client MCP — tout ce que les
outils MCP savent faire, un humain peut aussi le faire, depuis un terminal.

Lancez-le sans argument pour ouvrir un **shell interactif** : une connexion persistante
unique qui garde les locomotives en mouvement, allumées et acquises entre les commandes
(contrairement à un appel ponctuel, qui libère toutes les manettes dès qu'il se termine).
Le shell ajoute une vraie ergonomie de ligne de commande par-dessus : un **historique de
commandes** (flèches haut/bas) persisté d'une session à l'autre
(`~/.jmri-cli/shell_history`), la **complétion TAB** sur tout l'arbre de commandes, des
lignes multi-commandes séparées par `;`, une commande `wait` pour enchaîner un `--hold`
et une commande suivante, et une **syntaxe en phrase** plus naturelle pour la
vitesse/direction (`speed Autorail at 30 for 30 up 5 down 6 forward`) en plus de la
forme classique à base d'options. Quitter le shell laisse toujours le réseau en
sécurité : toute locomotive encore en mouvement déclenche une invite de
ralentissement-puis-libération, et les fonctions actives (éclairages) sont coupées
avant la fermeture de la connexion, plutôt que d'être abandonnées en l'état.

Chaque commande fonctionne aussi en mode ponctuel depuis un terminal classique, pour le
scripting, l'automatisation, ou des vérifications/dépannages manuels rapides.

Voir la [référence CLI](docs/cli.md).

## Outils MCP

Le serveur MCP expose actuellement 50 outils couvrant les principales fonctions de JMRI.

Voir la référence complète :

- [Référence des outils MCP](mcp-tools.md)

## État du projet

**v1.0**

Le projet est pleinement fonctionnel et activement maintenu.

Les améliorations futures, demandes de fonctionnalités et éléments de la feuille de route sont suivis sur le [tableau de projet](https://github.com/orgs/HO44-PROJECT/projects) et les [issues](../../issues).

## Prérequis

- Python ≥ 3.10 (développé en 3.12)
- Un serveur JMRI Web Server en cours d'exécution (testé avec JMRI 5.4)

Voir [docs/install.md](docs/install.md) pour les détails d'installation.

## Documentation

### Prise en main

- **[Guide d'installation](INSTALL.md)** — toutes les combinaisons d'installation (CLI, `.mcpb` Claude Desktop, pont Kira), configuration et premières commandes
- **[Développer sur ce dépôt](docs/install.md)** — installations éditables depuis une copie clonée, pour travailler sur le code lui-même

### Assistants IA

- **[Configuration Claude Desktop / Claude Code](docs/llm-setup-claude.md)** — connecter votre assistant IA à JMRI
- **[Configuration xiaozhi / Kira](docs/llm-setup-xiaozhi.md)** — exposer le contrôle JMRI aux assistants vocaux

### Utilisateurs avancés

- **[Référence CLI](docs/cli.md)** — référence des commandes `jmri-cli`
- **[Mode exhibition](docs/exhibition.md)** — mode à sécurité restreinte pour les démonstrations publiques
- **[Architecture](docs/architecture.md)** — conception des modules, clients JMRI, implémentation WebSocket
- **[Tests](docs/testing.md)** — suites de tests simulés et réels, configuration de sécurité matérielle
- **[Ressources](docs/resources.md)** — références pour JMRI, MCP, et xiaozhi/Kira

### Projet

- **[ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md)** — remerciements aux projets open-source dont dépend ce projet
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — lignes directrices de contribution et conventions du projet

## Configuration

| Variable | Défaut | Description |
|---|---|---|
| `JMRI_URL` | `http://localhost:12080` | URL de base du serveur JMRI Web Server |
| `EXHIBITION_PASSWORD` | `this is sparta` | Mot de passe requis pour sortir du mode exhibition. Voir [Mode exhibition](docs/exhibition.md). |
| `EXHIBITION_ALLOWED_ADDRESSES` | (aucun) | Adresses DCC (séparées par des virgules) auxquelles les locomotives sont restreintes tant que le mode exhibition est actif. |
| `EXHIBITION_START_ON` | (désactivé) | Si défini à `1`/`true`/`yes`/`on`, le serveur démarre déjà en mode exhibition. |

## Crédits

<img src="https://avatars.githubusercontent.com/u/159026337?v=4" width="80" height="80" alt="MrJ" align="left" style="margin-right: 12px; border-radius: 50%;">

Conçu et maintenu par **[MrJ](https://github.com/HO44-PROJECT)**.

Questions, bugs et demandes de fonctionnalités sont les bienvenus via les [issues](../../issues).

## Licence

[AGPL-3.0-or-later](LICENSE)

Choisie délibérément plutôt qu'une licence permissive (MIT/Apache), pour que quiconque modifie ce projet et le propose en tant que service réseau (pas seulement en redistribuant le code) doive aussi publier son code source modifié.

Voir le [texte de la licence](LICENSE) pour les termes exacts, et [NOTICE.md](NOTICE.md) (en anglais) pour l'attribution requise en cas de réutilisation.

### Code tiers

`xiaozhi_wrapper` (partie du package `jmri-mcp`) est adapté de l'exemple MCP pipe de [xiaozhi-esp32](https://github.com/78/xiaozhi-esp32) (licence MIT, Copyright (c) 2025 Shenzhen Xinzhi Future Technology Co., Ltd. et les contributeurs du projet).

Voir la documentation du package :

`packages/jmri-mcp/src/xiaozhi_wrapper/__init__.py`
