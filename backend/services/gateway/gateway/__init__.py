"""API gateway: the one origin the frontend talks to.

Routes ``/api/*`` to the right service by path, forwards the caller's identity
header, and fans out the demo reset. No business logic lives here.
"""
