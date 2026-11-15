"""Errors that any endpoint can raise and that map to one fixed HTTP answer.

Registered once in main.py, so every route that books (or later changes) a stay
answers an overlapping-stay conflict the same way without each router having to
know about it.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.services.booking_availability import OverlappingStay


def _day(d) -> str:
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def overlapping_stay_response(request: Request, error: OverlappingStay) -> JSONResponse:
    """409 in the same loc/msg shape as the other errors, plus ctx for the "view it" link."""
    c = error.conflict
    return JSONResponse(
        status_code=409,
        content={"detail": [{
            "type": "overlapping_stay",
            "loc": ["body", "check_in"],
            "msg": (
                f"You already have a stay at {c.hotel_name} from {_day(c.check_in)} to "
                f"{_day(c.check_out)} that shares nights with these dates. "
                "Cancel or change that booking first."
            ),
            "ctx": {
                "reservation_id": c.reservation_id,
                "hotel_id": c.hotel_id,
                "hotel_name": c.hotel_name,
                "check_in": c.check_in.isoformat(),
                "check_out": c.check_out.isoformat(),
            },
        }]},
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(OverlappingStay, overlapping_stay_response)
