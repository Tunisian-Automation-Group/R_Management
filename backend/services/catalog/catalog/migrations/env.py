from cappy_common.migrations import run_env
from catalog.tables import Base

run_env(Base.metadata)
