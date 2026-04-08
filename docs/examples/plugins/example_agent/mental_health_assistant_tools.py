# pytest: ollama, e2e
#
# Tool hook plugins — safety and security policies for tool invocation.
#
# This example demonstrates four enforcement / repair patterns using
# TOOL_PRE_INVOKE and TOOL_POST_INVOKE hooks, built on top of the @tool
# decorator examples:
#
#   1. Tool allow list     — blocks any tool not on an explicit approved list
#   2. Argument validator  — inspects args before invocation (e.g., blocks
#                            disallowed patterns in calculator expressions)
#   3. Tool audit logger   — fire-and-forget logging of every tool call
#   4. Arg sanitizer       — auto-fixes tool args before invocation instead of
#                            blocking (e.g., strips unsafe chars from calculator
#                            expressions and normalises location strings)
#
# Run:
#   uv run python docs/examples/plugins/tool_hooks.py

from dataclasses import dataclass
import logging
import re

from mellea import start_session
from mellea.backends import ModelOption, tool
from mellea.plugins import (
    HookType,
    PluginMode,
    PluginResult,
    PluginSet,
    PluginViolationError,
    block,
    hook,
)
from mellea.stdlib.functional import _call_tools
from mellea.stdlib.requirements import uses_tool


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("fancy_logger").setLevel(logging.ERROR)
log = logging.getLogger("tool_hooks")


# ---------------------------------------------------------------------------
# Tools (same as tool_decorator_example.py)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TrustedContacts:
    parent_email: str
    provider_email: str
    provider_name: str
 
 
# Stub — replace with a real DB lookup (see user_system_information.py).
_TRUSTED_CONTACTS: dict[str, TrustedContacts] = {
    "demo_user": TrustedContacts(
        parent_email="parent@example.com",
        provider_email="therapist@example.com",
        provider_name="Dr. Jane Smith",
    ),
}
 
 
def get_trusted_contacts(username: str) -> TrustedContacts | None:
    return _TRUSTED_CONTACTS.get(username.strip().lower())


_MEDICAL_SERVICES: dict[str, dict[str, str]] = {
    "crisis": {
        "name": "988 Suicide & Crisis Lifeline",
        "url": "https://988lifeline.org/",
        "description": "Free, confidential support 24/7 for people in distress.",
    },
    "youth": {
        "name": "California Youth Crisis Line",
        "url": "https://calyouth.org/cycl/",
        "description": "Crisis support specifically for young people in California.",
    },
    "chat": {
        "name": "Crisis Text Line",
        "url": "https://www.crisistextline.org/",
        "description": "Text HOME to 741741 to reach a crisis counselor.",
    },
    "eating_disorders": {
        "name": "Alliance for Eating Disorders",
        "url": "https://www.allianceforeatingdisorders.com/",
        "description": "Helpline and resources for eating disorder support.",
    },
    "general": {
        "name": "SAMHSA National Helpline",
        "url": "https://www.samhsa.gov/find-help/national-helpline",
        "description": "Free treatment referral and info, 24/7, in English and Spanish.",
    },
}

@tool
def get_medical_services_link(category: str) -> str:
    """Return a crisis or support resource link for the given category.
 
    Args:
        category: One of: crisis, youth, chat, eating_disorders, general.
    """
    key = category.strip().lower()
    service = _MEDICAL_SERVICES.get(key, _MEDICAL_SERVICES["general"])
    return (
        f"{service['name']}\n"
        f"URL: {service['url']}\n"
        f"About: {service['description']}"
    )


@tool()
def search_web(query: str, max_results: int = 5) -> list[str]:
    """Search the web for information.

    Args:
        query: Search query
        max_results: Maximum number of results to return
    """
    return [f"Result {i + 1} for '{query}'" for i in range(max_results)]


 
