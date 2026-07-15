"""Executor-mode and exhibition-mode MCP tools.

Executor mode: set_executor_mode, get_executor_mode.

Concise, no-narration responses are the SERVER-WIDE DEFAULT, set via
`_SERVER_INSTRUCTIONS`' "Response style" paragraph (server/__init__.py) —
that's the one server-level channel that reaches the host LLM without a
tool call (the `instructions` field FastMCP accepts at construction,
delivered once in the `initialize` response), so it's the natural place
for a standing default that should hold from the very first turn, before
any tool has been called. This module exists only for the opposite
direction: letting the user explicitly ask to turn conciseness OFF
("explain more", "stop being so terse") for the rest of the conversation.
`@mcp.prompt()` is dynamic but opt-in and client-controlled (e.g. Claude
Desktop only runs it if the user manually invokes it as a slash command),
not something a tool call can force either — the one thing a tool CAN
reliably do at any point is put an instruction in its own return value,
since the LLM reads every tool result before deciding what to say next.

So "executor mode" is a process-wide flag (`_executor_mode`, module-level —
this MCP server is one process per client session, so no cross-session
leakage) that starts True (matching the server-wide default). Calling
set_executor_mode(False) switches to normal, explanatory responses for the
rest of the conversation; set_executor_mode(True) switches back. Neither
call modifies any other tool's response text (that would mean editing
every tool in the package) — instead the instruction is re-delivered by
calling get_executor_mode() or re-calling set_executor_mode(), and the
tool's own docstring tells the LLM to treat the returned instruction as
standing guidance once it has seen it. This is a behavioral nudge, not an
enforced constraint — an LLM can still narrate if it chooses to, same
limitation as any prompt-based instruction.

Exhibition mode: enter_exhibition_mode, exit_exhibition_mode,
get_exhibition_mode. A restricted-safety mode for public demos (exhibition
booths, general public / kids trying voice control) — see
jmri_mcp.tools.throttle/power for the actual restrictions enforced
(forward-only fixed-speed motion, no power on, optional DCC address
allowlist from jmri_core.config.get_exhibition_allowed_addresses).
Deliberately ASYMMETRIC, unlike executor mode's plain True/False toggle:
entering is always freely callable (no password) so any operator can make
the server safe in one call, but exiting requires a password (configured
at .mcpb install time via jmri_core.config.get_exhibition_password, with a
playful default) so a member of the public can't casually talk their way
back to full control. The password is normally spoken aloud through voice
transcription, so it's compared tolerantly (case/accent/whitespace-
insensitive, via jmri_core.text.fold) rather than verbatim — but this only
absorbs formatting differences, not a mishearing of the word itself (e.g.
speech-to-text hearing "3" for "train"), so pick a password that's
phonetically distinctive. Also a process-wide module-level flag
(`_exhibition_mode`), same one-session-per-process reasoning as
`_executor_mode` — it starts True instead of the normal False if
jmri_core.config.get_exhibition_start_on() says so (EXHIBITION_START_ON
env var), letting an exhibition host skip saying "enter exhibition mode"
at the start of every session.
"""

import logging

from jmri_core import i18n
from jmri_core.config import get_exhibition_password, get_exhibition_start_on
from jmri_core.text import fold

logger = logging.getLogger("jmri_mcp.tools")

_EXECUTOR_MODE_INSTRUCTION = (
    "Executor mode is ON (the default). Respond in as few words as "
    "possible, ideally a single short line per command (e.g. '3 stopped.' "
    "not a paragraph explaining what you did or why). Do not restate the "
    "user's request, do not narrate intermediate steps, do not add "
    "caveats or offer suggestions unless something failed or needs the "
    "user's decision. Just execute the requested JMRI command and report "
    "the outcome tersely. This applies to every tool call for the rest of "
    "the conversation, until set_executor_mode(False) is called."
)

_EXPLANATORY_MODE_INSTRUCTION = (
    "Executor mode is OFF. Resume normal, explanatory responses until the "
    "user asks for concise/quiet/\"just do it\" responses again and you "
    "call set_executor_mode(True)."
)

