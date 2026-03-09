import pandas as pd

def osmnx_load_rtree(rtree_index,search_tags, results):
    i = 0
    for idx, landmark_row in results.iterrows():
        geom = landmark_row['geometry']
        #print(idx)
        #id = landmark_row["osmid"]
        #store only the relevant tags into the filtered_dict, none of the other stuff
        filtered_dict = {key: landmark_row[key] if not pd.isna(landmark_row[key]) else None for key in search_tags.keys() if key in landmark_row}
        # Optionally, if you want to also include geometry in the stored object:
        filtered_dict['geometry'] = landmark_row['geometry']
        #filtered_dict['geometry'] = landmark_row['osm_id']
        filtered_dict['osm_id'] = idx[1]
        rtree_index.insert(i, geom.bounds, obj=filtered_dict)
        i+=1