def _run_notification_obligation(
    username: str,
    trigger_message: str,
    #cfg: SMTPConfig,
) -> str:
    contacts = get_trusted_contacts(username)
    if contacts is None:
        log.warning("[obligation] no trusted contacts for username=%r", username)
        return f"No trusted contacts on file for '{username}'. No emails sent."
 
    subject = "Important: your child may need support"
    parent_body = (
        f"Dear parent or guardian,\n\n"
        f"We want to let you know that {username} may be experiencing some "
        f"difficult feelings and could benefit from your support.\n\n"
        f"If you believe they are in immediate danger, please call 988 "
        f"(Suicide & Crisis Lifeline) or your local emergency services.\n\n"
        f"— The Care Team"
    )
    provider_body = (
        f"Dear {contacts.provider_name},\n\n"
        f"A message from your patient '{username}' has been flagged for "
        f"clinical review:\n\n"
        f"  \"{trigger_message}\"\n\n"
        f"Please follow up according to your care protocol.\n\n"
        f"— Automated Alert System"
    )
 
    results = []
    for label, to_email, body in [
        ("parent", contacts.parent_email, parent_body),
        ("provider", contacts.provider_email, provider_body),
    ]:
        try:
            #_send_email(to_email, subject, body, cfg)
            results.append(f"{label} notified at {to_email}")
        except Exception as exc:
            log.error("[obligation] failed to email %s=%r: %s", label, to_email, exc)
            results.append(f"{label} notification FAILED: {exc}")
 
    return "; ".join(results)

@tool
def notify_trusted_provider(username: str, reason: str) -> str:
    """Send an alert email to the trusted medical provider and parent/guardian
    registered for a user. Use when the conversation warrants clinical follow-up
    beyond what has already been sent automatically.
 
    Args:
        username: The user's account name (must match the trusted contacts registry).
        reason: Plain-language description of the clinical concern.
    """
    '''
    if _smtp_cfg is None:
        return (
            "Email notifications are not configured. "
            "Please call configure_smtp() at application startup."
        )
    '''
    return _run_notification_obligation(username, reason)


_THERAPY_STYLES: list[dict[str, str]] = [
    {
        "name": "Cognitive Behavioral Therapy (CBT)",
        "summary": (
            "Focuses on identifying and changing negative thought patterns "
            "that influence feelings and behavior. Widely used for anxiety, "
            "depression, and OCD."
        ),
        "learn_more": "https://www.apa.org/ptsd-guideline/patients-and-families/cognitive-behavioral",
    },
    {
        "name": "Dialectical Behavior Therapy (DBT)",
        "summary": (
            "Builds skills in mindfulness, distress tolerance, emotion regulation, "
            "and interpersonal effectiveness. Developed for borderline personality "
            "disorder; widely used for self-harm and intense emotions."
        ),
        "learn_more": "https://behavioraltech.org/resources/faqs/dialectical-behavior-therapy-dbt/",
    },
    {
        "name": "Acceptance and Commitment Therapy (ACT)",
        "summary": (
            "Encourages accepting difficult thoughts and feelings rather than "
            "fighting them, while committing to actions aligned with personal values."
        ),
        "learn_more": "https://contextualscience.org/act",
    },
    {
        "name": "Eye Movement Desensitization and Reprocessing (EMDR)",
        "summary": (
            "Uses guided eye movements to help process and reduce distress "
            "from traumatic memories. Recommended for PTSD."
        ),
        "learn_more": "https://www.emdr.com/what-is-emdr/",
    },
    {
        "name": "Person-Centered Therapy",
        "summary": (
            "A non-directive approach emphasising empathy and unconditional positive "
            "regard. Believes people have the inner resources to grow and heal."
        ),
        "learn_more": "https://www.simplypsychology.org/client-centred-therapy.html",
    },
    {
        "name": "Mindfulness-Based Cognitive Therapy (MBCT)",
        "summary": (
            "Combines CBT techniques with mindfulness practices to prevent "
            "depression relapse and manage anxiety."
        ),
        "learn_more": "https://www.mindfulnessstudies.com/mbct/",
    },
    {
        "name": "Somatic Therapy",
        "summary": (
            "Focuses on the mind-body connection, using body awareness and movement "
            "to process trauma and chronic stress."
        ),
        "learn_more": "https://www.goodtherapy.org/learn-about-therapy/types/somatic-psychotherapy",
    },
    {
        "name": "Narrative Therapy",
        "summary": (
            "Helps people reframe the stories they tell about their lives, "
            "separating problems from identity so they can author a preferred story."
        ),
        "learn_more": "https://www.goodtherapy.org/learn-about-therapy/types/narrative-therapy",
    },
]
 
@tool
def get_therapy_styles(filter_keyword: str = "") -> str:
    """Return a structured list of therapy modalities with descriptions and links.
 
    Args:
        filter_keyword: Optional keyword to filter results (e.g. 'trauma',
            'mindfulness', 'depression'). Leave empty to return all styles.
    """
    keyword = filter_keyword.strip().lower()
    styles = (
        [s for s in _THERAPY_STYLES
         if keyword in s["name"].lower() or keyword in s["summary"].lower()]
        if keyword else _THERAPY_STYLES
    )
 
    if not styles:
        return (
            f"No therapy styles matched '{filter_keyword}'. "
            "Try a broader term or leave the filter empty to see all styles."
        )
 
    lines = [
        f"• {s['name']}\n  {s['summary']}\n  Learn more: {s['learn_more']}"
        for s in styles
    ]
    return "\n\n".join(lines)
 


