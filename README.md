# YouTube Audiobook App - Docker Deployment

This guide provides instructions for deploying the YouTube Audiobook App on a Raspberry Pi 5 using Docker.

## Prerequisites

1. Raspberry Pi 5 with Raspberry Pi OS (64-bit) or any ARM64 Linux distribution
2. Docker installed
3. Docker Compose installed

## Installing Docker on Raspberry Pi 5

If Docker is not already installed, run these commands:

```bash
# Update package index
sudo apt update

# Install prerequisites
sudo apt install -y apt-transport-https ca-certificates curl gnupg lsb-release

# Add Docker's official GPG key
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Install Docker Compose
sudo apt install -y docker-compose-plugin

# Add your user to the docker group (optional, to avoid using sudo)
sudo usermod -aG docker $USER

# Log out and log back in for changes to take effect
```

## Deployment Steps

1. Clone or copy your application files to the Raspberry Pi:
   ```bash
   # Navigate to your project directory (suggestion: create in home directory)
   cd ~
   mkdir youtube-audiobook-app && cd youtube-audiobook-app
   # Copy all application files (app.py, requirements.txt, templates/, Dockerfile, etc.) to this directory
   ```

2. Ensure your source directories exist and have proper permissions:
   ```bash
   # Make sure your books directory exists
   ls -la /home/yassir/ebooks/calibre-library
   
   # Make sure your downloads directory exists
   ls -la /home/yassir/shared-sync/audiobooks
   ```
   
   If the downloads directory doesn't exist, create it:
   ```bash
   mkdir -p /home/yassir/shared-sync/audiobooks
   ```

3. Make sure you have the following files in your project directory:
   - `app.py` - Main application file
   - `requirements.txt` - Python dependencies
   - `templates/index.html` - Frontend template
   - `Dockerfile` - Docker configuration
   - `docker-compose.yml` - Docker Compose configuration
   - `.dockerignore` - Files to ignore during Docker build
   - `.env` - Environment variables (optional, but recommended)

4. Create the instance directory for the database:
   ```bash
   mkdir -p instance
   ```

5. Build and start the application using Docker Compose:
   ```bash
   docker compose up -d
   ```

6. The application will be accessible at `http://<your-pi-ip>:8080`

## Managing the Application

- Start the application: `docker compose up -d`
- Stop the application: `docker compose down`
- View logs: `docker compose logs -f`
- Restart the application: `docker compose restart`
- Check running containers: `docker compose ps`

## Configuration

The application supports dynamic path configuration through the web interface. You can change the books and downloads directory paths directly from the settings panel in the application.

Note: The docker-compose.yml is already configured to use your specific paths:
- Books will be read from `/home/yassir/ebooks/calibre-library` 
- Downloads will be saved to `/home/yassir/shared-sync/audiobooks`

The application will automatically use these paths when it runs in the container. If you want to customize the paths later, you can modify the volumes section in `docker-compose.yml`.

## Persistent Data

The following volumes are mounted to persist data:
- `/home/yassir/ebooks/calibre-library` - Book files directory (mounted to /app/books in container)
- `/home/yassir/shared-sync/audiobooks` - Downloaded audiobooks directory (mounted to /app/downloads in container)
- `./instance` - SQLite database file

These directories will persist between container updates and restarts.

## Updating the Application

1. Pull the latest changes to your application code
2. Rebuild the container:
   ```bash
   docker compose build --no-cache
   docker compose up -d
   ```

## Troubleshooting

- If you encounter permission issues with your book or download directories, make sure they have the correct ownership:
  ```bash
  # For your books directory
  sudo chown -R 1000:1000 /home/yassir/ebooks/calibre-library
  
  # For your downloads directory  
  sudo chown -R 1000:1000 /home/yassir/shared-sync/audiobooks
  
  # For the database directory
  sudo chown -R 1000:1000 ./instance
  ```

- To check container logs:
  ```bash
  docker logs youtube-audiobook-app
  ```

- If the application fails to start, check for errors in the logs:
  ```bash
  docker compose logs
  ```

## Hardware Notes

This application is optimized for Raspberry Pi 5's ARM64 architecture. The Dockerfile specifically targets ARM64 to ensure compatibility. The application uses yt-dlp for downloading YouTube content, which may require significant resources during processing. Downloads are converted to MP3 format using FFmpeg, which is included in the container.

## Security

The container runs as a non-root user for security. The application uses basic Flask without authentication - consider adding a reverse proxy with authentication if exposing to the internet.