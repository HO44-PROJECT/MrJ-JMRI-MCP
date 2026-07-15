"""Executor-mode MCP tools: set_executor_mode, get_executor_mode.

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
"""

import logging

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
