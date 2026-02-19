from typing import List, Dict, Any
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

class SQLTool:
    def __init__(self, db_url: str):
        self.engine: Engine = create_engine(db_url)
    
    def execute(self, query: str) -> List[Dict[str, Any]]:
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                rows = result.fetchall()
                cols = result.keys()
                return [dict(zip(cols, row)) for row in rows]
        except SQLAlchemyError as e:
            raise RuntimeError(f"Database error: {str(e)}")