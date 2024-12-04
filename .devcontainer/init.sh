apt update
apt upgrade -y

apt install build-essential -y
apt install libsqlite3-dev -y
apt install software-properties-common -y
apt install libpq-dev -y

pip install -r src/requirements.txt
