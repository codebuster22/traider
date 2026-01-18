"""Natural language to SQL query engine using Gemini 2.0 Flash."""
import logging
import os
import re
from decimal import Decimal
from typing import Any

from google import genai

from traider.db import get_conn

logger = logging.getLogger(__name__)

# Configuration
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.0-flash"
QUERY_TIMEOUT_SECONDS = 5
MAX_RESULTS = 1000

# Allowed tables (whitelist)
ALLOWED_TABLES = {"fabrics", "fabric_aliases", "fabric_variants", "stock_movements", "stock_balances"}

# Forbidden keywords (SQL injection prevention)
FORBIDDEN_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER",
    "CREATE", "GRANT", "REVOKE", "EXECUTE", "EXEC", "COPY",
    "LOAD", "VACUUM", "REINDEX", "CLUSTER", "ANALYZE", "EXPLAIN"
}

# Database schema for LLM context
SCHEMA_CONTEXT = """
TABLES:
- fabrics: id, fabric_code (unique), name, image_url, gallery
- fabric_aliases: fabric_id (FK→fabrics), alias (alternate names)
- fabric_variants: id, fabric_id (FK→fabrics), color_code, finish, gsm, width, image_url, gallery
  - UNIQUE constraint on (fabric_id, color_code)
- stock_balances: variant_id (FK→fabric_variants), on_hand_m, on_hand_rolls, updated_at
- stock_movements: id, ts, variant_id (FK→fabric_variants), movement_type ('RECEIPT'/'ISSUE'/'ADJUST'),
  delta_qty_m, original_qty, original_uom ('m'/'roll'), reason, created_at, roll_count, document_id,
  is_cancelled (bool), cancelled_at

RELATIONSHIPS:
- fabric_variants belongs to fabrics (via fabric_id)
- stock_balances belongs to fabric_variants (via variant_id)
- stock_movements belongs to fabric_variants (via variant_id)
- fabric_aliases belongs to fabrics (via fabric_id)

IMPORTANT NOTES:
- Stock is stored per variant, not per fabric
- To get stock by fabric, JOIN fabric_variants → fabrics and GROUP BY
- movement_type values are uppercase: 'RECEIPT', 'ISSUE', 'ADJUST'
- on_hand_m is always in meters (source of truth)
- Use is_cancelled = FALSE to exclude cancelled movements
"""

LLM_PROMPT_TEMPLATE = """You are a SQL query generator for a fabric inventory system. Generate a PostgreSQL SELECT query based on the user's question.

{schema}

Rules:
1. Generate ONLY SELECT queries - never INSERT, UPDATE, DELETE, etc.
2. Use clear column aliases that describe the data (e.g., total_stock_m, fabric_name)
3. ALWAYS include these identifiers in results (both IDs and codes are mandatory):
   - For fabric queries: MUST include fabric_id and fabric_code
   - For variant queries: MUST include variant_id, fabric_id, fabric_code, and color_code
4. For aggregations, include COUNT or SUM as appropriate
5. Default to ordering by the most relevant column
6. If the question cannot be answered with the available data, respond with ERROR: <reason>
7. DATE FILTERING: When filtering by date ranges on timestamp columns (ts, created_at):
   - For "from X to Y" where X and Y are different dates: use ts >= 'X' AND ts < 'Y+1day'
   - For "from X to X" (same date) or "on date X": use ts >= 'X' AND ts < 'X+1day' to include the ENTIRE day
   - NEVER use ts < 'X' when X is the start date - this returns nothing
   - Example: "from 2026-01-17 to 2026-01-17" means the entire day, so use: ts >= '2026-01-17' AND ts < '2026-01-18'

User Question: {question}

Respond with ONLY:
1. The SQL query (no markdown, no explanation)
2. A pipe separator |
3. A brief description of what the query returns

EXAMPLES:

Question: "What's my total stock by fabric?"
Response: SELECT f.id as fabric_id, f.fabric_code, f.name, SUM(sb.on_hand_m) as total_stock_m FROM fabrics f JOIN fabric_variants fv ON f.id = fv.fabric_id LEFT JOIN stock_balances sb ON fv.id = sb.variant_id GROUP BY f.id, f.fabric_code, f.name ORDER BY total_stock_m DESC|Total stock in meters grouped by fabric, sorted highest first

Question: "Show all variants with stock under 50 meters"
Response: SELECT fv.id as variant_id, f.id as fabric_id, f.fabric_code, fv.color_code, sb.on_hand_m FROM fabric_variants fv JOIN fabrics f ON f.id = fv.fabric_id LEFT JOIN stock_balances sb ON fv.id = sb.variant_id WHERE sb.on_hand_m < 50 ORDER BY sb.on_hand_m ASC|Variants with stock below 50 meters, sorted lowest first

Question: "How many rolls do I have for each variant?"
Response: SELECT fv.id as variant_id, f.id as fabric_id, f.fabric_code, fv.color_code, sb.on_hand_m, sb.on_hand_rolls FROM fabric_variants fv JOIN fabrics f ON f.id = fv.fabric_id LEFT JOIN stock_balances sb ON fv.id = sb.variant_id ORDER BY f.fabric_code, fv.color_code|Stock balance with roll count for each variant

Question: "Show all receipts from the last 7 days"
Response: SELECT sm.id as movement_id, fv.id as variant_id, f.id as fabric_id, f.fabric_code, fv.color_code, sm.delta_qty_m, sm.roll_count, sm.document_id, sm.ts FROM stock_movements sm JOIN fabric_variants fv ON fv.id = sm.variant_id JOIN fabrics f ON f.id = fv.fabric_id WHERE sm.movement_type = 'RECEIPT' AND sm.is_cancelled = FALSE AND sm.ts >= NOW() - INTERVAL '7 days' ORDER BY sm.ts DESC|Stock receipts from the last 7 days

Question: "List all stock movements from 2026-01-17 to 2026-01-17"
Response: SELECT sm.id as movement_id, fv.id as variant_id, f.id as fabric_id, f.fabric_code, fv.color_code, sm.movement_type, sm.delta_qty_m, sm.roll_count, sm.document_id, sm.ts FROM stock_movements sm JOIN fabric_variants fv ON fv.id = sm.variant_id JOIN fabrics f ON f.id = fv.fabric_id WHERE sm.is_cancelled = FALSE AND sm.ts >= '2026-01-17' AND sm.ts < '2026-01-18' ORDER BY sm.ts DESC|Stock movements for January 17, 2026

Question: "Which fabrics have no stock?"
Response: SELECT f.id as fabric_id, f.fabric_code, f.name FROM fabrics f WHERE NOT EXISTS (SELECT 1 FROM fabric_variants fv JOIN stock_balances sb ON fv.id = sb.variant_id WHERE fv.fabric_id = f.id AND sb.on_hand_m > 0) ORDER BY f.fabric_code|Fabrics with zero stock across all variants"""


