from app.config.settings import DB_URL
from app.db.sqltool import SQLTool


def main():
    db = SQLTool(DB_URL)

    query = "SELECT 1 AS test;"
    result = db.execute(query)

    print("DB connection OK")
    print(result)


if __name__ == "__main__":
    main()
