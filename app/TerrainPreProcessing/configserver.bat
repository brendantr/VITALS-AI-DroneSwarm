docker volume create osm-data

docker run -w /us-south-260304.osm.pbf:/data/region.osm.pbf -v osm-data:/data/database/ overv/openstreetmap-tile-server import

docker volume create osm-tiles
