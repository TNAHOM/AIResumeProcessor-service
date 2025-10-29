from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context
from app.db.models import Application
from app.core.config import settings  # Load DB_URL from .env

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Ensure sqlalchemy.url comes from our application settings (.env)
# This keeps migrations consistent with the running app configuration.
if settings and getattr(settings, "DB_URL", None):
    config.set_main_option("sqlalchemy.url", settings.DB_URL)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata

target_metadata = [Application.metadata]

# Only manage our own tables; skip external ones owned by other services
EXCLUDED_TABLES = {"users", "job_posts"}


def include_object(obj, name, type_, reflected, compare_to):
    # Skip excluded tables entirely
    if type_ == "table" and name in EXCLUDED_TABLES:
        return False

    # Skip indexes that belong to excluded tables
    if type_ == "index":
        table = getattr(obj, "table", None)
        tbl_name = getattr(table, "name", None)
        if tbl_name in EXCLUDED_TABLES:
            return False
    return True


# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
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
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
