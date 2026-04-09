# pytest: ollama, e2e
#
# Tool hook plugins for the example mental health assistant agent.  This example includes:
# - A tool allow list plugin that blocks any tool calls for tools not explicitly allowed.
# - A tool output sanitizer that redacts potential PII from tool outputs before they enter context
# - A tool audit logger that records every tool call outcome for auditing purposes.
# - A self-harm message detector that blocks and triggers notifications if a user message indicates potential
#   self-harm intent.
#
# Run:
#   uv run python docs/examples/plugins/example_agent/mental_health_assistant_tools.py

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

def _send_email(to_email: str, subject: str, body: str) -> None:
    """Stub: prints the email instead of sending it."""
    print(
        f"\n[DUMMY EMAIL]\n"
        f"  To:      {to_email}\n"
        f"  Subject: {subject}\n"
        f"  Body:\n{body}\n"
        f"[END EMAIL]\n"
    )
    log.info("[dummy-smtp] would have sent email to=%r subject=%r", to_email, subject)

 
def _run_notification_obligation(
    username: str,
    trigger_message: str,
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
            _send_email(to_email, subject, body)
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

ALLOWED_TOOLS: frozenset[str] = frozenset({"get_medical_services_link", "get_therapy_styles", "notify_trusted_provider"})



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
# Plugin 2 — Tool PII detector 
#
# Ensures sensitive information is not passed into LLM context from tool output
# ---------------------------------------------------------------------------

_PII_PATTERNS: list[re.Pattern] = [
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
        re.compile(r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    ]
@hook(HookType.TOOL_POST_INVOKE, mode=PluginMode.SEQUENTIAL, priority=5)
async def redact_pii_from_tool_output(payload, _) -> PluginResult | None:
        """Scrub SSN / email / phone from tool output before it enters context."""
        raw: str = str(payload.tool_output or "")
        redacted = raw
        for pattern in _PII_PATTERNS:
            redacted = pattern.sub("[REDACTED]", redacted)
        if redacted == raw:
            return None
        log.warning("[pii] Redacted PII from output of tool=%r",
                    payload.model_tool_call.name)
        modified = payload.model_copy(update={"tool_output": redacted})
        return PluginResult(continue_processing=True, modified_payload=modified)



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
# Compose into PluginSets for clean session-scoped registration
# ---------------------------------------------------------------------------

user_input_safety = PluginSet("user-input-safety", [detect_self_harm])

tool_security = PluginSet(
    "tool-security", [enforce_tool_allowlist]
)


tool_sanitizer = PluginSet("tool-sanitizer", [redact_pii_from_tool_output, audit_tool_calls ])


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
    """Scenario 1: allowed tool call (get_therapy_styles)."""
    with start_session(plugins=[tool_security]) as m:
        result = m.instruct(
            description="What is cognitive behavioral therapy and provide a link to a reputable resource?",
            requirements=[uses_tool("get_therapy_styles")],
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



# ---------------------------------------------------------------------------
# Main — six scenarios
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("--- Tool hook plugins example ---")
    log.info("")

    all_tools = [get_therapy_styles, get_medical_services_link, notify_trusted_provider]  

    _run_scenario(
        "Scenario 1: allowed tool — get_therapy_styles",
        lambda: scenario_1_allowed_tool(all_tools),
    )
    _run_scenario(
        "Scenario 2: blocked tool — search_web not on allow list",
        lambda: scenario_2_blocked_tool(all_tools),
    )
    