# ============================================================================
# Custom Exceptions
# ============================================================================

class InvalidQueryError(Exception):
    """Raised when the question cannot be interpreted as a valid inventory query."""
    pass


class UnsafeQueryError(Exception):
    """Raised when the generated SQL contains forbidden operations."""
    pass


class QueryExecutionError(Exception):
    """Raised when the SQL query fails to execute."""
    pass


class QueryTimeoutError(Exception):
    """Raised when the query exceeds the timeout limit."""
    pass


# ============================================================================
# Helper Functions
# ============================================================================

def _serialize_value(value: Any) -> Any:
    """Convert database values to JSON-serializable format."""
    if isinstance(value, Decimal):
        return float(value)
    elif hasattr(value, 'isoformat'):  # datetime objects
        return value.isoformat()
    return value


def _serialize_row(row: dict) -> dict:
    """Convert a database row to JSON-serializable format."""
    return {k: _serialize_value(v) for k, v in row.items()}


# ============================================================================
# Core Functions
# ============================================================================

def generate_sql(question: str) -> tuple[str, str]:
    """
    Generate SQL from a natural language question using Gemini.

    Args:
        question: Natural language question about inventory

    Returns:
        Tuple of (sql_query, description)

    Raises:
        InvalidQueryError: If the question cannot be interpreted
    """
    if not GEMINI_API_KEY:
        raise InvalidQueryError("GEMINI_API_KEY not configured")

    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = LLM_PROMPT_TEMPLATE.format(
        schema=SCHEMA_CONTEXT,
        question=question
    )

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )

        result_text = response.text.strip()

        # Check for error response
        if result_text.upper().startswith("ERROR:"):
            error_msg = result_text[6:].strip()
            raise InvalidQueryError(error_msg)

        # Parse response: SQL|description
        if "|" not in result_text:
            raise InvalidQueryError("LLM response missing description separator")

        parts = result_text.split("|", 1)
        sql = parts[0].strip()
        description = parts[1].strip() if len(parts) > 1 else "Query results"

        # Remove markdown code block if present
        if sql.startswith("```"):
            sql = re.sub(r'^```(?:sql)?\s*', '', sql)
            sql = re.sub(r'\s*```$', '', sql)

        return sql, description

    except genai.errors.APIError as e:
        logger.error(f"Gemini API error: {e}")
        raise InvalidQueryError(f"LLM service error: {str(e)}")


