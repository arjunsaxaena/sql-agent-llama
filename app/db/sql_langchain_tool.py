from langchain_core.tools import Tool
from app.db.sqltool import SQLTool
from app.config.settings import DB_URL

_sql_tool = SQLTool(DB_URL)

def run_sql(query: str) -> str:
    results = _sql_tool.execute(query)
    return str(results)

sql_tool = Tool(
    name="run_sql",
    description="Execute a SQL query and return the results",
    func=run_sql,
)