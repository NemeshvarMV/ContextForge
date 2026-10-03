import logfire
from langchain_groq import ChatGroq
from nemoguardrails import RailsConfig, LLMRails

from app.config import settings
from app.guardrails.colang_rules import COLANG_CONTENT, YAML_CONTENT, RAIL_INDICATORS


_rails: LLMRails | None = None
_deterministic_responses: dict[str, str] = {}


def _normalize_message(message: str) -> str:
    return message.strip().lower().rstrip("!.,?:;")


def initialize_rails() -> None:
    """
    Build the NeMo LLMRails singleton at app startup.
    Uses llama-3.1-8b-instant for fast intent classification at the gate —
    the heavier llama-3.3-70b-versatile is reserved for the RAG pipeline.
    """
    global _deterministic_responses, _rails

    guard_llm = ChatGroq(
        api_key=settings.GROQ_API_KEY,
        model="openai/gpt-oss-20b",
        temperature=0
    )

    config = RailsConfig.from_content(
        colang_content=COLANG_CONTENT,
        yaml_content=YAML_CONTENT
    )

    _deterministic_responses = {}
    for flow in config.flows:
        elements = flow.get("elements", [])
        if len(elements) < 2:
            continue

        user_intent = elements[0].get("intent_name")
        bot_message = elements[1].get("action_params", {}).get("value")
        if not user_intent or not bot_message:
            continue

        responses = config.bot_messages.get(bot_message, [])
        if not responses:
            continue

        for phrase in config.user_messages.get(user_intent, []):
            _deterministic_responses[_normalize_message(phrase)] = responses[0]

    _rails = LLMRails(config, llm=guard_llm)
    logfire.info("🛡️ NeMo Guardrails initialised (openai/gpt-oss-20b).")
    
    


def guard(message: str) -> tuple[bool, str | None]:
    """
    Run a user message through the NeMo rails gate.

    Returns:
        (True,  rail_response) — a rail fired; return this response immediately,
                                skip the RAG pipeline entirely.
        (False, None)          — message is clean; proceed to LangGraph.
    """
    deterministic_response = _deterministic_responses.get(_normalize_message(message))
    if deterministic_response is not None:
        logfire.info(f"🛡️ Colang flow fired | query='{message[:80]}'")
        return True, deterministic_response

    if _rails is None:
        logfire.warning("⚠️ Guardrails not initialised — skipping gate.")
        return False, None

    with logfire.span("🛡️ Guardrails Check"):
        result = _rails.generate(messages=[{"role": "user", "content": message}])

        # NeMo returns {'role': 'assistant', 'content': '...'} — extract text
        content = result.get("content", "") if isinstance(result, dict) else str(result)

        fired = any(indicator in content for indicator in RAIL_INDICATORS)

        if fired:
            logfire.info(f"🛡️ Guardrails fired | query='{message[:80]}'")
            return True, content

        logfire.info("✅ Guardrails passed.")
        return False, None