docker volume create osm-data

docker run -v /home/alex/Downloads/us-south-260211.osm.pbf:/data/region.osm.pbf -v osm-data:/data/database/ overv/openstreetmap-tile-server import

docker volume create osm-tiles
