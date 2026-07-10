"""Executor-mode MCP tools: set_executor_mode, get_executor_mode.

MCP does have one server-level channel that reaches the host LLM without a
tool call: the `instructions` field FastMCP accepts at construction (see
`server/__init__.py`'s `_SERVER_INSTRUCTIONS`), delivered once in the
`initialize` response. But it's static and one-shot — set before the
server even starts, with no way to update it mid-conversation — so it
can't carry a flag that flips on/off as the user asks for it. `@mcp.prompt()`
is dynamic but opt-in and client-controlled (e.g. Claude Desktop only runs
it if the user manually invokes it as a slash command), not something a
tool call can force either. The one thing a tool CAN reliably do at any
point in the conversation is put an instruction in its own return value,
since the LLM reads every tool result before deciding what to say next —
that's the mechanism this module relies on for something that toggles
mid-session.

So "executor mode" is a process-wide flag (`_executor_mode`, module-level —
this MCP server is one process per client session, so no cross-session
leakage) that starts off. set_executor_mode(True) flips it on and returns
an explicit instruction string; from then on, every other tool's response
in this module is NOT modified (that would mean editing every tool in the
package) — instead the instruction is re-delivered by calling
get_executor_mode() or re-calling set_executor_mode(), and the tool's own
docstring tells the LLM to treat "executor mode is on" as standing guidance
for the rest of the conversation once it has seen it once. This is a
behavioral nudge, not an enforced constraint — an LLM can still narrate if
it chooses to, same limitation as any prompt-based instruction.
"""

import logging

logger = logging.getLogger("jmri_mcp.tools")

_EXECUTOR_MODE_INSTRUCTION = (
    "Executor mode is ON. From now on in this conversation: respond in as "
    "few words as possible, ideally a single short line per command (e.g. "
    "'3 stopped.' not a paragraph explaining what you did or why). Do not "
    "restate the user's request, do not narrate intermediate steps, do not "
    "add caveats or offer suggestions unless something failed or needs the "
    "user's decision. Just execute the requested JMRI command and report "
    "the outcome tersely. This applies to every tool call for the rest of "
    "the conversation, until set_executor_mode(False) is called."
)

# Module-level, not per-connection: this MCP server process serves one
# client session at a time (stdio transport), so a single flag is correct
# and simpler than threading state through every tool call.
_executor_mode = False


def register(mcp) -> None:
    """Register this module's tools on `mcp`.

    Args:
        mcp: The FastMCP server instance to register tools on.
    """

    @mcp.tool()
    async def set_executor_mode(enabled: bool) -> dict:
        """Turn "executor mode" on or off: a concise, no-narration response style.

        Args:
            enabled: True to switch to terse/execution-only responses for
                the rest of the conversation, False to go back to normal,
                explanatory responses.

        Call this when the user asks for a quiet/concise/"just do it"
        mode — phrases like "stop explaining", "just execute", "be quick",
        "mode exécutant", or similar. Once enabled, follow the returned
        instruction for every subsequent response in this conversation
        (not just tool calls) until the user asks to turn it off again and
        you call this with enabled=False.

        This does NOT silence errors or safety confirmations — always
        report a failed command or a "confirmed: false" honestly, briefly,
        even in executor mode.
        """
        global _executor_mode
        _executor_mode = enabled
        logger.info("Executor mode set to %s", enabled)
        if enabled:
            return {"executor_mode": True, "instruction": _EXECUTOR_MODE_INSTRUCTION}
        return {
            "executor_mode": False,
            "instruction": "Executor mode is OFF. Resume normal, explanatory responses.",
        }

    @mcp.tool()
    async def get_executor_mode() -> dict:
        """Report whether executor mode (concise, no-narration responses) is currently on.

        No arguments. Call this if you're unsure whether executor mode is
        still active (e.g. at the start of a new turn after a long gap) —
        it re-delivers the same standing instruction as set_executor_mode
        when the mode is on, since there's no system-prompt-level way for
        this server to keep reminding you otherwise.
        """
        if _executor_mode:
            return {"executor_mode": True, "instruction": _EXECUTOR_MODE_INSTRUCTION}
        return {"executor_mode": False}
