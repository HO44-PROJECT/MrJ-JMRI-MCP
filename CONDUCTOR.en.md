*[Français](CONDUCTOR.fr.md)*

# 🚂 Conductor

**The simple path.** You just want to run trains.

You could be a visitor at an exhibition, a kid trying this for the first time, or the
layout owner who just wants to drive without thinking about DCC addresses or JMRI
internals. You talk (or type) to the assistant in plain language, and it drives.

This page lists the phrases that work today. Say the locomotive's name if you know it
("the Autorail") — the assistant resolves it to the right DCC address for you.

For the tools these phrases map to, see [mcp-tools.md](mcp-tools.md). For the
restrictions an exhibition/demo session applies on top of this (speed caps, forward-only,
no power control), see [docs/exhibition.md](docs/exhibition.md) — this page documents
what you can *say*, not what a given session is *allowed* to do.

---

## Get a locomotive ready

> "Prepare the Autorail" · "get the 3 ready"

Acquires the locomotive, faces it forward, turns its lights on — one call, ready to
drive.

## Drive

> "Speed up the 3 to 40%"
> "Stop the Autorail"
> "Turn the 3 around" (reverse direction)
> "Run the Autorail forward for 10 seconds"
> "Brake the Autorail over 5 seconds" · "Bring the 3 to a smooth stop over 5 seconds"

A duration ("for 10 seconds") makes the assistant handle the wait and the stop for you —
you don't need to ask it to stop afterward. "Brake ... over N seconds" slows down
gradually to a stop instead of stopping abruptly.

## Lights

> "Turn on the Autorail's lights"
> "Turn off the 3's headlight"

## Put it away

> "Park the Autorail" · "put the 3 to bed"

Smooth stop, lights off, control released — the polite way to end a session with one
locomotive.

## Stop everything, right now

> "Stop everything!"

Emergency-stops every locomotive currently being driven, immediately. This is a motion
stop, not a power cut — see [TINKERER.en.md](TINKERER.en.md) if you need to cut power to
the whole layout.

## Night and day

> "Night mode" — every layout light and every locomotive currently being driven, lights on
> together.
> "Day mode" — same, but off.

## What locomotives do I have?

> "What locomotives do I have?"
> "What functions does the Autorail have?"

Useful before naming a function by effect ("turn on the cabin lights") rather than by
number.

## What's going on?

> "What's happening on the layout?"
> "Is everything ready?"

One-shot overview: is JMRI reachable, which locomotives are running, at what speed.

---

Want more control — turnouts, layout lights, power, signals? See
[TINKERER.en.md](TINKERER.en.md). Want the full tool-by-tool reference, or to
script/automate the layout? See [ENGINEER.en.md](ENGINEER.en.md).
