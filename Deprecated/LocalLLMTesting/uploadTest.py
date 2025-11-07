import requests
import os

# Path to the image file you want to upload
image_dir_path = './images/'
image_name = 'Picture1.jpg'
image_path = image_dir_path + image_name

# URL of the Express server upload endpoint
url = 'http://localhost:8800/api/upload'

# Open the file in binary mode and send it as a POST request
with open(image_path, 'rb') as image_file:
    files = {'image': image_file}
    response = requests.post(url, files=files)

# Print the server's response
print(response.json())

# Rename the image file to avoid conflicts
os.rename(image_path, image_dir_path + response.json()['filename'])

