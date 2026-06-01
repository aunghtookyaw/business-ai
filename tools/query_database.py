import psycopg2
import config


def query_database(sql_query):

    try:

        connection = psycopg2.connect(
            host=config.POSTGRES_HOST,
            database=config.POSTGRES_DB,
            user=config.POSTGRES_USER,
            password=config.POSTGRES_PASSWORD,
            port=config.POSTGRES_PORT
        )

        cursor = connection.cursor()

        cursor.execute(sql_query)

        rows = cursor.fetchall()

        column_names = [
            desc[0]
            for desc in cursor.description
        ]

        result = []

        for row in rows:

            row_data = {}

            for i in range(len(column_names)):
                row_data[column_names[i]] = str(row[i])

            result.append(row_data)

        cursor.close()
        connection.close()

        return result

    except Exception as e:

        return f"Database Error: {str(e)}"
