import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

_MONGO_CLIENT = None

def get_db():
    global _MONGO_CLIENT

    mongo_uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("DB_NAME", "edgeproject")

    if not mongo_uri:
        raise RuntimeError("MONGODB_URI is missing. Put it in .env")

    if _MONGO_CLIENT is None:
        _MONGO_CLIENT = MongoClient(mongo_uri)

    return _MONGO_CLIENT[db_name]