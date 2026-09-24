"""Shared building blocks for the Cappy services.

Everything here is deliberately small: the domain *models* (a 1:1 port of the
frontend's ``src/domain/types.ts``), settings, an event bus with an in-memory
and a Redis implementation, an HTTP client for service-to-service calls, and
the FastAPI plumbing every service repeats (health, CORS, error shape).
"""
