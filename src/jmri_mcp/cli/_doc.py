"""Short, inviting one-line descriptions for each top-level jmri-cli command group.

Kept separate from parser.py so the "what does this command group do, and
why would I want it" copy is easy to scan and edit in one place, rather
than buried inline among argparse wiring calls.
"""

GROUP_HELP = {
    "power": "Control power to your DCC systems",
    "status": "Quick health check: is JMRI reachable, and what's the power state",
    "roster": "Browse your locomotive roster",
    "throttle": "Drive your locomotives: speed, direction, functions, lights",
    "light": "Control your layout lights",
    "turnout": "Control your turnouts",
    "sensor": "Check your sensors (read-only)",
    "signal": "Control your signal masts",
}
