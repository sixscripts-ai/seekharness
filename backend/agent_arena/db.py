from appwrite.client import Client
from appwrite.services.databases import Databases

from .config import settings
from .hermetic import assert_not_hermetic


def get_client() -> Client:
    assert_not_hermetic("appwrite")
    s = settings()
    return (
        Client()
        .set_endpoint(s["APPWRITE_ENDPOINT"])
        .set_project(s["APPWRITE_PROJECT_ID"])
        .set_key(s["APPWRITE_API_KEY"])
    )


def get_databases() -> Databases:
    return Databases(get_client())


def get_database_id() -> str:
    return settings()["APPWRITE_DATABASE_ID"]