def validate_sql(sql: str) -> str:
    """
    Validate and sanitize the generated SQL.

    Args:
        sql: The SQL query to validate

    Returns:
        The validated (and possibly modified) SQL query

    Raises:
        UnsafeQueryError: If the SQL contains forbidden operations
    """
    # Normalize for checking
    sql_upper = sql.upper()

    # Must start with SELECT
    if not sql_upper.strip().startswith("SELECT"):
        raise UnsafeQueryError("Only SELECT queries are allowed")

    # Check for forbidden keywords
    for keyword in FORBIDDEN_KEYWORDS:
        # Use word boundary check to avoid false positives
        pattern = r'\b' + keyword + r'\b'
        if re.search(pattern, sql_upper):
            raise UnsafeQueryError(f"Forbidden keyword detected: {keyword}")

    # Check for semicolon (potential query chaining)
    if ";" in sql:
        # Only allow semicolon at the very end
        if sql.strip().rstrip(";").count(";") > 0:
            raise UnsafeQueryError("Multiple statements not allowed")
        sql = sql.strip().rstrip(";")

    # Extract table references and validate against whitelist
    # Simple regex to find table names after FROM and JOIN keywords
    table_pattern = r'\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)'
    tables_found = re.findall(table_pattern, sql_upper)

    for table in tables_found:
        if table.lower() not in ALLOWED_TABLES:
            raise UnsafeQueryError(f"Access to table '{table}' is not allowed")

    # Add LIMIT if not present
    if "LIMIT" not in sql_upper:
        sql = sql.rstrip() + f" LIMIT {MAX_RESULTS}"

    return sql


def execute_query(sql: str) -> list[dict]:
    """
    Execute the validated SQL query with timeout protection.

    Args:
        sql: The validated SQL query

    Returns:
        List of result rows as dictionaries

    Raises:
        QueryTimeoutError: If the query exceeds the timeout
        QueryExecutionError: If the query fails to execute
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            try:
                # Set statement timeout (LOCAL so it's transaction-scoped)
                cur.execute(f"SET LOCAL statement_timeout = '{QUERY_TIMEOUT_SECONDS * 1000}'")

                # Execute the query
                cur.execute(sql)

                # Fetch results
                rows = cur.fetchall()

                # Serialize results
                result = [_serialize_row(row) for row in rows]

                # Rollback to cleanly close the read-only transaction
                conn.rollback()

                return result

            except Exception as e:
                error_msg = str(e).lower()
                if "canceling statement due to statement timeout" in error_msg:
                    raise QueryTimeoutError("Query exceeded time limit")
                raise QueryExecutionError(f"Query execution failed: {str(e)}")


def query(question: str) -> dict:
    """
    Main entry point: process a natural language question and return structured results.

    Args:
        question: Natural language question about inventory

    Returns:
        Dictionary with structure:
        {
            "success": bool,
            "data": [...] or None,
            "summary": {"description": str, "row_count": int} or None,
            "error": {"code": str, "message": str} or None
        }
    """
    try:
        # Step 1: Generate SQL from question
        sql, description = generate_sql(question)
        logger.info(f"Generated SQL: {sql}")

        # Step 2: Validate SQL
        validated_sql = validate_sql(sql)
        logger.info(f"Validated SQL: {validated_sql}")

        # Step 3: Execute query
        results = execute_query(validated_sql)

        # Check for empty results
        if not results:
            return {
                "success": False,
                "data": None,
                "summary": None,
                "error": {
                    "code": "NO_RESULTS",
                    "message": "Query returned no results"
                }
            }

        # Success response
        return {
            "success": True,
            "data": results,
            "summary": {
                "description": description,
                "row_count": len(results)
            },
            "error": None
        }

    except InvalidQueryError as e:
        logger.warning(f"Invalid query: {e}")
        return {
            "success": False,
            "data": None,
            "summary": None,
            "error": {
                "code": "INVALID_QUERY",
                "message": str(e)
            }
        }

    except UnsafeQueryError as e:
        logger.warning(f"Unsafe query: {e}")
        return {
            "success": False,
            "data": None,
            "summary": None,
            "error": {
                "code": "UNSAFE_QUERY",
                "message": str(e)
            }
        }

    except QueryTimeoutError as e:
        logger.warning(f"Query timeout: {e}")
        return {
            "success": False,
            "data": None,
            "summary": None,
            "error": {
                "code": "TIMEOUT",
                "message": str(e)
            }
        }

    except Exception as e:
        logger.error(f"Internal error in query engine: {e}")
        return {
            "success": False,
            "data": None,
            "summary": None,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred"
            }
        }
