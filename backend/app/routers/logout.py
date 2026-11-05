"""POST /auth/logout: end the guest's session (US5.4, task 5.4.1)"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


class LogoutResponse(BaseModel):
    detail: str


@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="Log out",
    description=(
        "Call this when the user clicks Log out, then delete the access and "
        "refresh tokens on the client. Always returns 200, even if the token "
        "is missing or expired."
    ),
)
def logout() -> LogoutResponse:
    return LogoutResponse(detail="Logged out.")
