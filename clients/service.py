

import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DB_USER = os.getenv("ZENOTI_POSTGRES_USER")
DB_PASSWORD = os.getenv("ZENOTI_POSTGRES_PASSWORD")
DB_HOST = os.getenv("ZENOTI_POSTGRES_HOST")
DB_PORT = os.getenv("ZENOTI_POSTGRES_PORT")
DB_NAME = os.getenv("ZENOTI_POSTGRES_DB")
DB_SCHEMA = os.getenv("ZENOTI_POSTGRES_SCHEMA")

DATABASE_URL = (
    f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)



def get_walkin_appointments_by_date(from_date: str, to_date: str):
    """
    Return appointment_id and mobilenumber for walkins between from_date and to_date inclusive.
    Expects from_date and to_date as strings in 'YYYY-MM-DD' format.
    """
    session = SessionLocal()
    try:
        sql = text("""
            SELECT appointment_id, mobilenumber
            FROM test.appointments_walkin
            WHERE date1 >= CAST(:from_date AS DATE)
              AND date1 <= CAST(:to_date AS DATE)
        """)
        result = session.execute(sql, {"from_date": from_date, "to_date": to_date})
        columns = result.keys()
        data = [dict(zip(columns, row)) for row in result.fetchall()]
        return data
    except Exception as exc:
        session.rollback()
        raise
    finally:
        session.close()
