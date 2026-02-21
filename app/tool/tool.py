from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from app.db.db import db
from app.llm.ollama import llm


def get_sql_toolkit() -> SQLDatabaseToolkit:
    return SQLDatabaseToolkit(db=db, llm=llm)


def get_sql_tools():
    return get_sql_toolkit().get_tools()