# ---------------------------------------------------------------------------
# Plugin 1 — Tool allow list (enforce)
#
# Only tools explicitly listed in ALLOWED_TOOLS may be called.  Any tool call
# for an unlisted tool is blocked before it reaches the function.
# ---------------------------------------------------------------------------

ALLOWED_TOOLS: frozenset[str] = frozenset({"get_medical_services_link", "search_web", "get_therapy_styles", "notify_trusted_provider"})



@hook(HookType.TOOL_PRE_INVOKE, mode=PluginMode.CONCURRENT, priority=5)
async def enforce_tool_allowlist(payload, _):
    """Block any tool not on the explicit allow list."""
    tool_name = payload.model_tool_call.name
    if tool_name not in ALLOWED_TOOLS:
        log.warning(
            "[allowlist] BLOCKED tool=%r — not in allowed set %s",
            tool_name,
            sorted(ALLOWED_TOOLS),
        )
        return block(
            f"Tool '{tool_name}' is not permitted",
            code="TOOL_NOT_ALLOWED",
            details={"tool": tool_name, "allowed": sorted(ALLOWED_TOOLS)},
        )
    log.info("[allowlist] permitted tool=%r", tool_name)


# ---------------------------------------------------------------------------
# Plugin 2 — Argument validator (enforce)
#
# Inspects the arguments before a tool is invoked.  For the calculator,
# reject expressions that contain characters outside the safe set.
# This runs after the allow list so it only sees permitted tools.
# ---------------------------------------------------------------------------

_CALCULATOR_ALLOWED_CHARS: frozenset[str] = frozenset("0123456789 +-*/(). ")


@hook(HookType.TOOL_PRE_INVOKE, mode=PluginMode.CONCURRENT, priority=10)
async def validate_tool_args(payload, _):
    """Validate tool arguments before invocation."""
    tool_name = payload.model_tool_call.name
    tool_args = payload.model_tool_call.args or {}
    if tool_name == "calculator":
        expression = tool_args.get("expression", "")
        disallowed = set(expression) - _CALCULATOR_ALLOWED_CHARS
        if disallowed:
            log.warning(
                "[arg-validator] BLOCKED calculator expression=%r (disallowed chars: %s)",
                expression,
                disallowed,
            )
            return block(
                f"Calculator expression contains disallowed characters: {disallowed}",
                code="UNSAFE_EXPRESSION",
                details={"expression": expression, "disallowed": sorted(disallowed)},
            )
        log.info("[arg-validator] calculator expression=%r is safe", expression)
    else:
        log.info("[arg-validator] no arg validation required for tool=%r", tool_name)


# ---------------------------------------------------------------------------
# Plugin 3 — Tool audit logger (fire-and-forget)
#
# Records every tool invocation outcome for audit purposes.  Uses
# fire_and_forget so it never adds latency to the main execution path.
# ---------------------------------------------------------------------------


@hook(HookType.TOOL_POST_INVOKE, mode=PluginMode.FIRE_AND_FORGET)
async def audit_tool_calls(payload, _):
    """Log the result of every tool call for audit purposes."""
    status = "OK" if payload.success else "ERROR"
    tool_name = payload.model_tool_call.name
    log.info(
        "[audit] tool=%r status=%s latency=%dms args=%s",
        tool_name,
        status,
        payload.execution_time_ms,
        payload.model_tool_call.args,
    )
    if not payload.success and payload.error is not None:
        log.error("[audit] tool=%r error=%r", tool_name, str(payload.error))


# ---------------------------------------------------------------------------
# Plugin 4 — Detect Self-Harm Message
# 
# Intercepts every user message and checks for a self-harm message, on a self-harm detection,
# block and sends message to parents and a trusted provider
# ---------------------------------------------------------------------------
_SELF_HARM_PATTERNS: list[re.Pattern] = [
        re.compile(r"\b(want to (hurt|kill|harm) (my)?self)\b", re.IGNORECASE),
        re.compile(r"\b(suicid(e|al)|self.harm|cutting myself)\b", re.IGNORECASE),
        re.compile(r"\b(don'?t want to (be alive|live anymore|exist))\b", re.IGNORECASE),
        re.compile(r"\b(end(ing)? (my|this) (life|pain))\b", re.IGNORECASE),
        re.compile(r"\b(no (reason|point) (in |to )?(living|going on))\b", re.IGNORECASE),
    ]
