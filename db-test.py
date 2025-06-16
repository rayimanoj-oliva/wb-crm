import psycopg2

db_user = 'olivauat'
db_password = 'vBnRepqTrRR5vz09ZaRL'
db_host = 'oliva-uat-db.cvsa8g2eyjnd.ap-south-1.rds.amazonaws.com'
db_port = '5432'
db_name = 'postgres'

try:
    conn = psycopg2.connect(
        dbname=db_name,
        user=db_user,
        password=db_password,
        host=db_host,
        port=db_port
    )
    cur = conn.cursor()
    cur.execute("SELECT * FROM alembic_version;")
    rows = cur.fetchall()
    for row in rows:
        print(row)

    cur.close()
    conn.close()

except Exception as e:
    print("Error:", e)
