
AFO_download.py:
Trains the YOLOv11 model using a dataset.
Configures the training settings such as the dataset path (AFO-1/data.yaml), model file (yolo11l.pt), number of epochs (100), and device (cpu/gpu).
Saves the training results to the folder runs/train/AFO_train​


AFO_Train.py:
Downloads a dataset from Roboflow using an API key.
Saves the dataset into a folder named "AFO-1" in the current working directory.
Prints the location of the downloaded dataset​


NOTES: 
Modify AFO_Train.py to set device="cuda" to enable GPU usage if available.
use "pip install -r requirements.txt" in your environment to download all the dependencies.