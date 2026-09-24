"""Pure domain logic. No I/O, no clock: ``now`` is always an argument.

A 1:1 port of the frontend's ``src/domain/`` so the server and the app agree
on every cent, every offer and every rank. If you change a rule here, change
it there too; ``tests/test_domain.py`` is the port of the app's own
``npm run check`` and will tell you when the two drift.
"""
