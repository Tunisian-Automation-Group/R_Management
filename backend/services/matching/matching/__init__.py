"""Matching service: feasibility, availability, pricing, ranking and browse.

Stateless. It reads the world from the catalog service, caches it briefly, and
drops the cache when the catalog announces a change.
"""
