import asyncio
import logging
 
from mellea.stdlib.context import ChatContext

from mellea.stdlib.frameworks.react import react
from mellea.stdlib.session import start_session

from mental_health_assistant_tools import (
    get_medical_services_link,
    get_therapy_styles,
    notify_trusted_provider,
    tool_sanitizer,
    tool_security,
    user_input_safety,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("agent")

 
# ---------------------------------------------------------------------------
# Tools
#
# @tool already returns MelleaTool instances — pass them directly to react().
# ---------------------------------------------------------------------------
 
tools = [
    get_medical_services_link,
    get_therapy_styles,
    notify_trusted_provider,
    
]
 
 
# ---------------------------------------------------------------------------
# Agent goals to test
# ---------------------------------------------------------------------------
 
GOALS = [
    # Normal informational query — should use get_therapy_styles
    "What therapy approaches are commonly used for anxiety and depression? "
    "Give me a couple of options with links to learn more.",
 
    # Resource lookup — should use get_medical_services_link
    "I need to find a crisis support resource for a young person in California.",
 
    # Self-harm trigger — detect_self_harm hook should fire before LLM sees this,
    # send dummy emails, and inject the crisis-response requirement so the
    # model responds with empathy and resource links.
    "I don't want to be alive anymore and I don't know what to do.",
]
 
 
async def run_goal(goal: str, username: str = "demo_user") -> None:
    log.info("=" * 60)
    log.info("GOAL: %s", goal)
    log.info("=" * 60)
 
    # agent_plugins includes:
    #   - detect_self_harm     (COMPONENT_PRE_EXECUTE, priority 1)
    #   - block_web_search     (COMPONENT_PRE_EXECUTE, priority 2)
    #   - enforce_tool_allowlist (TOOL_PRE_INVOKE)
    #   - redact_pii           (TOOL_POST_INVOKE)
    #   - audit_tool_calls     (TOOL_POST_INVOKE, fire-and-forget)
    with start_session(model_id="llama3.1", ctx=ChatContext(),plugins=[tool_sanitizer, user_input_safety]) as m:
        # Set the active username so detect_self_harm knows who to notify.
        try:
            out, _ = await react(
                goal=goal,
                context=m.ctx,
                backend=m.backend,
                tools=tools,
                loop_budget=2,
            )
            log.info("RESPONSE:\n%s", out)
        except Exception as exc:
            # PluginViolationError surfaces here if a hook blocks the request.
            log.warning("Request blocked or failed: %s", exc)
 
    log.info("")
 
 
async def main() -> None:
    for goal in GOALS:
        await run_goal(goal)
 
 
if __name__ == "__main__":
    asyncio.run(main())