from langchain_community.utilities import SQLDatabase
from app.config.settings import DB_URL

db = SQLDatabase.from_uri(DB_URL, sample_rows_in_table_info=0)