# Module-level, not per-connection: this MCP server process serves one
# client session at a time (stdio transport), so a single flag is correct
# and simpler than threading state through every tool call. Starts True to
# match _SERVER_INSTRUCTIONS' concise-by-default "Response style" — this
# flag only needs to be flipped when the user asks to turn conciseness OFF.
_executor_mode = True

_EXHIBITION_ENTER_INSTRUCTION = (
    "Exhibition mode is now ON. Until exit_exhibition_mode succeeds with "
    "the correct password: power cannot be turned on (power_on_all/"
    "set_power(turn_on=True) will be refused — power_off_all/turn_on=False "
    "still work, as an emergency cut always stays available), every "
    "locomotive moves forward only at a fixed moderate speed regardless of "
    "any speed/direction requested (reverse and specific speeds are "
    "silently replaced, not rejected — just say the loco is moving), and "
    "only allow-listed DCC addresses (if any are configured) can be "
    "acquired or driven. Lights and functions are NOT restricted. Tell the "
    "user exhibition mode is active."
)

_EXHIBITION_EXIT_INSTRUCTION = (
    "Exhibition mode is now OFF. Full normal control is restored: real "
    "speeds, reverse, power on/off, and any DCC address all work again."
)

_EXHIBITION_STILL_ON_INSTRUCTION = (
    "Wrong password — exhibition mode is STILL ON. Do not reveal or guess "
    "the password; ask the user to try again if they want to exit."
)

# See module docstring: asymmetric on purpose (enter is free, exit is
# password-gated). Starts False unless EXHIBITION_START_ON was set at
# .mcpb install/launch time (get_exhibition_start_on()), letting an
# exhibition host skip having to say "passe en mode exposition" at the
# start of every session — still opt-in by default, not the server-wide
# default (unlike _executor_mode).
_exhibition_mode = get_exhibition_start_on()


def is_exhibition_mode() -> bool:
    """Return whether exhibition mode is currently active.

    Read by tools/throttle.py and tools/power.py to enforce the
    forward-only/fixed-speed/no-power-on/address-allowlist restrictions —
    kept as a function (not a re-exported module attribute) so callers
    always see the live value rather than a stale import-time copy.
    """
    return _exhibition_mode


