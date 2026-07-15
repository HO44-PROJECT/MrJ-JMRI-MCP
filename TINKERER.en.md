*[Français](TINKERER.fr.md)*

# 🔧 Tinkerer

**Runs the network, not just the trains.** You set up sessions, manage power, throw
turnouts, and get the layout ready before handing it to a conductor — or you're operating
solo and want more than "drive the loco."

This page lists the phrases that work today. Everything in
[CONDUCTOR.en.md](CONDUCTOR.en.md) still applies; this adds the layout-management layer
on top.

---

## Power

> "Cut the power" · "cut everything"
> "Turn everything on"
> "Turn on the Ohara system"

`power_off_all`/`power_on_all` are the real "stop absolutely everything" and "restore
everything" buttons — they cut power on every DCC system, reaching every locomotive
regardless of who's driving it (a JMRI panel, another session, not just this one). Naming
power/current always routes here, never to the motion-only emergency stop — "cut the
power" and "stop everything" are NOT the same request.

> "What's the power state?"

## Turnouts

> "Set turnout 5 to closed"
> "Throw the turnout by the depot"
> "Close every turnout"
> "Throw all turnouts"

The bulk phrasing sets *every* turnout to the same state in one call — not a
per-turnout restore to some previous position.

## Layout lights

Depot, street, signal lamps — JMRI's own `Light` objects, distinct from a locomotive's
headlights (see [CONDUCTOR.en.md](CONDUCTOR.en.md) for those).

> "Turn on the street lights"
> "Turn on all the lights" (no locomotive named → this, not a loco's lights)

## Signals

> "Set the signal at block 3 to yellow"
> "What's the signal at the station showing?"

## Whole-layout modes

Night/day mode is covered in [CONDUCTOR.en.md](CONDUCTOR.en.md) — it's a simple
"ambiance" command anyone can use. This is the session-management layer around it:

> "I'm done for today, secure the layout" — smooth stop for every running locomotive,
> lights off, layout lights off, throttles released: the end-of-session "put everything
> away" command.
> "Release the locomotives" — hands back control (to a JMRI panel or another session)
> without changing anything about their current state.

`secure_layout` is deliberately gentler than `power_off_all` (which also reaches
locomotives nobody here is driving) and more thorough than `emergency_stop_all` (motion
only, no lights, no release).

## Exhibition mode

> "Exhibition mode" · "passe en mode démo"

A restricted-safety mode for public demos — kids or general visitors trying voice
control. While it's on: power can't be turned on (turning it off still works, as an
emergency cut), every locomotive moves forward-only at one fixed, moderate speed no
matter what's asked, and only allow-listed DCC addresses (if you've configured any) can
be driven. Lights and functions aren't restricted — visitors toggling a headlight or
bell is part of the fun, not a safety concern.

> "Exit exhibition mode"

Requires the password you configured at install time — see
[docs/exhibition.md](docs/exhibition.md) for setup and full details.

---

Want the full 50-tool reference, session-scripting details, or JMRI/protocol internals?
See [ENGINEER.en.md](ENGINEER.en.md) and [mcp-tools.md](mcp-tools.md). Just want to drive
a train? [CONDUCTOR.en.md](CONDUCTOR.en.md).
