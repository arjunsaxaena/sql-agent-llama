from langchain.agents import create_agent

from app.llm.ollama import llm
from app.prompts.sys_prompt import system_prompt
from app.tool.tool import get_sql_tools


def build_sql_agent():
    return create_agent(
        llm,
        get_sql_tools(),
        system_prompt=system_prompt,
    )


agent = build_sql_agent()