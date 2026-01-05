import main
from fastapi import FastAPI

fastapi_app = FastAPI()

# import and run the nicegui app
main.run(fastapi_app)

if __name__ == "__main__":
    print('This is for production, run with "uvicorn main_fastapi:fastapi_app --workers 1 --port ...."')
