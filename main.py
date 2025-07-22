from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from pydantic import BaseModel
import pandas as pd
import json

from zip_utils import zip_to_city_map, city_to_zips

app = FastAPI(
    title="LifeLine Connect API",
    description="API for accessing reentry and support resources by city, ZIP code, or virtual availability.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load CSV on startup
df = pd.read_csv("resources.csv", dtype=str)
df = df.fillna("")

# Normalize column names if needed
df.rename(
    columns={
        "isVirtual": "isvirtual",
        "Areas_Served": "areas_served"
    },
    inplace=True
)

# Ensure the new columns exist even if missing in the original
for col in ["isvirtual", "areas_served"]:
    if col not in df.columns:
        df[col] = ""

# 1. Define Pydantic model
class Resource(BaseModel):
    category: Optional[str] = ""
    name: str
    phone: Optional[str] = ""
    description: Optional[str] = ""
    address: Optional[str] = ""
    city: str
    state: str
    zip: Optional[str] = ""
    isvirtual: Optional[str] = ""
    website: Optional[str] = ""
    areas_served: Optional[str] = ""

# 2. Route with enhanced docs + response model
@app.get("/resources/", response_model=List[Resource], tags=["Resources"], summary="Get resources by city, ZIP, or virtual availability")
def get_resources(
    city: Optional[str] = Query(None, description="City name (e.g., Tulsa)"),
    zip: Optional[str] = Query(None, description="ZIP code (e.g., 74136)"),
    is_virtual: Optional[bool] = Query(None, description="Filter by virtual services")
):
    results = df.copy()

    if city:
        results = results[results["city"].str.lower() == city.lower()]
    elif zip:
        matched_city = zip_to_city_map.get(zip)
        if matched_city:
            related_zips = city_to_zips.get(matched_city, [])
            results = results[results["zip"].isin(related_zips) | (results["city"].str.lower() == matched_city)]
        else:
            results = results[results["zip"] == zip]

    if is_virtual is not None:
        results = results[results["isvirtual"].str.lower() == str(is_virtual).lower()]

    return json.loads(results.to_json(orient="records"))
