# NOTICE — License, attribution, and reuse

## Copyright

MrJ-JMRI-MCP
Copyright (C) 2026 HO44 PROJECT (MrJ)

## License

This project — `jmri-core`, `jmri-cli`, `jmri-mcp` (including the
`xiaozhi_wrapper` bridge and the Codex integration), the documentation, and
every configuration shipped in this repository — is licensed under the
**GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later)**. The
full license text is in [LICENSE](LICENSE).

The AGPL was chosen deliberately, not as a default. It is a copyleft
license: anyone who redistributes this project, a modified version of it, or
a derivative work — including running it as a network service (an MCP
server, a bridge, a hosted API) — must:

1. **Keep the copyright and license notices intact.** You may not strip,
   replace, or obscure the attribution above.
2. **Credit the original author** (MrJ / HO44 PROJECT) and link back to the
   original repository: <https://github.com/HO44-PROJECT/MrJ-JMRI-MCP>.
3. **Make the complete corresponding source available** under the same
   license, to anyone who receives the software or interacts with it over a
   network — this applies even if you only modify it and never
   "distribute" it in the traditional sense.
4. **License your modified or derivative version under AGPL-3.0-or-later
   too.** You cannot relicense this project, or a fork of it, under a more
   restrictive license, a permissive license, or "all rights reserved."

This applies **regardless of where or how you reuse the work** — a GitHub
fork, a copy pasted into another repository, a rebrand under a different
project name, a `.mcpb`/`.codex.zip` bundle redistributed elsewhere, a
write-up or tutorial, a video, a package registry listing, etc. The medium
doesn't matter; the obligations above do.

## Why this file exists

This project is published openly so other JMRI/model-railroad hobbyists and
MCP developers can build on it. That only works if reuse is honest: if
someone can silently drop the author's name, present the work as their own,
and strip the license, the incentive to share disappears for everyone.

**Removing or hiding attribution is not a grey area and not just bad
manners — it is a violation of the license this project is distributed
under.** Reused work found without the required attribution and license
will be treated as a license violation, and pursued as one (takedown
requests to the hosting platform or package registry, and other remedies
available under AGPL-3.0-or-later).

## What to do if you reuse this project

It's simple: say where it came from, keep the license, and keep it open.
Concretely, when you republish or build on this work, include something
like:

> Based on **MrJ-JMRI-MCP** by MrJ / HO44 PROJECT
> (<https://github.com/HO44-PROJECT/MrJ-JMRI-MCP>), licensed under
> AGPL-3.0-or-later.

That's it. Attribution and an open license back — not a fee, not a
restriction on what you build. Contributions, forks, and derivative
projects that follow this are genuinely welcome.

## Contact

- Questions, ideas, general discussion: [GitHub Discussions](https://github.com/HO44-PROJECT/MrJ-JMRI-MCP/discussions).
- Bugs and feature requests: [Issues](https://github.com/HO44-PROJECT/MrJ-JMRI-MCP/issues).

## Third-party code

`xiaozhi_wrapper` (part of the `jmri-mcp` package) is adapted from the MCP
pipe example in [xiaozhi-esp32](https://github.com/78/xiaozhi-esp32) (MIT
License, Copyright (c) 2025 Shenzhen Xinzhi Future Technology Co., Ltd. and
Project Contributors). See
`packages/jmri-mcp/src/xiaozhi_wrapper/__init__.py` for the full notice.

## Related projects

Same author (MrJ / HO44 PROJECT), same license and attribution rules apply:

- [MrJ-LayoutFX](https://github.com/HO44-PROJECT/MrJ-LayoutFX) — DCC-controlled ESP32 accessory decoder and lighting-effects engine.
- [MrJ DB-style train signals](https://github.com/HO44-PROJECT/MrJ-HO-scale-DB-style-Era-III-Train-Signals-Electronics) — the HO-scale Deutsche Bahn Era III signal electronics referenced in this project's docs.