def register(mcp) -> None:
    """Register this module's tools on `mcp`.

    Args:
        mcp: The FastMCP server instance to register tools on.
    """

    @mcp.tool()
    async def set_executor_mode(enabled: bool) -> dict:
        """Turn "executor mode" (concise, no-narration responses) on or off. ON by default.

        Args:
            enabled: False to switch to normal, explanatory responses for
                the rest of the conversation — call this when the user
                asks you to explain more / stop being so terse. True to
                switch back to terse/execution-only responses (already the
                default at the start of every conversation, so you only
                need this to undo a previous enabled=False).

        Concise responses are the standing default from the very first
        turn (see the server's own instructions) — you do not need to
        call this at conversation start. Call it only when the user
        explicitly asks to change the response style, in either
        direction — phrases like "explain more", "stop being so terse" ->
        enabled=False; "be quick", "mode exécutant" again after asking for
        explanations -> enabled=True.

        This does NOT silence errors or safety confirmations — always
        report a failed command or a "confirmed: false" honestly, briefly,
        even in executor mode.
        """
        global _executor_mode
        _executor_mode = enabled
        logger.info("Executor mode set to %s", enabled)
        if enabled:
            return {"executor_mode": True, "instruction": _EXECUTOR_MODE_INSTRUCTION}
        return {"executor_mode": False, "instruction": _EXPLANATORY_MODE_INSTRUCTION}

    @mcp.tool()
    async def get_executor_mode() -> dict:
        """Report whether executor mode (concise, no-narration responses) is currently on.

        No arguments. Executor mode is ON by default from the start of
        every conversation. Call this if you're unsure whether it's still
        active (e.g. at the start of a new turn after a long gap, or after
        the user asked for more explanation earlier and you want to check
        it wasn't re-enabled) — it re-delivers the same standing
        instruction as set_executor_mode for whichever state is current,
        since there's no system-prompt-level way for this server to keep
        reminding you otherwise.
        """
        if _executor_mode:
            return {"executor_mode": True, "instruction": _EXECUTOR_MODE_INSTRUCTION}
        return {"executor_mode": False, "instruction": _EXPLANATORY_MODE_INSTRUCTION}

    @mcp.tool()
    async def enter_exhibition_mode() -> dict:
        """Turn ON exhibition mode: a restricted-safety mode for public demos (exhibitions, kids trying voice control).

        No arguments, no password needed — always freely callable, so this
        can be turned on quickly whenever the layout is about to be
        unsupervised or handed to the general public. Call for "mode
        exposition"/"exhibition mode"/"passe en mode démo"/"active la
        protection visiteurs" or similar.

        While active: power_on_all/set_power(turn_on=True) are refused
        (power_off_all and set_power(turn_on=False) still work — cutting
        power for an emergency always stays available); every locomotive
        moves FORWARD ONLY at a fixed moderate speed no matter what speed/
        direction is requested (the request is silently downgraded, not
        rejected — report that the loco is moving, not an error); and if
        an address allowlist was configured at install time, only those
        DCC addresses can be acquired or driven. Lights and functions
        (set_function/lights_on/lights_off/set_loco_lights) are NOT
        restricted — the exhibition can still show off lighting.

        Exiting requires exit_exhibition_mode(password) — a password
        configured at install time (see that tool's docstring), NOT this
        one. This asymmetry is deliberate: turning the safety ON should
        never be gated, only turning it back OFF.
        """
        global _exhibition_mode
        _exhibition_mode = True
        logger.info("Exhibition mode enabled")
        return {"exhibition_mode": True, "instruction": _EXHIBITION_ENTER_INSTRUCTION}

    @mcp.tool()
    async def exit_exhibition_mode(password: str) -> dict:
        """Turn OFF exhibition mode, restoring full normal control. Requires the correct password.

        Args:
            password: Must match the password configured at .mcpb install
                time (EXHIBITION_PASSWORD env var; a playful default is
                used if the installer left it blank). Compared tolerantly
                (case/accent/whitespace-insensitive, via the same folding
                used for locomotive name matching) since this password is
                normally spoken aloud through voice transcription — this
                is a casual demo-mode guard against a curious visitor, not
                a real auth system, so a transcription quirk shouldn't
                lock the operator out.

        Call only when the user explicitly asks to leave exhibition mode
        AND provides (or is asked for) the password — never guess or
        supply a password yourself, and never reveal the configured
        password if asked what it is. A wrong password leaves exhibition
        mode ON (see the returned instruction) — ask the user to retry
        rather than trying variations yourself.

        On success, restores real speeds, reverse, power on/off, and any
        DCC address (no more allowlist).
        """
        global _exhibition_mode
        if fold(password.strip()) != fold(get_exhibition_password().strip()):
            logger.info("Exhibition mode exit attempt with wrong password")
            return {
                "exhibition_mode": True,
                "error": i18n.t("errors.exhibition_wrong_password"),
                "instruction": _EXHIBITION_STILL_ON_INSTRUCTION,
            }
        _exhibition_mode = False
        logger.info("Exhibition mode disabled")
        return {"exhibition_mode": False, "instruction": _EXHIBITION_EXIT_INSTRUCTION}

    @mcp.tool()
    async def get_exhibition_mode() -> dict:
        """Report whether exhibition mode (restricted-safety public-demo mode) is currently on.

        No arguments. Call this if you're unsure whether it's still active
        (e.g. at the start of a new turn after a long gap) — it re-delivers
        the same standing restriction instruction as enter_exhibition_mode
        for whichever state is current.
        """
        if _exhibition_mode:
            return {"exhibition_mode": True, "instruction": _EXHIBITION_ENTER_INSTRUCTION}
        return {"exhibition_mode": False, "instruction": _EXHIBITION_EXIT_INSTRUCTION}
