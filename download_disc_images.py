#!/usr/bin/env python3
"""
Download disc images from weblinks and store in SQLite database.
- Extracts image URL from webpage using selector: a.img-holder img.img-fluid
- Converts webp to png for DB Browser compatibility
- Stores image as BLOB in 'img' column
- Also saves to ./images/ folder as backup
"""

import sqlite3
import os
import re
import io
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from PIL import Image

# Configuration
DB_PATH = "disc_flight_data.db"
IMAGES_DIR = Path("./images")
MAX_WORKERS = 10
REQUEST_TIMEOUT = 30
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)


def ensure_img_column(db_path: str) -> None:
    """Add 'img' BLOB column if it doesn't exist."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if column exists
    cursor.execute("PRAGMA table_info(disc_data)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if "img" not in columns:
        logger.info("Adding 'img' column to disc_data table")
        cursor.execute("ALTER TABLE disc_data ADD COLUMN img BLOB")
        conn.commit()
    else:
        logger.info("'img' column already exists")
    
    conn.close()


def get_discs_to_process(db_path: str) -> list[dict]:
    """Fetch discs that need image download (have weblink, no img)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, model, manufacturer, weblink 
        FROM disc_data 
        WHERE weblink IS NOT NULL 
          AND weblink != '' 
          AND (img IS NULL OR img = '')
    """)
    
    discs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    logger.info(f"Found {len(discs)} discs to process")
    return discs


def extract_image_url(weblink: str) -> str | None:
    """
    Visit webpage and extract image URL from:
    a.img-holder img.img-fluid
    """
    headers = {"User-Agent": USER_AGENT}
    
    try:
        response = requests.get(weblink, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Find a.img-holder > img.img-fluid
        img_holder = soup.select_one("a.img-holder img.img-fluid")
        
        if img_holder and img_holder.get("src"):
            img_url = img_holder["src"]
            # Handle relative URLs
            if img_url.startswith("//"):
                img_url = "https:" + img_url
            elif img_url.startswith("/"):
                parsed = urlparse(weblink)
                img_url = f"{parsed.scheme}://{parsed.netloc}{img_url}"
            return img_url
        
        return None
        
    except Exception as e:
        logger.error(f"Failed to extract image URL from {weblink}: {e}")
        return None


def download_and_convert_image(img_url: str) -> bytes | None:
    """Download image and convert to PNG bytes."""
    headers = {"User-Agent": USER_AGENT}
    
    try:
        response = requests.get(img_url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        
        # Open image and convert to PNG
        img = Image.open(io.BytesIO(response.content))
        
        # Convert to RGB if necessary (for PNG compatibility)
        if img.mode in ("RGBA", "LA", "P"):
            # Keep alpha channel for PNG
            if img.mode == "P":
                img = img.convert("RGBA")
        elif img.mode != "RGB":
            img = img.convert("RGB")
        
        # Save as PNG to bytes
        png_buffer = io.BytesIO()
        img.save(png_buffer, format="PNG", optimize=True)
        return png_buffer.getvalue()
        
    except Exception as e:
        logger.error(f"Failed to download/convert image {img_url}: {e}")
        return None


def sanitize_filename(name: str) -> str:
    """Remove/replace invalid filename characters."""
    # Replace problematic characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', name)
    sanitized = re.sub(r'\s+', '_', sanitized)
    return sanitized


def process_disc(disc: dict) -> tuple[int, bytes | None, str | None]:
    """
    Process a single disc: extract URL, download, convert.
    Returns: (disc_id, png_bytes, filename)
    """
    disc_id = disc["id"]
    weblink = disc["weblink"]
    manufacturer = disc["manufacturer"]
    model = disc["model"]
    
    filename = f"{sanitize_filename(manufacturer)}_{sanitize_filename(model)}.png"
    
    logger.info(f"Processing: {manufacturer} {model} (ID: {disc_id})")
    
    # Extract image URL from webpage
    img_url = extract_image_url(weblink)
    if not img_url:
        logger.warning(f"No image URL found for {manufacturer} {model}")
        return (disc_id, None, None)
    
    # Download and convert to PNG
    png_bytes = download_and_convert_image(img_url)
    if not png_bytes:
        return (disc_id, None, None)
    
    logger.info(f"Successfully processed: {manufacturer} {model} ({len(png_bytes)} bytes)")
    return (disc_id, png_bytes, filename)


def save_to_file(filename: str, data: bytes) -> None:
    """Save image bytes to file."""
    filepath = IMAGES_DIR / filename
    with open(filepath, "wb") as f:
        f.write(data)


def update_db_image(db_path: str, disc_id: int, img_data: bytes) -> None:
    """Update single disc's img column."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE disc_data SET img = ? WHERE id = ?", (img_data, disc_id))
    conn.commit()
    conn.close()


def main():
    # Ensure images directory exists
    IMAGES_DIR.mkdir(exist_ok=True)
    
    # Ensure img column exists
    ensure_img_column(DB_PATH)
    
    # Get discs to process
    discs = get_discs_to_process(DB_PATH)
    
    if not discs:
        logger.info("No discs to process")
        return
    
    success_count = 0
    fail_count = 0
    
    # Process concurrently
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_disc = {executor.submit(process_disc, disc): disc for disc in discs}
        
        for future in as_completed(future_to_disc):
            disc = future_to_disc[future]
            try:
                disc_id, png_bytes, filename = future.result()
                
                if png_bytes and filename:
                    # Save to database
                    update_db_image(DB_PATH, disc_id, png_bytes)
                    
                    # Save to file as backup
                    save_to_file(filename, png_bytes)
                    
                    success_count += 1
                else:
                    fail_count += 1
                    
            except Exception as e:
                logger.error(f"Error processing disc {disc['id']}: {e}")
                fail_count += 1
    
    logger.info(f"Completed: {success_count} success, {fail_count} failed")


if __name__ == "__main__":
    main()