@hook(HookType.COMPONENT_PRE_EXECUTE, mode=PluginMode.SEQUENTIAL, priority=1)
async def detect_self_harm(payload, ctx):
    context_view = payload.context_view or []
    user_messages = [
            turn for turn in context_view
            if getattr(turn, "role", None) == "user"
        ]
    if not user_messages:
            return None
    latest_message = str(getattr(user_messages[-1], "content", ""))
    if not any(p.search(latest_message) for p in _SELF_HARM_PATTERNS):
            return None
    log.warning("[self-harm] Flagged message — triggering obligation pipeline.")
    _run_notification_obligation("username", latest_message)
    return block(
                f"A self harm message was detected, message sent to trusted providers and parents",
                code="USER_UNSAFE",
                details={"message": user_messages },
            )


    
# ---------------------------------------------------------------------------
# Plugin 4 — Arg sanitizer (repair)
#
# Instead of blocking, this plugin auto-fixes tool arguments before
# invocation.  Two repairs are applied:
#
#   calculator  — strips any character outside the safe arithmetic set so
#                 that the expression can still be evaluated.  A warning is
#                 logged showing what was removed.
#
#   get_weather — normalises the location string to title-case and strips
#                 leading/trailing whitespace (e.g. "  NEW YORK " → "New York").
#
# The plugin returns a modified ModelToolCall via model_copy so that the
# corrected args are what actually reaches the tool function.
# ---------------------------------------------------------------------------


@hook(HookType.TOOL_PRE_INVOKE, mode=PluginMode.CONCURRENT, priority=15)
async def sanitize_tool_args(payload, _) -> PluginResult:
    """Auto-fix tool arguments rather than blocking on unsafe input."""
    mtc = payload.model_tool_call
    tool_name = mtc.name
    args = dict(mtc.args or {})
    updated: dict[str, object] = {}

    if tool_name == "calculator":
        raw_expr = str(args.get("expression", ""))
        sanitized = "".join(c for c in raw_expr if c in _CALCULATOR_ALLOWED_CHARS)
        if sanitized != raw_expr:
            removed = set(raw_expr) - _CALCULATOR_ALLOWED_CHARS
            log.warning(
                "[sanitizer] calculator: stripped disallowed chars %s from expression=%r → %r",
                sorted(removed),
                raw_expr,
                sanitized,
            )
            updated["expression"] = sanitized

    elif tool_name == "get_weather":
        raw_location = str(args.get("location", ""))
        normalised = raw_location.strip().title()
        if normalised != raw_location:
            log.info(
                "[sanitizer] get_weather: normalised location %r → %r",
                raw_location,
                normalised,
            )
            updated["location"] = normalised

    if not updated:
        return None  # nothing changed — pass through as-is

    new_args = {**args, **updated}
    new_call = dataclass.replace(mtc, args=new_args)
    modified = payload.model_copy(update={"model_tool_call": new_call})
    return PluginResult(continue_processing=True, modified_payload=modified)


# ---------------------------------------------------------------------------
# Compose into PluginSets for clean session-scoped registration
# ---------------------------------------------------------------------------

tool_security = PluginSet(
    "tool-security", [enforce_tool_allowlist, validate_tool_args, audit_tool_calls]
)

tool_sanitizer = PluginSet("tool-sanitizer", [sanitize_tool_args, audit_tool_calls])


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def _run_scenario(name: str, fn) -> None:
    """Run a scenario function, logging any PluginViolationError without halting."""
    log.info("=== %s ===", name)
    try:
        fn()
    except PluginViolationError as e:
        log.warning(
            "Execution blocked on %s: [%s] %s (plugin=%s)",
            e.hook_type,
            e.code,
            e.reason,
            e.plugin_name,
        )
    log.info("")


def scenario_1_allowed_tool(all_tools):
    """Scenario 1: allowed tool call (get_weather)."""
    with start_session(plugins=[tool_security]) as m:
        result = m.instruct(
            description="What is the weather in Boston for the next 3 days?",
            requirements=[uses_tool("get_weather")],
            model_options={ModelOption.TOOLS: all_tools},
            tool_calls=True,
        )
        tool_outputs = _call_tools(result, m.backend)
        if tool_outputs:
            log.info("Tool returned: %s", tool_outputs[0].content)
        else:
            log.error("Expected tool call but none were executed")


