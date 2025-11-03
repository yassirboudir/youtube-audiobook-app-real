import os
import json
import re
import logging
from pathlib import Path
from typing import List, Dict, Any
from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from youtube_search import YoutubeSearch
import yt_dlp
import threading

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ---------------------------- Config ----------------------------
# Initialize with default values, but allow dynamic changes
BOOKS_DIR = os.getenv("BOOKS_DIR", "./books")  # Directory containing book folders
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "./downloads")  # Directory for downloaded MP3s

# Global variables to store the current paths
current_books_dir = BOOKS_DIR
current_download_dir = DOWNLOAD_DIR
os.makedirs(current_download_dir, exist_ok=True)

# ---------------------------- App & DB ----------------------------
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///history.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Database model
class History(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    book_title = db.Column(db.String(500))
    author = db.Column(db.String(500))
    youtube_title = db.Column(db.String(500))
    youtube_url = db.Column(db.String(500))
    download_path = db.Column(db.String(1000))
    added_at = db.Column(db.String(50), default=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    status = db.Column(db.String(20), default='pending')  # pending, downloading, completed, failed
    progress = db.Column(db.Float, default=0.0)  # Download progress percentage (0.0 to 100.0)
    total_size = db.Column(db.BigInteger, default=0)  # Total size of the file being downloaded
    downloaded_size = db.Column(db.BigInteger, default=0)  # Size downloaded so far

# Create tables
with app.app_context():
    db.create_all()


# Route to initialize/recreate the database
@app.route('/init-db')
def init_db():
    """Initialize or recreate the database with the current schema"""
    try:
        db.drop_all()
        db.create_all()
        return jsonify({"message": "Database initialized successfully"})
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")
        return jsonify({"error": f"Error initializing database: {str(e)}"}), 500

# ---------------------------- Book Scanning ----------------------------
def extract_author_title(folder_name: str) -> tuple[str, str]:
    """
    Extract author and title from folder name using common patterns
    E.g. "Author Name - Book Title" or "Book Title by Author Name"
    """
    # Pattern: "Author Name - Book Title"
    match = re.match(r"^(.*?)\s*[-–—]+\s*(.*)$", folder_name.strip())
    if match:
        author = match.group(1).strip()
        title = match.group(2).strip()
        return author, title

    # Pattern: "Book Title by Author Name"
    match = re.match(r"^(.*?)\s+by\s+(.*)$", folder_name.strip(), re.IGNORECASE)
    if match:
        title = match.group(1).strip()
        author = match.group(2).strip()
        return author, title

    # If no pattern matches, return folder name as title with empty author
    return "", folder_name.strip()

def scan_book_files() -> List[Dict[str, str]]:
    """Scan the current_books_dir for book files and folders and extract author/title info"""
    book_items = []
    
    books_path = Path(current_books_dir)
    if not books_path.exists():
        logger.warning(f"Books directory does not exist: {current_books_dir}")
        return book_items

    # Define supported book file extensions
    book_extensions = {'.pdf', '.epub', '.mobi', '.azw', '.azw3', '.djvu', '.fb2', '.html', '.lit', '.lrf', '.odt', '.prc', '.rb', '.rtf', '.txt'}
    
    for item in books_path.iterdir():
        if item.is_dir():
            # Handle directories (existing behavior)
            author, title = extract_author_title(item.name)
            book_items.append({
                "item_name": item.name,
                "full_path": str(item.absolute()),
                "author": author,
                "title": title,
                "search_query": f"{title} {author}".strip(),
                "type": "folder"
            })
        elif item.is_file() and item.suffix.lower() in book_extensions:
            # Handle book files
            author, title = extract_author_title(item.stem)  # Use stem (filename without extension)
            book_items.append({
                "item_name": item.name,
                "full_path": str(item.absolute()),
                "author": author,
                "title": title,
                "search_query": f"{title} {author}".strip(),
                "type": "file"
            })

    return book_items


def scan_book_folders() -> List[Dict[str, str]]:
    """Scan the BOOKS_DIR for book folders and extract author/title info"""
    # For backward compatibility, call the new more flexible function
    return scan_book_files()

# Global variables to store the current paths
current_books_dir = BOOKS_DIR
current_download_dir = DOWNLOAD_DIR

# ---------------------------- Routes ----------------------------
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/config')
def get_config():
    """Get current configuration"""
    global current_books_dir, current_download_dir
    return jsonify({
        "books_dir": current_books_dir,
        "download_dir": current_download_dir
    })

@app.route('/config', methods=['POST'])
def set_config():
    """Set new configuration paths"""
    global current_books_dir, current_download_dir
    try:
        data = request.get_json()
        new_books_dir = data.get("books_dir", current_books_dir)
        new_download_dir = data.get("download_dir", current_download_dir)
        
        # Validate that the paths exist or can be created
        if not os.path.isdir(new_books_dir):
            # Try to create the directory if it doesn't exist
            os.makedirs(new_books_dir, exist_ok=True)
            if not os.path.isdir(new_books_dir):
                return jsonify({"error": f"Books directory does not exist and could not be created: {new_books_dir}"}), 400
        
        if not os.path.isdir(new_download_dir):
            # Try to create the directory if it doesn't exist
            os.makedirs(new_download_dir, exist_ok=True)
            if not os.path.isdir(new_download_dir):
                return jsonify({"error": f"Download directory does not exist and could not be created: {new_download_dir}"}), 400
        
        # If both directories are valid, update the global variables
        current_books_dir = new_books_dir
        current_download_dir = new_download_dir
        
        return jsonify({
            "ok": True,
            "books_dir": current_books_dir,
            "download_dir": current_download_dir
        })
    except Exception as e:
        logger.error(f"Error updating config: {str(e)}")
        return jsonify({"error": f"Error updating configuration: {str(e)}"}), 500

@app.route('/health')
def health():
    return jsonify({"ok": True})

@app.route('/books')
def get_books():
    """Get list of book files and folders from the configured directory"""
    try:
        books = scan_book_folders()
        return jsonify({"books": books})
    except Exception as e:
        logger.error(f"Error scanning book files and folders: {str(e)}")
        return jsonify({"error": f"Error scanning book files and folders: {str(e)}"}), 500

# ---------------------------- YouTube Search ----------------------------
def search_youtube_sync(query: str, max_results: int = 10) -> List[Dict[str, Any]]:
    """Search YouTube for audiobook content matching the query"""
    try:
        # Use youtube-search-python library to search
        results = YoutubeSearch(query, max_results=max_results).to_dict()
        
        formatted_results = []
        for result in results:
            formatted_results.append({
                "id": result["id"],
                "title": result["title"],
                "channel": result["channel"],
                "duration": result.get("duration", "N/A"),
                "publish_time": result.get("publish_time", "N/A"),
                "view_count": result.get("view_count", "N/A"),
                "url": f"https://www.youtube.com/watch?v={result['id']}",
                "thumbnail": f"https://i.ytimg.com/vi/{result['id']}/hqdefault.jpg"
            })
        
        return formatted_results
    except Exception as e:
        logger.error(f"Error searching YouTube for '{query}': {str(e)}")
        return []

@app.route('/search', methods=['POST'])
def search_audiobooks():
    """Search YouTube for audiobooks based on the provided query"""
    payload = request.get_json()
    query = payload.get("query", "")
    max_results = payload.get("maxResults", 10)
    
    logger.info(f"Searching YouTube for: '{query}'")
    
    try:
        results = search_youtube_sync(query, max_results)
        logger.info(f"Found {len(results)} results for: '{query}'")
        return jsonify({"results": results, "query": query})
    except Exception as e:
        error_msg = f"YouTube search failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({"error": error_msg}), 502

# ---------------------------- Download Management ----------------------------
def download_youtube_audio(youtube_url: str, output_path: str, title: str, progress_callback=None) -> bool:
    """Download and convert YouTube video to MP3 with progress tracking"""
    try:
        def progress_hook(d):
            if d['status'] == 'downloading':
                if progress_callback:
                    # Calculate progress percentage
                    if 'total_bytes' in d and d['total_bytes'] > 0:
                        progress = (d['downloaded_bytes'] / d['total_bytes']) * 100
                        progress_callback(progress, d['total_bytes'], d['downloaded_bytes'])
                    elif 'total_bytes_estimate' in d and d['total_bytes_estimate'] > 0:
                        progress = (d['downloaded_bytes'] / d['total_bytes_estimate']) * 100
                        progress_callback(progress, d['total_bytes_estimate'], d['downloaded_bytes'])
                    else:
                        # If we don't have total bytes, we can't calculate exact progress
                        # Just indicate that download is happening
                        progress_callback(0.0, 0, d['downloaded_bytes'])

        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'postprocessor_args': [
                '-ar', '44100',  # Set audio sample rate
                '-ac', '2',      # Set audio channels
                '-b:a', '192k',  # Set audio bitrate
                '-vn',           # Remove video stream
            ],
            'prefer_ffmpeg': True,
            'audioquality': '0',
            'extractaudio': True,
            'audioformat': 'mp3',
            'outtmpl': output_path.replace('.%(ext)s', '.mp3'),  # Ensure .mp3 extension
            'noplaylist': True,
            'quiet': True,
            'no_warnings': False,
            'progress_hooks': [progress_hook],
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([youtube_url])
        
        logger.info(f"Successfully downloaded and converted: {title}")
        return True
    except Exception as e:
        logger.error(f"Error downloading {youtube_url}: {str(e)}")
        return False

def update_download_progress(download_id: int, progress: float, total_size: int, downloaded_size: int):
    """Update download progress in the database"""
    try:
        with app.app_context():
            history_item = History.query.get(download_id)
            if history_item:
                history_item.progress = progress
                history_item.total_size = total_size
                history_item.downloaded_size = downloaded_size
                db.session.commit()
    except Exception as e:
        logger.error(f"Error updating progress for download {download_id}: {str(e)}")


def download_youtube_audio_async(download_id: int, youtube_url: str, output_path: str, book_title: str, author: str, youtube_title: str):
    """Asynchronous wrapper for downloading YouTube audio with progress tracking"""
    def progress_callback(progress, total_size, downloaded_size):
        # Update progress in database
        update_download_progress(download_id, progress, total_size, downloaded_size)
    
    try:
        # Create a new application context for this thread
        with app.app_context():
            # Update database status to downloading
            history_item = History.query.get(download_id)
            if history_item:
                history_item.download_path = output_path
                history_item.status = 'downloading'
                history_item.progress = 0.0
                history_item.total_size = 0
                history_item.downloaded_size = 0
                db.session.commit()
            
            # Use the actual author name or "Unknown" in the title for the download function
            display_title = f"{book_title} by {author if author and author.strip() else 'Unknown'}"
            success = download_youtube_audio(youtube_url, output_path, display_title, progress_callback)
            
            # Update database status based on success
            history_item = History.query.get(download_id)
            if history_item:
                history_item.status = 'completed' if success else 'failed'
                if success:
                    # Set progress to 100% on completion
                    history_item.progress = 100.0
                db.session.commit()
    except Exception as e:
        logger.error(f"Error in async download for {youtube_url}: {str(e)}")
        with app.app_context():
            history_item = History.query.get(download_id)
            if history_item:
                history_item.status = 'failed'
                history_item.progress = 0.0
                db.session.commit()

@app.route('/download', methods=['POST'])
def download_audiobook():
    """Download a YouTube video as MP3 and add to history"""
    try:
        # Log the raw request data for debugging
        raw_data = request.get_data()
        logger.info(f"Raw request data: {raw_data}")
        
        data = request.get_json()
        if not data:
            logger.error("No JSON data provided in request")
            return jsonify({"error": "No JSON data provided"}), 400
            
        book_title = data.get("book_title")
        author = data.get("author")
        youtube_url = data.get("youtube_url")
        youtube_title = data.get("youtube_title")
        
        logger.info(f"Parsed data - book_title: {book_title}, author: {author}, youtube_url: {youtube_url}, youtube_title: {youtube_title}")
        
        # Check for missing or empty fields (excluding empty strings)
        if not book_title or not book_title.strip():
            logger.error("book_title is missing or empty")
            return jsonify({"error": "Missing required field: book_title"}), 400
        if not youtube_url or not youtube_url.strip():
            logger.error("youtube_url is missing or empty")
            return jsonify({"error": "Missing required field: youtube_url"}), 400
        if not youtube_title or not youtube_title.strip():
            logger.error("youtube_title is missing or empty")
            return jsonify({"error": "Missing required field: youtube_title"}), 400
        # Author can be empty string, so we don't check for it as required
        
        # Use 'Unknown' for empty author to avoid issues in filename
        display_author = author if author and author.strip() else "Unknown"
        logger.info(f"Starting download: {book_title} by {display_author} from {youtube_url}")
        
        # Create a unique filename for the download using the current download directory
        safe_title = re.sub(r'[<>:"/\\|?*]', '_', f"{display_author} - {book_title} - {youtube_title}")
        output_path = os.path.join(current_download_dir, f"{safe_title}.mp3")
        
        # Add to history with pending status
        history_item = History(
            book_title=book_title,
            author=author,  # Store the actual author value (could be empty)
            youtube_title=youtube_title,
            youtube_url=youtube_url,
            download_path=output_path,
            status='pending',
            progress=0.0,
            total_size=0,
            downloaded_size=0
        )
        db.session.add(history_item)
        db.session.commit()
        
        logger.info(f"Added download to history with ID: {history_item.id}")
        
        # Start download in a separate thread
        thread = threading.Thread(
            target=download_youtube_audio_async,
            args=(history_item.id, youtube_url, output_path, book_title, author, youtube_title)
        )
        thread.start()
        
        logger.info(f"Started download thread for ID: {history_item.id}")
        
        return jsonify({"ok": True, "download_id": history_item.id})
    except Exception as e:
        logger.error(f"Error starting download: {str(e)}", exc_info=True)
        return jsonify({"error": f"Error starting download: {str(e)}"}), 500

# ---------------------------- History ----------------------------
@app.route('/history')
def get_history():
    """Get download history"""
    try:
        history_items = History.query.order_by(History.id.desc()).limit(200).all()
        
        items = []
        for item in history_items:
            items.append({
                "id": item.id,
                "book_title": item.book_title,
                "author": item.author,
                "youtube_title": item.youtube_title,
                "youtube_url": item.youtube_url,
                "download_path": item.download_path,
                "added_at": item.added_at,
                "status": item.status,
                "progress": float(item.progress) if item.progress is not None else 0.0,
                "total_size": int(item.total_size) if item.total_size is not None else 0,
                "downloaded_size": int(item.downloaded_size) if item.downloaded_size is not None else 0
            })
        
        return jsonify({"items": items})
    except Exception as e:
        logger.error(f"Error getting history: {str(e)}")
        # Return empty items array to maintain expected structure
        return jsonify({"items": [], "error": str(e)})

@app.route('/history/<int:row_id>', methods=['DELETE'])
def delete_history(row_id):
    """Delete a history item"""
    history_item = History.query.get(row_id)
    if history_item:
        db.session.delete(history_item)
        db.session.commit()
    return jsonify({"ok": True})

@app.route('/progress/<int:download_id>')
def get_download_progress(download_id):
    """Get the progress of a specific download"""
    try:
        history_item = History.query.get(download_id)
        if not history_item:
            return jsonify({"error": "Download not found"}), 404
        
        return jsonify({
            "id": history_item.id,
            "status": history_item.status,
            "progress": float(history_item.progress) if history_item.progress is not None else 0.0,
            "total_size": int(history_item.total_size) if history_item.total_size is not None else 0,
            "downloaded_size": int(history_item.downloaded_size) if history_item.downloaded_size is not None else 0,
            "book_title": history_item.book_title,
            "author": history_item.author,
            "youtube_title": history_item.youtube_title,
            "youtube_url": history_item.youtube_url
        })
    except Exception as e:
        logger.error(f"Error getting download progress: {str(e)}")
        return jsonify({"error": f"Error getting download progress: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)