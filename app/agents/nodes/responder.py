import logfire
from app.agents.state import AgentState
from app.gateway.client import portkey_client, extract_cache_status


def generate_node(state: AgentState):
    """
    Synthesizes a response using both Documentation Context AND Conversation History.
    Uses the native Portkey client (not LangChain) so we can read the
    x-portkey-cache-status response header and surface Cache: Hit in the UI.
    """
    query = state["current_query"]

    history_str = ""
    for msg in state["messages"][:-1]:
        role = "User" if msg["role"] == "user" else "Assistant"
        history_str += f"{role}: {msg['content']}\n"

    user_msg = state["messages"][-1]["content"] if state["messages"] else ""

    OFF_TOPIC_REFUSAL = (
        "I am an Enterprise IT Assistant for ContextForge. I can only assist with technical topics covered by "
        "our enterprise IT documentation (Cloud Infrastructure, DevOps & CI/CD, SRE & Incident Management, "
        "and Cybersecurity). I cannot help with off-topic or general lifestyle requests."
    )

    if query == "OFF_TOPIC":
        logfire.info("Responding with standard off-topic refusal.")
        return {
            "final_answer": OFF_TOPIC_REFUSAL,
            "status": "Blocked by enterprise guardrails.",
            "plan": state["plan"],
            "messages": [{"role": "assistant", "content": OFF_TOPIC_REFUSAL}]
        }

    if query == "CONVERSATIONAL":
        logfire.info("Generating conversational response using memory.")
        prompt = f"""
        You are an Enterprise IT Assistant for ContextForge.
        Your role is to handle polite conversation (greetings, acknowledgments) or questions referencing prior conversation history.

        STRICT BOUNDARIES:
        - If the user is asking about cooking, recipes, coffee, sports, movies, or general non-IT topics, respond ONLY with:
          "{OFF_TOPIC_REFUSAL}"
        - Otherwise, answer the user politely using the CONVERSATION HISTORY below.

        CONVERSATION HISTORY:
        {history_str}

        LATEST MESSAGE:
        "{user_msg}"
        """
    else:
        logfire.info("Generating technical RAG response.")
        max_context_chars = 25000
        full_context = ""

        for doc in state["documents"]:
            if len(full_context) + len(doc) < max_context_chars:
                full_context += doc + "\n\n"
            else:
                logfire.warning("Context truncated to fit Groq TPM limits.")
                break

        prompt = f"""
        You are a Senior Technical Architect and Enterprise IT Assistant for ContextForge.
        Answer the question using the TECHNICAL CONTEXT provided.

        GROUNDING & BOUNDARY RULES:
        1. Base your answer strictly on the facts present in the TECHNICAL CONTEXT.
        2. If the TECHNICAL CONTEXT does not contain relevant information to answer the question, state clearly:
           "I do not have documentation on that topic in my knowledge base. I can only answer questions covered by our verified enterprise IT documentation (GitLab, Microsoft, Google Cloud/SRE, and Atlassian)."
        3. Never invent, extrapolate, or hallucinate technical procedures or policies not supported by the context.
        4. Cite the company or source documentation when providing procedures.

        TECHNICAL CONTEXT:
        {full_context}

        CONVERSATION HISTORY:
        {history_str}

        USER QUESTION:
        "{user_msg}"
        """

    with logfire.span("✍️ LLM Synthesis"):
        try:
            response = portkey_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            content = response.choices[0].message.content
            cache_status = extract_cache_status(response)
            is_cache_hit = cache_status == "HIT"

            if is_cache_hit:
                logfire.info("⚡ Gateway Cache Hit — response served from Portkey cache.")
                plan_update = state["plan"] + ["Cache: Hit ⚡"]
                status = "Cache hit — instant response."
            else:
                logfire.info("✅ Response synthesised via LLM.")
                plan_update = state["plan"]
                status = "Response generated."

            return {
                "final_answer": content,
                "status": status,
                "plan": plan_update,
                "messages": [{"role": "assistant", "content": content}]
            }

        except Exception as e:
            logfire.error(f"LLM Generation failed: {e}")
            raise e