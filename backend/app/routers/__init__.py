"""FastAPI router package.

Runtime composition intentionally lives outside this package initializer. Importing
one router must never eagerly import the entire integration/traceability graph or
mutate sibling routers; backend.app.main composes cross-router METRC behavior only
after all router modules have initialized.
"""
