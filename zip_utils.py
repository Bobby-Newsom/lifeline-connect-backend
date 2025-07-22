# zip_utils.py

city_to_zips = {
    "tulsa": ["74127", "74136", "74120", "74104", "74106", "74114"],
    "norman": ["73069", "73071", "73072"],
    "oklahoma city": ["73102", "73103", "73106", "73107", "73109", "73112", "73114", "73120"],
    # Add more cities and ZIPs here as needed
}

# Reverse mapping: zip -> city
zip_to_city_map = {}
for city, zips in city_to_zips.items():
    for zip_code in zips:
        zip_to_city_map[zip_code] = city