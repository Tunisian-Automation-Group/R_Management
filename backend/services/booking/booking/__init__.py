"""Booking service: the lifecycle of a request from "asked" to "rated".

Owns the bookings table and the state machine. Asks the matching service to
price and validate every request, so a client can never post its own quote.
"""
