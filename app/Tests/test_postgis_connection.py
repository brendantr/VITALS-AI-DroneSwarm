from sqlalchemy import create_engine, text

# This is the default connection string used by postgis_handler.py
engine = create_engine("postgresql://renderer:renderer@localhost:5432/gis")

with engine.connect() as conn:
    # Test 1: Basic connection
    result = conn.execute(text("SELECT 1"))
    print("✅ Database connection successful!")

    # Test 2: Check OSM tables exist
    tables = conn.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'planet_osm%'"
    )).fetchall()
    print(f"✅ OSM tables found: {[t[0] for t in tables]}")

    # Test 3: Check data exists in polygon table
    count = conn.execute(text("SELECT count(*) FROM planet_osm_polygon")).fetchone()
    print(f"✅ planet_osm_polygon rows: {count[0]}")

    # Test 4: Check data exists in line table
    count = conn.execute(text("SELECT count(*) FROM planet_osm_line")).fetchone()
    print(f"✅ planet_osm_line rows: {count[0]}")

    # Test 5: Check buildings exist in your area (UCF/Cape Canaveral area)
    buildings = conn.execute(text("""
        SELECT count(*) FROM planet_osm_polygon
        WHERE building IS NOT NULL
        AND ST_Intersects(way, ST_Transform(ST_MakeEnvelope(-81.21, 28.59, -81.19, 28.61, 4326), 3857))
    """)).fetchone()
    print(f"✅ Buildings near UCF area: {buildings[0]}")