def scenario_2_blocked_tool(all_tools):
    """Scenario 2: blocked tool call (search_web not on allow list)."""
    with start_session(plugins=[tool_security]) as m:
        result = m.instruct(
            description="Search the web for the latest Python news.",
            requirements=[uses_tool("search_web")],
            model_options={ModelOption.TOOLS: all_tools},
            tool_calls=True,
        )
        tool_outputs = _call_tools(result, m.backend)
        if not tool_outputs:
            log.info("Tool call was blocked — outputs list is empty, as expected")
        else:
            log.warning("Expected tool to be blocked but it executed: %s", tool_outputs)


def scenario_3_safe_calculator(all_tools):
    """Scenario 3: safe calculator expression goes through."""
    with start_session(plugins=[tool_security]) as m:
        result = m.instruct(
            description="Use the calculator to compute 6 * 7.",
            requirements=[uses_tool("calculator")],
            model_options={ModelOption.TOOLS: all_tools},
            tool_calls=True,
        )
        tool_outputs = _call_tools(result, m.backend)
        if tool_outputs:
            log.info("Tool returned: %s", tool_outputs[0].content)
        else:
            log.error("Expected tool call but none were executed")


def scenario_4_blocked_calculator(all_tools):
    """Scenario 4: unsafe calculator expression is blocked."""
    with start_session(plugins=[tool_security]) as m:
        result = m.instruct(
            description=(
                "Use the calculator on this expression: "
                "__builtins__['print']('injected')"
            ),
            requirements=[uses_tool("calculator")],
            model_options={ModelOption.TOOLS: all_tools},
            tool_calls=True,
        )
        tool_outputs = _call_tools(result, m.backend)
        if not tool_outputs:
            log.info("Tool call was blocked — outputs list is empty, as expected")
        else:
            log.warning("Expected tool to be blocked but it executed: %s", tool_outputs)


def scenario_5_sanitizer_calculator(all_tools):
    """Scenario 5: arg sanitizer auto-fixes an unsafe calculator expression."""
    with start_session(plugins=[tool_sanitizer]) as m:
        result = m.instruct(
            description=(
                "Use the calculator on this expression: "
                "6 * 7 + __import__('os').getpid()"
            ),
            requirements=[uses_tool("calculator")],
            model_options={ModelOption.TOOLS: all_tools},
            tool_calls=True,
        )
        tool_outputs = _call_tools(result, m.backend)
        if tool_outputs:
            log.info(
                "Sanitized expression evaluated — tool returned: %s",
                tool_outputs[0].content,
            )
        else:
            log.error("Expected sanitized tool call but none were executed")


def scenario_6_sanitizer_location(all_tools):
    """Scenario 6: arg sanitizer normalises a messy location string."""
    with start_session(plugins=[tool_sanitizer]) as m:
        result = m.instruct(
            description="What is the weather in '  NEW YORK  '?",
            requirements=[uses_tool("get_weather")],
            model_options={ModelOption.TOOLS: all_tools},
            tool_calls=True,
        )
        tool_outputs = _call_tools(result, m.backend)
        if tool_outputs:
            log.info(
                "Weather fetched with normalised location — tool returned: %s",
                tool_outputs[0].content,
            )
        else:
            log.error("Expected tool call but none were executed")


# ---------------------------------------------------------------------------
# Main — six scenarios
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("--- Tool hook plugins example ---")
    log.info("")

    all_tools = [get_weather, search_web, calculate]

    _run_scenario(
        "Scenario 1: allowed tool — get_weather",
        lambda: scenario_1_allowed_tool(all_tools),
    )
    _run_scenario(
        "Scenario 2: blocked tool — search_web not on allow list",
        lambda: scenario_2_blocked_tool(all_tools),
    )
    _run_scenario(
        "Scenario 3: safe calculator expression",
        lambda: scenario_3_safe_calculator(all_tools),
    )
    _run_scenario(
        "Scenario 4: unsafe calculator expression blocked",
        lambda: scenario_4_blocked_calculator(all_tools),
    )
    _run_scenario(
        "Scenario 5: arg sanitizer auto-fixes calculator expression",
        lambda: scenario_5_sanitizer_calculator(all_tools),
    )
    _run_scenario(
        "Scenario 6: arg sanitizer normalises location in get_weather",
        lambda: scenario_6_sanitizer_location(all_tools),
    )