import os
import sys
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool, MetaData
from alembic import context

# Add project root to Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# ✅ Import both Base classes
from models.models import Base as CoreBase
from service_booking.model import Base as ServiceBookingBase

# ✅ Merge metadata by collecting all tables
target_metadata = MetaData()
for table in CoreBase.metadata.tables.values():
    table.tometadata(target_metadata)

for table in ServiceBookingBase.metadata.tables.values():
    table.tometadata(target_metadata)

# ✅ Alembic Config object
config = context.config

# ✅ Logging
if config.config_file_name:
    fileConfig(config.config_file_name)

# ✅ Load environment variables
load_dotenv()

# ✅ Build DB URL from .env
user = os.getenv("POSTGRES_USER")
password = os.getenv("POSTGRES_PASSWORD")
host = os.getenv("POSTGRES_HOST")
port = os.getenv("POSTGRES_PORT")
db = os.getenv("POSTGRES_DB")

DATABASE_URL = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"

# ✅ Set the DB URL in alembic config
config.set_main_option("sqlalchemy.url", DATABASE_URL)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True  # Optional: to detect type changes
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
