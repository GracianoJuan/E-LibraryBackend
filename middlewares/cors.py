from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
from dotenv import load_dotenv
import os

load_dotenv()

origins = os.getenv("CLIENT_URL") or os.getenv("CLENT_URL") or "http://localhost:3000"
origins = origins.split(",")

def cors(app: FastAPI):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )