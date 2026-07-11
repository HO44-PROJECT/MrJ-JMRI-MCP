"""Short, inviting one-line descriptions for each top-level jmri-cli command group.

Kept separate from parser.py so the "what does this command group do, and
why would I want it" copy is easy to scan and edit in one place, rather
than buried inline among argparse wiring calls.
"""

GROUP_HELP = {
    "light": "Control your layout lights",
    "power": "Control power to your DCC systems",
    "roster": "Browse your locomotive roster",
    "sensor": "Check your sensors",
    "signal": "Control your signal masts",
    "status": "Quick health check: is JMRI reachable, and what's the power state",
    "throttle": "Drive your locomotives: speed, direction, functions, lights",
    "turnout": "Control your turnouts",
}
