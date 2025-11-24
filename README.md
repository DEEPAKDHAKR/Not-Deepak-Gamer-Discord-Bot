sudo apt update
sudo apt upgrade -y
sudo apt install python3 python3-pip -y

sudo apt install git -y
git clone <YOUR_GITHUB_REPO_URL>
cd <your-bot-folder>

pip3 install -r requirements.txt
pip3 install discord.py

start Bot
python3 bot.py
