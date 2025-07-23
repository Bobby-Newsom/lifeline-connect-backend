from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List, Tuple
from pydantic import BaseModel
import pandas as pd
import re

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

df.rename(
    columns={
        "isVirtual": "isvirtual",
        "is_virtual": "isvirtual",
        "Areas_Served": "areas_served",
        "areasServed": "areas_served",
    },
    inplace=True,
)

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

    if is_virtual is not None:
        results = results[
            results["isvirtual"].str.lower() == str(is_virtual).lower()
        ]

    return results.to_dict(orient="records")


# -----------------------
# Helpers for /ask route
# -----------------------

ZIP_REGEX = re.compile(r"\b\d{5}\b")

def extract_location(query: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Return (city, zip) if found in text. City is lowercase.
    """
    q = query.lower()

    # Zip first
    m = ZIP_REGEX.search(q)
    if m:
        z = m.group(0)
        if z in zip_to_city_map:
            return zip_to_city_map[z], z
        return None, z

    # City match from our known list
    for c in city_to_zips.keys():
        if c in q:
            return c, None

    return None, None

FOOD_WORDS = ["food", "meal", "pantry", "hunger", "groceries", "eat"]
HOUSING_WORDS = ["housing", "shelter", "rent", "homeless"]
UTIL_WORDS = ["utility", "utilities", "electric", "water", "gas", "bill"]
MENTAL_HEALTH_WORDS = ["mental", "therapy", "counsel", "counseling", "therapist"]

def filter_by_topic(df_in: pd.DataFrame, query: str) -> pd.DataFrame:
    q = query.lower()
    if any(w in q for w in FOOD_WORDS):
        mask = df_in["category"].str.contains("food", case=False) | df_in["description"].str.contains("food|meal|pantry", case=False, na=False)
        return df_in[mask]
    if any(w in q for w in HOUSING_WORDS):
        mask = df_in["category"].str.contains("housing|shelter", case=False) | df_in["description"].str.contains("housing|shelter|rent", case=False, na=False)
        return df_in[mask]
    if any(w in q for w in UTIL_WORDS):
        mask = df_in["category"].str.contains("utilities", case=False) | df_in["description"].str.contains("utility|bill", case=False, na=False)
        return df_in[mask]
    if any(w in q for w in MENTAL_HEALTH_WORDS):
        mask = df_in["category"].str.contains("mental", case=False) | df_in["description"].str.contains("mental|therapy|counsel", case=False, na=False)
        return df_in[mask]

    # default: no topic filtering
    return df_in


# -------------
# /ask endpoint
# -------------
from fastapi import Body

class AskRequest(BaseModel):
    query: str

class AskResponse(BaseModel):
    response: str
    resources: List[Resource] = []


@app.post("/ask", response_model=AskResponse, tags=["Chat"])
def ask(payload: AskRequest = Body(...)):
    query = payload.query.strip()
    if not query:
        return AskResponse(response="Please enter a question.", resources=[])

    # location detection
    city, z = extract_location(query)

    filtered = df.copy()

    # Narrow by location if we got one
    if city:
        related_zips = city_to_zips.get(city, [])
        filtered = filtered[
            (filtered["city"].str.lower() == city)
            | (filtered["zip"].isin(related_zips))
        ]
    elif z:
        matched_city = zip_to_city_map.get(z)
        if matched_city:
            related_zips = city_to_zips.get(matched_city, [])
            filtered = filtered[
                filtered["zip"].isin(related_zips)
                | (filtered["city"].str.lower() == matched_city)
            ]
        else:
            filtered = filtered[filtered["zip"] == z]

    # Topic filter (food, housing, etc.)
    filtered = filter_by_topic(filtered, query)

    # If still empty, just fallback to original df (or return none)
    if filtered.empty:
        filtered = df.copy()

    # Limit to 10 results
    filtered = filtered.head(10)

    # Build a friendly text
    if city:
        loc_text = city.title()
    elif z:
        loc_text = z
    else:
        loc_text = "your area"

    topic_word = ""
    ql = query.lower()
    if any(w in ql for w in FOOD_WORDS):
        topic_word = "food "
    elif any(w in ql for w in HOUSING_WORDS):
        topic_word = "housing "
    elif any(w in ql for w in UTIL_WORDS):
        topic_word = "utility "
    elif any(w in ql for w in MENTAL_HEALTH_WORDS):
        topic_word = "mental health "

    text_intro = f"Here are some {topic_word}resources near {loc_text}:"

    # Convert to dict list for response_model
    resources_out = filtered.to_dict(orient="records")

    return AskResponse(response=text_intro, resources=resources_out)
