from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, model_validator

from app.db.db import db
from app.llm.ollama import llm


class ThinkInput(BaseModel):
    thought: str = ""

    model_config = {"extra": "allow"}

    @model_validator(mode="before")
    @classmethod
    def accept_any_field(cls, values):
        if isinstance(values, dict) and "thought" not in values:
            first_str = next((v for v in values.values() if isinstance(v, str)), "")
            return {"thought": first_str}
        return values


def _think(thought: str) -> str:
    return (
        f"Thought recorded: {thought}\n\n"
        "Now based on this reasoning, proceed with the correct action. "
        "If you identified an error, write a corrected query that fixes it. "
        "If you are planning, write the SQL query that matches your plan."
    )


think = StructuredTool.from_function(
    func=_think,
    name="think",
    description=(
        "Use this tool to reason and plan before writing SQL, or to reflect on "
        "errors. Pass your reasoning as the 'thought' argument. "
        "This tool does not execute anything -- it helps you think step by step."
    ),
    args_schema=ThinkInput,
)


def get_sql_toolkit() -> SQLDatabaseToolkit:
    return SQLDatabaseToolkit(db=db, llm=llm)


def get_sql_tools():
    return [think] + get_sql_toolkit().get_tools()