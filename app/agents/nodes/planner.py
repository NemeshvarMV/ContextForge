from app.agents.state import AgentState
from app.gateway.client import get_langchain_llm
import logfire

llm = get_langchain_llm(feature="planner")

def planner_node(state: AgentState):
    """
    The Planner determines if a search is needed based on the ENTIRE conversation.
    """
    history = ""
    for msg in state["messages"][:-1]:
        role = "User" if msg["role"] == "user" else "Assistant"
        history += f"{role}: {msg['content']}\n"

    user_message = state["messages"][-1]["content"] if state["messages"] else ""

    prompt = f"""
    You are an intelligent Assistant Planner for an Enterprise IT Assistant.
    Analyze the conversation history and the latest user message.

    CONVERSATION HISTORY:
    {history}

    LATEST MESSAGE:
    "{user_message}"

    Classify the user's intent into one of three categories:
    1. CONVERSATIONAL: The message is a greeting (hi, hello, hey), polite farewell, or a conversational query that refers strictly to the conversation history above (e.g. "what was the second step you just mentioned?").
    2. OFF_TOPIC: The message is about non-enterprise IT topics (cooking, recipes, coffee, food, sports, movies, celebrity gossip, creative writing, personal advice, or general trivia unrelated to enterprise IT).
    3. TECHNICAL: The message is a technical question about Cloud Infrastructure, Site Reliability Engineering, Incident Management, DevOps, CI/CD, Cybersecurity, or Enterprise IT Operations. Output a refined technical search query for documentation retrieval.

    Output format:
    - If CONVERSATIONAL, output ONLY 'CONVERSATIONAL'
    - If OFF_TOPIC, output ONLY 'OFF_TOPIC'
    - If TECHNICAL, output ONLY the refined search query (do not prefix with 'TECHNICAL:')
    """

    with logfire.span("🧠 Planner Decision"):
        decision = llm.invoke(prompt).content.strip()
        logfire.info(f"Intent identified: {decision}")

    if decision.upper() == "OFF_TOPIC" or decision.upper().startswith("OFF_TOPIC"):
        return {
            "current_query": "OFF_TOPIC",
            "status": "Off-topic query intercepted by planner.",
            "plan": ["Intent: Off-Topic Refused", "Retrieval: Skipped"]
        }

    if decision.upper() == "CONVERSATIONAL" or decision.upper().startswith("CONVERSATIONAL"):
        return {
            "current_query": "CONVERSATIONAL",
            "status": "Handling conversationally (using memory)...",
            "plan": ["Intent: Conversational/Memory", "Retrieval: Skipped"]
        }

    return {
        "current_query": decision,
        "status": f"Technical research needed. Searching for: {decision}",
        "plan": ["Intent: Technical", f"Search Term: {decision}"]
    }