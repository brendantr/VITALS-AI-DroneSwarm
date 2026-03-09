def classify_highway(highway_value):
    if not highway_value:
        return "unknown"

    highway_value = str(highway_value).lower()
    road_tags = {
        "motorway",
        "trunk",
        "primary",
        "secondary",
        "tertiary",
        "residential",
        "unclassified",
        "service",
        "living_street",
    }
    pedestrian_tags = {"footway", "path", "track", "bridleway", "pedestrian", "cycleway"}

    if highway_value in road_tags:
        return "highway"
    if highway_value in pedestrian_tags:
        return "pedestrian_path"
    return "highway"


def disambiguate(feature_type, value):
    if feature_type == "highway":
        return classify_highway(value)
    return feature_type
