from fastapi import FastAPI

import main
from routes.api import api_router
# from ng_loba.store.orm import init_db
# from services.storage.storage import initialize_multitenancy

fastapi_app = FastAPI(
    title="eduPersona API",
    version="1.0.0",
    description="Self-service system for matching/verifying eduID users with institutional accounts",
)
fastapi_app.include_router(api_router)

# Initialize multi-tenancy system
# initialize_multitenancy()

# import and run the nicegui app
main.run(fastapi_app)

if __name__ == "__main__":
    print('This is for production, run with "uvicorn main_fastapi:fastapi_app --workers 1 --port ...."')
