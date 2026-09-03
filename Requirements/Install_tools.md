## Yt-dlp

### First-Time Installation

`sudo wget https://github.com -O /usr/local/bin/yt-dlp && sudo chmod a+rx /usr/local/bin/yt-dlp`

### Update Command

`sudo yt-dlp -U`

### Verify

`yt-dlp --version`

### Permanent fix: No manual updating
- Open your terminal and open the system's root automation file: `sudo crontab -e`
- *(If prompted to choose an editor, press 1 for Nano).*
- Scroll to the absolute bottom of the file and paste this line: `0 12 * * * /usr/local/bin/yt-dlp -U >/dev/null 2>&1`
- **What this does:** It forces your system to silently run sudo yt-dlp -U every single day at 12:00 PM in the background, updating it directly from GitHub without needing you to lift a finger or type a password.

## FFmpeg

### First-Time Installation

`sudo apt update && sudo apt install -y ffmpeg`

### Update Command

`sudo apt update && sudo apt --only-upgrade install ffmpeg`

### verify

`ffmpeg -version`


## Aria2c

### First-Time Installation

`sudo apt update && sudo apt install -y aria2`

### Update Command

`sudo apt update && sudo apt --only-upgrade install aria2`

### Verify

`aria2c --version`

### For Both **FFmpeg** and **Aria2c**
Open your terminal to run this single command. It forces the visual Update Manager to display updates immediately, exactly when the terminal sees them:
`echo 'Update-Manager::Always-Include-Phased-Updates "true";' | sudo tee /etc/apt/apt.conf.d/99force-visual-updates`
