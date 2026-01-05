# Traider

AI-powered fabric inventory service for textile trades. Single-tenant design for internal use with MCP integration for Claude Desktop.

## Goal

- Dead-simple stock tracking for textile businesses
- AI-assisted inventory management via MCP
- REST API for external integrations

## Project Structure

```
src/traider/
├── __init__.py         # Package version
├── cli.py              # Entry points (traider-server)
├── main.py             # FastAPI app, lifespan, ASGI middleware
├── db.py               # PostgreSQL connection & DDL (schema source of truth)
├── models.py           # Pydantic request/response schemas
├── repo.py             # Data access layer (all SQL queries)
├── mcp.py              # MCP tool definitions & handlers
├── cloudinary_utils.py # Image upload to Cloudinary
└── routes/
    ├── fabrics.py      # Fabric CRUD endpoints
    ├── variants.py     # Variant CRUD endpoints
    ├── movements.py    # Stock receive/issue/adjust
    ├── stock.py        # Stock balance queries
    └── mcp.py          # MCP HTTP Streamable transport
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11+ |
| Web Framework | FastAPI |
| Database | PostgreSQL |
| DB Driver | psycopg3 (no ORM, raw SQL) |
| Validation | Pydantic v2 |
| AI Protocol | MCP (HTTP Streamable) |
| Image Storage | Cloudinary |
| Package Manager | UV |
| ASGI Server | Uvicorn |

## How to Read the Project

- **Entry point:** `cli.py` → starts uvicorn server
- **App setup:** `main.py` → FastAPI lifespan, routing, ASGI middleware
- **Database:** `db.py` → connection pool, DDL (schema source of truth)
- **Data access:** `repo.py` → all SQL queries (functional pattern)
- **API models:** `models.py` → Pydantic schemas
- **REST routes:** `routes/*.py` → endpoint handlers
- **MCP:** See `MCP_SERVER.md` for full MCP documentation

## Commands

| Task | Command |
|------|---------|
| Run server | `uv run traider` or `./run.sh` |
| Add package | `uv add <package>` |
| Add dev package | `uv add --dev <package>` |
| Run tests | `uv run pytest` |
| Install deps | `uv sync` |

## Rules

**Architecture:**
- Layered: Routes → Repo → Database
- No ORM - raw SQL with parameterized queries
- Functional repository pattern (no service classes)

**Business Logic:**
- All stock stored in meters (source of truth)
- Roll size is user-defined (NOT a fixed constant)
- Movement types: `RECEIPT`, `ISSUE`, `ADJUST`

## Development Workflows

**Adding a Change (bug fix, small update):**
1. Identify the affected file(s)
2. Make changes following existing patterns
3. Test manually or run `uv run pytest`

**Adding a New Feature:**
1. Add Pydantic models in `models.py` (request/response)
2. Add database operations in `repo.py`
3. Create route handler in `routes/`
4. Add MCP tool in `mcp.py` (if AI access needed)
5. Update DDL in `db.py` (if schema changes)

## Dos and Don'ts

**DO:**
- Use parameterized SQL queries (injection prevention)
- Define Pydantic models for new endpoints
- Add new tools to `mcp.py` for AI access
- Use `repo.py` for all database operations
- Handle `None` returns from repo (404 cases)

**DON'T:**
- Use raw string formatting in SQL
- Bypass `repo.py` for database access
- Add authentication (single-tenant internal design)
- Assume roll size (user-defined, not fixed)
- Create new DB connections (use pool from `db.py`)
