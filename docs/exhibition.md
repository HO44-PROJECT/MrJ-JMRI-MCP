# Exhibition mode

A restricted-safety mode for public demos — exhibitions, kids trying voice control —
where the layout must stay safe to operate unsupervised. While active, motion and power
are locked down; everything else (lights, functions, roster/status reads) works normally.

## Turning it on and off

- **"mode exposition" / "exhibition mode" / "passe en mode démo"** → always works, no
  password needed, so any operator can make the layout safe in one sentence.
- **"sors du mode exposition" / "exit exhibition mode" / "désactive le mode démo"** →
  requires the password. If you don't give one in the same request, the assistant will
  ask for it.

The password check ignores case, accents, and extra whitespace (it's normally spoken
aloud, and voice transcription rarely reproduces those exactly) — but it can't recover
from the transcription mishearing the word itself (e.g. "train" coming back as "3" or
"Tren"). **Pick a password that's phonetically distinctive** — a word unlikely to be
confused with a number or another common word in whatever language you'll say it in.

You can also check the current state at any time: "is exhibition mode on?" →
`get_exhibition_mode()`.

## What's restricted

| | While exhibition mode is ON |
|---|---|
| Power | Turning power **ON** (`set_power(turn_on=True)`, `power_on_all`) is refused. Turning power **OFF** always still works — an emergency cut is never blocked. |
| Speed | Any requested speed is replaced with a fixed, moderate speed (30%) — the locomotive still moves, just not at the speed asked for. |
| Direction | Always forward. A request for reverse is refused outright. |
| DCC addresses | If an address allowlist is configured (see below), only those addresses can be acquired or driven — everything else is refused. |
| Lights / functions | **Not restricted.** Headlights, bell, whistle, etc. all work exactly as normal. |

## Configuration (set at `.mcpb` install time, or via environment variables)

| Setting | Env var | Effect |
|---|---|---|
| Exit password | `EXHIBITION_PASSWORD` | The password required for `exit_exhibition_mode`. Defaults to `this is sparta` if left blank — pick your own, see the phonetic-distinctiveness note above. |
| Allowed DCC addresses | `EXHIBITION_ALLOWED_ADDRESSES` | Comma-separated addresses (e.g. `4,5,6`) locomotives are restricted to while exhibition mode is on. Leave blank to allow any address. |
| Start already in exhibition mode | `EXHIBITION_START_ON` | Any of `1`/`true`/`yes`/`on` (case-insensitive). If set, the server starts already in exhibition mode — no need to say "enter exhibition mode" at the start of every session. |

## Notes

- Exhibition mode is a flag held by the running MCP server process — it does not persist
  across a server restart unless `EXHIBITION_START_ON` is set.
- There is no `jmri-cli` equivalent for exhibition mode: it's a voice/chat-only concept
  for a public audience, and anyone with CLI access already has direct access to the
  layout.
- Day/night automatic time-based restrictions are a separate, not-yet-implemented idea —
  exhibition mode today is a manual on/off, not a schedule.
