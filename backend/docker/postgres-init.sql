-- One Postgres container, one database per service. A service never reads
-- another service's tables; they talk over HTTP and events.
CREATE DATABASE cappy_catalog;
CREATE DATABASE cappy_booking;
CREATE DATABASE cappy_accounts;
