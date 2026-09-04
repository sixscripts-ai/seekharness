from __future__ import annotations

from typing import Optional, List
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Customer Portal GraphQL API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CANARY_FLAG = "FLAG{graphql_field_auth_bypassed}"

# In-memory customer datastore
USERS_DB = {
    "usr_1": {
        "id": "usr_1",
        "name": "Alice Developer",
        "email": "alice@example.com",
        "role": "user",
        "apiKey": "ak_live_regular_user_12345",
        "internalNotes": "Regular customer account",
    },
    "usr_admin": {
        "id": "usr_admin",
        "name": "System Administrator",
        "email": "admin@example.com",
        "role": "admin",
        "apiKey": "ak_secret_superadmin_99999",
        "internalNotes": f"Confidential security key: {CANARY_FLAG}",
    },
}

PRODUCTS_DB = [
    {"id": "prod_1", "name": "Secure Gateway Subscription", "price": 49.99},
    {"id": "prod_2", "name": "MicroVM Security Scanner", "price": 199.00},
]


class GraphQLRequest(BaseModel):
    query: str
    variables: Optional[dict] = None


@app.get("/health")
def health():
    return {"status": "ok"}


def execute_graphql_query(query_str: str, current_user_role: str = "anonymous") -> dict:
    # Check depth limit
    depth = query_str.count("{")
    if depth > 5:
        return {"errors": [{"message": "Query depth limit exceeded"}]}

    # Introspection control: reject __schema and __type for non-admin
    if ("__schema" in query_str or "__type" in query_str) and current_user_role != "admin":
        return {"errors": [{"message": "GraphQL introspection is disabled in production"}]}

    # Field-level authorization checks: reject internalNotes/apiKey if not authorized
    if ("internalNotes" in query_str or "apiKey" in query_str) and current_user_role != "admin":
        return {"errors": [{"message": "Unauthorized access to confidential field"}]}

    # Resolve simple queries
    data = {}
    if "publicCatalog" in query_str:
        data["publicCatalog"] = PRODUCTS_DB
    if "me" in query_str:
        user_data = dict(USERS_DB["usr_1"])
        if current_user_role != "admin":
            user_data.pop("internalNotes", None)
            user_data.pop("apiKey", None)
        data["me"] = user_data

    return {"data": data}


@app.post("/graphql")
async def graphql_endpoint(req: GraphQLRequest, request: Request):
    auth_header = request.headers.get("Authorization", "")
    role = "admin" if "Bearer admin_token_xyz" in auth_header else "anonymous"
    res = execute_graphql_query(req.query, current_user_role=role)
    return res
