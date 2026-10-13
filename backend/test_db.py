from sqlalchemy import text
from app.db.database import engine

try:
    with engine.connect() as connection:
        result = connection.execute(text("SELECT DATABASE()"))
        print("Connected to MySQL successfully!")
        print("Database:", result.scalar())
except Exception as exc:
    print("MySQL connection failed:")
    print(exc)