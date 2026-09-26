-- One database per service, as in AWS: no service reads another's tables.
CREATE DATABASE catalog;
CREATE DATABASE booking;
CREATE DATABASE payments;
CREATE DATABASE notifications;
