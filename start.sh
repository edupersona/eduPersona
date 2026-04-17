#!/usr/bin/env bash
# starts FastAPI app (in main_fastapi.fastapi_app) from uvicorn
#
# use path of this example as working directory; enables starting this script from anywhere
# NB: behind the nginx proxy, port 8080 is also used, so you can stop the server and run ./start.sh dev instead
# clear
cd "$(dirname "$0")"

if [ "$1" = "prod" ]; then
    echo "Starting Uvicorn server in production mode..."
    # we also use a single worker in production mode so socket.io connections are always handled by the same worker
    uvicorn main_fastapi:fastapi_app --workers 1 --port 8090
elif [ "$1" = "dev" ]; then
    echo "Starting Uvicorn server in development mode... point your browser at http://localhost:8080/"
    # reload implies workers = 1
    uvicorn main_fastapi:fastapi_app --reload --reload-include "static/scss/*.scss" --log-level critical --port 8080
elif [ "$1" = "test" ]; then
    echo "Running pytest"
    pytest -c pyproject.toml -s test
else
    echo "Invalid parameter. Use 'prod' or 'dev'."
    exit 1
fi
