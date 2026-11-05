from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.exceptions import RequestValidationError
from pydantic import Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.search import HotelSearchParams
from app.services.availability import SortOption, find_available_hotels
from app.services.distance import resolve_origin

router = APIRouter(prefix="/search", tags=["search"])


class SearchQuery(HotelSearchParams):
    """HotelSearchParams (8.4.1) plus pagination for the results list (1.1.3).

    FastAPI can't mix a query-parameter model with separate query params, so
    the paging fields live on a subclass instead of editing the shared schema.
    """

    sort: SortOption = "recommended"  # 1.5.1: recommended | price_asc | price_desc | rating | distance
    limit: int = Field(default=20, ge=1, le=50)
    offset: int = Field(default=0, ge=0)


@router.get("")
def search_hotels(
    params: Annotated[SearchQuery, Query()],
    db: Session = Depends(get_db),
):
    """Hotels with a free room for the destination, dates and guest count.

    Date and guest validation lives in HotelSearchParams and returns 422.
    An empty `results` list is a normal answer; the UI shows the 1.1.4
    empty state.
    """
    origin = None
    if params.sort == "distance":
        origin = resolve_origin(params.destination, params.lat, params.lng)
        if origin is None:
            raise RequestValidationError([{
                "type": "value_error",
                "loc": ("query", "sort"),
                "msg": "Distance sort needs a known city, or lat and lng.",
                "input": params.sort,
            }])
    results = find_available_hotels(
        db,
        destination=params.destination,
        check_in=params.check_in,
        check_out=params.check_out,
        guests=params.guests,
        sort=params.sort,
        limit=params.limit,
        offset=params.offset,
        min_price=params.min_price,
        max_price=params.max_price,
        min_stars=params.min_stars,
        room_type=params.room_type,
        origin=origin,
    )
    return {"results": results, "sort": params.sort, "limit": params.limit, "offset": params.offset,}
