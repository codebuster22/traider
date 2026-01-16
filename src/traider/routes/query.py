"""Route for natural language queries."""
from fastapi import APIRouter

from traider.models import QueryRequest, QueryResponse
from traider import query_engine

router = APIRouter(prefix="/query", tags=["query"])


@router.post("", response_model=QueryResponse, status_code=200)
def execute_query(request: QueryRequest) -> QueryResponse:
    """
    Execute a natural language query against inventory data.

    Accepts questions like:
    - "What's my total stock by fabric?"
    - "Show variants with stock under 100 meters"
    - "How much did I receive this month?"

    Returns a structured response with:
    - success: Whether the query was successful
    - data: List of result rows (if successful)
    - summary: Description and row count (if successful)
    - error: Error details (if failed)
    """
    result = query_engine.query(request.question)
    return QueryResponse(**result)
