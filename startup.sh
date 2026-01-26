sudo apt install gstreamer1.0-plugins-bad gstreamer1.0-libav gstreamer1.0-gl -y
sudo apt install libfuse2 -y
sudo apt install libxcb-xinerama0 libxkbcommon-x11-0 libxcb-cursor-dev -y

chmod +x ../Downloads/QGroundControl-x86_64.AppImage

if [ ! -d "PX4-Autopilot/.git" ]; then
    git clone --recursive https://github.com/PX4/PX4-Autopilot.git
    bash PX4-Autopilot/Tools/setup/ubuntu.sh
else
    echo "PX4-Autopilot already exists"
fi
  source ~/.bashrc

../Downloads/QGroundControl-x86_64.AppImage 

sleep 60

echo "QGC loaded"

cd PX4-Autopilot
make px4_sitl gz_x500

echo "PX4 SITL started"

cd app
git pull
docker compose pull
docker compose up -d


