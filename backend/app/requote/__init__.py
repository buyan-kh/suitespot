"""2.3.2 Price re-quote on change (US2.3).

quote_change() works out what changing a reservation's dates, room or guest
count would cost, without changing anything. The modify form (2.3.3) shows it
through POST /reservations/{id}/quote-change; the modify endpoint (2.3.1) calls
it again right before applying the change, then charges balance_due or refunds
refund_due.
"""
