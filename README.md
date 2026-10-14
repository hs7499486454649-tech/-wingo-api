\
# Wingo Pattern API — Render restart package

This API stores manually entered BIG/SMALL results and summarizes historical patterns.
It does not automatically fetch live Wingo results and cannot guarantee future outcomes.

## Deploy on Render
1. Upload all files in this ZIP to the ROOT of a GitHub repository.
2. In Render, create a new Web Service and connect that repository.
3. Select Docker runtime; the included Dockerfile provides the start command.
4. After deployment, check `/health` and `/docs` on your service URL.

The Dockerfile copies `main.py` from the repository root. It does not expect an `app/` folder.

## Data note
SQLite is stored at `/data/wingo.db`. On a free host without persistent storage, data may be lost after restarts or redeploys.
