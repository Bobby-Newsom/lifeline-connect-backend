from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from pydantic import BaseModel
import pandas as pd

from zip_utils import zip_to_city_map, city_to_zips

app = FastAPI(
    title="LifeLine Connect API",
    description="API for accessing reentry and support resources by city, ZIP code, or virtual availability.",
    version="1.0.0",
)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Load and normalize data once at startup ---
df = pd.read_csv("resources.csv", dtype=str).fillna("")

# Normalize column names to match our Pydantic model
df.rename(
    columns={
        "isVirtual": "isvirtual",
        "is_virtual": "isvirtual",
        "Areas_Served": "areas_served",
        "areasServed": "areas_served",
    },
    inplace=True,
)

# Make sure all expected columns exist
required_cols = [
    "category",
    "name",
    "phone",
    "description",
    "address",
    "city",
    "state",
    "zip",
    "isvirtual",
    "website",
    "areas_served",
]
for col in required_cols:
    if col not in df.columns:
        df[col] = ""


# --- Pydantic model ---
class Resource(BaseModel):
    category: str = ""
    name: str
    phone: str = ""
    description: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    zip: str = ""
    isvirtual: str = ""
    website: str = ""
    areas_served: str = ""


# --- Routes ---
@app.get(
    "/resources/",
    response_model=List[Resource],
    tags=["Resources"],
    summary="Get resources by city, ZIP, or virtual availability",
)
def get_resources(
    city: Optional[str] = Query(None, description="City name (e.g., Tulsa)"),
    zip: Optional[str] = Query(None, description="ZIP code (e.g., 74136)"),
    is_virtual: Optional[bool] = Query(
        None, description="Filter by virtual services (true/false)"
    ),
):
    results = df.copy()

    # Filter by city or ZIP
    if city:
        results = results[results["city"].str.lower() == city.lower()]
    elif zip:
        matched_city = zip_to_city_map.get(zip)
        if matched_city:
            related_zips = city_to_zips.get(matched_city, [])
            results = results[
                results["zip"].isin(related_zips)
                | (results["city"].str.lower() == matched_city)
            ]
        else:
            results = results[results["zip"] == zip]

    # Filter virtual / non-virtual
    if is_virtual is not None:
        # CSV stores TRUE/FALSE (strings). Compare lowercased.
        results = results[
            results["isvirtual"].str.lower() == str(is_virtual).lower()
        ]

    return results.to_dict(orient="records")
