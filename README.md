Test api build - built for GCP not db

to run dev server: uv run fastapi dev


main.py        = exports app
bootstrap.py   = builds FastAPI app
lifespan.py    = startup/shutdown resources
state.py       = typed app.state access
problem.py     = RFC-style error body helpers
errors.py      = global exception handlers
limiter.py     = rate-limit identity
security/      = trusted caller checks
features/meta  = root + health endpoints
features/foods = food endpoint + USDA logic


preview retest; preview boostrap first
