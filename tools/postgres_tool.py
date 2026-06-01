import psycopg2

from config import (
    POSTGRES_HOST,
    POSTGRES_DB,
    POSTGRES_USER,
    POSTGRES_PASSWORD,
    POSTGRES_PORT
)

def query_database(sql_query):

    try:

        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            port=POSTGRES_PORT
        )

        cur = conn.cursor()

        cur.execute(sql_query)

        rows = cur.fetchall()

        cur.close()

        conn.close()

        return str(rows)

    except Exception as e:

        return f"SQL Error: {str(e)}"
