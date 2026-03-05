from sqlalchemy import create_engine, text

engine = create_engine("postgresql://renderer:renderer@localhost:5432/gis")

with engine.connect() as conn:
    # Test 1: Total rows in the database
    total = conn.execute(text("SELECT count(*) FROM planet_osm_polygon")).fetchone()
    print(f"Total polygons in DB: {total[0]}")

    total_lines = conn.execute(text("SELECT count(*) FROM planet_osm_line")).fetchone()
    print(f"Total lines in DB: {total_lines[0]}")

    # Test 2: Check what geographic area the data covers
    extent = conn.execute(text("""
        SELECT
            ST_XMin(ST_Transform(ST_SetSRID(ST_Extent(way), 3857), 4326)) as min_lon,
            ST_YMin(ST_Transform(ST_SetSRID(ST_Extent(way), 3857), 4326)) as min_lat,
            ST_XMax(ST_Transform(ST_SetSRID(ST_Extent(way), 3857), 4326)) as max_lon,
            ST_YMax(ST_Transform(ST_SetSRID(ST_Extent(way), 3857), 4326)) as max_lat
        FROM planet_osm_polygon
    """)).fetchone()
    print(f"\nData geographic extent:")
    print(f"  Latitude:  {extent[1]:.4f} to {extent[3]:.4f}")
    print(f"  Longitude: {extent[0]:.4f} to {extent[2]:.4f}")

    # Test 3: Check if UCF area (28.59-28.61, -81.20 to -81.19) has data
    # The polygon data is stored in EPSG:3857, so we need to transform our search box
    ucf_check = conn.execute(text("""
        SELECT count(*) FROM planet_osm_polygon
        WHERE ST_Intersects(
            way,
            ST_Transform(ST_MakeEnvelope(-81.21, 28.59, -81.19, 28.61, 4326), 3857)
        )
    """)).fetchone()
    print(f"\nPolygons in UCF area: {ucf_check[0]}")

    # Test 4: Check buildings specifically
    buildings = conn.execute(text("""
        SELECT count(*) FROM planet_osm_polygon
        WHERE building IS NOT NULL
        AND ST_Intersects(
            way,
            ST_Transform(ST_MakeEnvelope(-81.21, 28.59, -81.19, 28.61, 4326), 3857)
        )
    """)).fetchone()
    print(f"Buildings in UCF area: {buildings[0]}")

    # Test 5: Check water
    water = conn.execute(text("""
        SELECT count(*) FROM planet_osm_polygon
        WHERE water IS NOT NULL OR waterway IS NOT NULL OR "natural" = 'water'
    """)).fetchone()
    print(f"\nTotal water features in DB: {water[0]}")

    # Test 6: Check what columns exist (the query uses 'building' and 'water' columns)
    columns = conn.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'planet_osm_polygon'
        AND column_name IN ('building', 'water', 'highway', 'waterway', 'natural')
        ORDER BY column_name
    """)).fetchall()
    print(f"\nRelevant columns in planet_osm_polygon: {[c[0] for c in columns]}")