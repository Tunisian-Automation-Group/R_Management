from booking.tables import Base
from cappy_common.migrations import run_env

run_env(Base.metadata)
