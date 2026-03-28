import importlib
import json
import re
from typing import Literal, TypedDict

from langgraph.graph import END, StateGraph
from app.agent.agent import agent
from app.db.db import db
from app.llm.ollama import llm
from app.prompts.sys_prompt import (
    db_router_prompt,
    db_schema_context_prompt,
    non_db_answer_prompt,
    result_summary_prompt,
)

try:
    colorama = importlib.import_module("colorama")
    Fore = colorama.Fore
    Style = colorama.Style
    init = colorama.init
except ModuleNotFoundError:
    class _AnsiFore:
        BLUE = "\033[34m"
        CYAN = "\033[36m"
        GREEN = "\033[32m"
        MAGENTA = "\033[35m"
        YELLOW = "\033[33m"

    class _AnsiStyle:
        RESET_ALL = "\033[0m"

    Fore = _AnsiFore()
    Style = _AnsiStyle()

    def init(*_args, **_kwargs):
        return None


def _extract_text_content(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(part for part in parts if part).strip()
    return str(content).strip()


def _final_ai_message_text(messages) -> str:
    for message in reversed(messages):
        if getattr(message, "type", "") == "ai":
            text = _extract_text_content(getattr(message, "content", ""))
            if text:
                return text
    return "I couldn't generate a response."


def _summarize_sql_result(sql: str, sql_result, user_query: str) -> str:
    summary = llm.invoke(
        result_summary_prompt.format(
            user_query=user_query,
            sql=sql,
            sql_result=sql_result,
        )
    )
    return _extract_text_content(getattr(summary, "content", summary))


def _resolve_tool_json_as_text(raw_text: str, user_query: str) -> str | None:
    payload = None
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        embedded = re.search(
            r'\{\s*"name"\s*:\s*"sql_(?:query|db_query)"\s*,\s*"parameters"\s*:\s*\{\s*"query"\s*:\s*".*?"\s*\}\s*\}',
            raw_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not embedded:
            return None
        try:
            payload = json.loads(embedded.group(0))
        except json.JSONDecodeError:
            return None

    if not isinstance(payload, dict):
        return None

    tool_name = payload.get("name")
    params = payload.get("parameters")
    if tool_name not in {"sql_query", "sql_db_query"}:
        return None
    if not isinstance(params, dict) or not isinstance(params.get("query"), str):
        return None

    sql = params["query"]
    try:
        sql_result = db.run(sql)
    except Exception as exc:
        return f"SQL execution failed: {exc}"
    return _summarize_sql_result(sql=sql, sql_result=sql_result, user_query=user_query)


def _is_likely_sql(sql: str) -> bool:
    lowered = f" {sql.lower()} "
    stripped = lowered.strip()

    if stripped.startswith("select"):
        return " from " in lowered
    if stripped.startswith("insert"):
        return " into " in lowered and " values " in lowered
    if stripped.startswith("update"):
        return " set " in lowered
    if stripped.startswith("delete"):
        return " from " in lowered
    if stripped.startswith("show") or stripped.startswith("explain"):
        return True
    if stripped.startswith("with"):
        return " as " in lowered and any(
            token in lowered for token in (" select ", " insert ", " update ", " delete ")
        )
    return False


def _extract_sql_from_text(raw_text: str) -> str | None:
    text = raw_text.strip()
    if not text:
        return None

    fenced = re.search(r"```sql\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        sql_candidate = fenced.group(1).strip().rstrip(";").strip()
        if sql_candidate and _is_likely_sql(sql_candidate):
            return f"{sql_candidate};"

    sql_like = re.search(
        r"^\s*(select|insert|update|delete|with|show|explain)\b[\s\S]*?(?:;|$)",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if not sql_like:
        return None

    sql_candidate = sql_like.group(0).strip().rstrip(";").strip()
    if not sql_candidate:
        return None

    if _is_likely_sql(sql_candidate):
        return f"{sql_candidate};"
    return None


def _resolve_sql_text_as_answer(raw_text: str, user_query: str) -> str | None:
    sql = _extract_sql_from_text(raw_text)
    if not sql:
        return None

    try:
        sql_result = db.run(sql)
    except Exception as exc:
        return f"SQL execution failed: {exc}"
    return _summarize_sql_result(sql=sql, sql_result=sql_result, user_query=user_query)


def _should_query_db(user_query: str) -> bool:
    decision = llm.invoke(db_router_prompt.format(user_query=user_query))
    decision_text = _extract_text_content(getattr(decision, "content", decision)).upper()
    return decision_text.startswith("YES")


def _answer_without_db(user_query: str) -> str:
    response = llm.invoke(non_db_answer_prompt.format(user_query=user_query))
    return _extract_text_content(getattr(response, "content", response))


def _get_db_schema_context() -> str:
    try:
        table_names = list(db.get_usable_table_names())
        if not table_names:
            return "No tables found in the database."
        schema = db.get_table_info(table_names=table_names)
        _log_step("SCHEMA", Fore.BLUE, f"Loaded schema for {len(table_names)} table(s)")
        return schema
    except Exception as exc:
        _log_step("SCHEMA", Fore.YELLOW, f"Failed to load schema context: {exc}")
        return ""


class AgentState(TypedDict, total=False):
    query: str
    route: Literal["direct", "db"]
    final_answer: str


def _log_step(label: str, color: str, message: str) -> None:
    print(f"{color}[{label}]{Style.RESET_ALL} {message}")


def _preview(text: str, limit: int = 220) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit]}..."


def _stream_logs(messages, seen_count: int) -> int:
    for message in messages[seen_count:]:
        message_type = getattr(message, "type", "")

        if message_type == "ai":
            text = _extract_text_content(getattr(message, "content", ""))
            if text:
                _log_step("THINK", Fore.CYAN, text)

            for tool_call in (getattr(message, "tool_calls", None) or []):
                tool_name = tool_call.get("name", "unknown_tool")
                tool_args = tool_call.get("args", {})
                _log_step(
                    "TOOL CALL",
                    Fore.MAGENTA,
                    f"{tool_name} | args={json.dumps(tool_args, default=str)}",
                )

        elif message_type == "tool":
            tool_name = getattr(message, "name", "tool")
            content = _extract_text_content(getattr(message, "content", ""))
            _log_step("TOOL RESULT", Fore.YELLOW, f"{tool_name} -> {_preview(content)}")

    return len(messages)


def _route_question_node(state: AgentState) -> AgentState:
    query = state["query"]
    if _should_query_db(query):
        _log_step("ROUTER", Fore.BLUE, "Database lookup needed")
        return {"route": "db"}
    _log_step("ROUTER", Fore.BLUE, "No database lookup needed")
    return {"route": "direct"}


def _direct_answer_node(state: AgentState) -> AgentState:
    return {"final_answer": _answer_without_db(state["query"])}


def _db_answer_node(state: AgentState) -> AgentState:
    query = state["query"]
    _log_step("RUN", Fore.BLUE, "Starting SQL agent")
    schema_context = _get_db_schema_context()
    _log_step("SCHEMA CONTEXT", Fore.CYAN, f"\n{schema_context}")
    last_seen_message_count = 0
    final_messages = []

    db_context_message = db_schema_context_prompt.format(schema_context=schema_context)

    for step in agent.stream(
        {
            "messages": [
                {"role": "system", "content": db_context_message},
                {"role": "user", "content": query},
            ]
        },
        stream_mode="values",
        config={"recursion_limit": 30},
    ):
        messages = step.get("messages", [])
        last_seen_message_count = _stream_logs(messages, last_seen_message_count)
        final_messages = messages

    answer = _final_ai_message_text(final_messages)
    resolved_answer = _resolve_tool_json_as_text(answer, query)
    if resolved_answer:
        _log_step("FALLBACK", Fore.YELLOW, "Converted tool-style JSON into plain answer")
    else:
        resolved_answer = _resolve_sql_text_as_answer(answer, query)
        if resolved_answer:
            _log_step("FALLBACK", Fore.YELLOW, "Executed plain SQL text and summarized the result")
    return {"final_answer": resolved_answer or answer}


def _route_condition(state: AgentState) -> Literal["direct_answer", "db_answer"]:
    return "db_answer" if state.get("route") == "db" else "direct_answer"


def _build_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("route_question", _route_question_node)
    workflow.add_node("direct_answer", _direct_answer_node)
    workflow.add_node("db_answer", _db_answer_node)

    workflow.set_entry_point("route_question")
    workflow.add_conditional_edges(
        "route_question",
        _route_condition,
        {
            "direct_answer": "direct_answer",
            "db_answer": "db_answer",
        },
    )
    workflow.add_edge("direct_answer", END)
    workflow.add_edge("db_answer", END)
    return workflow.compile()


graph = _build_graph()


def run_cli() -> None:
    init(autoreset=True, strip=False)
    while True:
        query = input("User Query: ")
        if query.lower() in ["exit", "quit", "bye"]:
            break

        result = graph.invoke({"query": query})
        print(f"{Fore.GREEN}Assistant:{Style.RESET_ALL} {result.get('final_answer', '')}")
