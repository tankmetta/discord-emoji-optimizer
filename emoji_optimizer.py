#!/usr/bin/env python3
"""
Discord Emoji Optimizer
Watches a folder for new images and automatically optimizes them for Discord emojis.

Discord emoji requirements:
- Max size: 256KB
- Max dimensions: 128x128 pixels
- Formats: PNG, JPG, GIF
"""

import os
import sys
import time
import shutil
from pathlib import Path
from PIL import Image
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configuration
INPUT_FOLDER = Path(__file__).parent / "input"
OUTPUT_FOLDER = Path(__file__).parent / "output"
MAX_SIZE_BYTES = 256 * 1024  # 256KB
MAX_DIMENSIONS = (128, 128)
SUPPORTED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}


def ensure_folders():
    """Create input and output folders if they don't exist."""
    INPUT_FOLDER.mkdir(exist_ok=True)
    OUTPUT_FOLDER.mkdir(exist_ok=True)


def optimize_image(input_path: Path) -> Path | None:
    """
    Optimize an image for Discord emoji use.
    Returns the output path if successful, None otherwise.
    """
    try:
        print(f"Processing: {input_path.name}")

        # Open the image
        with Image.open(input_path) as img:
            # Handle animated GIFs
            is_animated = getattr(img, 'is_animated', False)

            if is_animated:
                return optimize_animated_gif(input_path)

            # Convert to RGBA if necessary (for transparency support)
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                img = img.convert('RGBA')
                output_format = 'PNG'
                output_ext = '.png'
            else:
                img = img.convert('RGB')
                output_format = 'PNG'
                output_ext = '.png'

            # Resize to fit within 128x128 while maintaining aspect ratio
            img.thumbnail(MAX_DIMENSIONS, Image.Resampling.LANCZOS)

            # Create output path
            output_path = OUTPUT_FOLDER / f"{input_path.stem}_emoji{output_ext}"

            # Save with compression, adjusting quality to meet size requirement
            if output_format == 'PNG':
                # Try saving as PNG first
                img.save(output_path, format='PNG', optimize=True)

                # If too large, try reducing colors or switching to JPEG
                if output_path.stat().st_size > MAX_SIZE_BYTES:
                    # Try quantizing to reduce file size
                    if img.mode == 'RGBA':
                        img_quantized = img.quantize(colors=256, method=Image.Mediancut, dither=Image.Dither.FLOYDSTEINBERG)
                        img_quantized.save(output_path, format='PNG', optimize=True)

                    # If still too large, convert to JPEG (loses transparency)
                    if output_path.stat().st_size > MAX_SIZE_BYTES:
                        output_path = OUTPUT_FOLDER / f"{input_path.stem}_emoji.jpg"
                        img_rgb = img.convert('RGB')
                        save_with_size_limit(img_rgb, output_path, 'JPEG')

            file_size = output_path.stat().st_size
            print(f"  Saved: {output_path.name} ({file_size / 1024:.1f}KB)")
            return output_path

    except Exception as e:
        print(f"  Error processing {input_path.name}: {e}")
        return None


def optimize_animated_gif(input_path: Path) -> Path | None:
    """Optimize an animated GIF for Discord."""
    try:
        output_path = OUTPUT_FOLDER / f"{input_path.stem}_emoji.gif"

        with Image.open(input_path) as img:
            frames = []
            durations = []

            try:
                while True:
                    # Resize each frame
                    frame = img.copy()
                    frame.thumbnail(MAX_DIMENSIONS, Image.Resampling.LANCZOS)
                    frames.append(frame)
                    durations.append(img.info.get('duration', 100))
                    img.seek(img.tell() + 1)
            except EOFError:
                pass

            if frames:
                # Save optimized GIF
                frames[0].save(
                    output_path,
                    save_all=True,
                    append_images=frames[1:],
                    duration=durations,
                    loop=img.info.get('loop', 0),
                    optimize=True
                )

                # If still too large, reduce frames or colors
                if output_path.stat().st_size > MAX_SIZE_BYTES:
                    # Try reducing frame count
                    reduced_frames = frames[::2]  # Take every other frame
                    reduced_durations = [d * 2 for d in durations[::2]]

                    reduced_frames[0].save(
                        output_path,
                        save_all=True,
                        append_images=reduced_frames[1:],
                        duration=reduced_durations,
                        loop=img.info.get('loop', 0),
                        optimize=True
                    )

                file_size = output_path.stat().st_size
                print(f"  Saved: {output_path.name} ({file_size / 1024:.1f}KB, {len(frames)} frames)")
                return output_path

    except Exception as e:
        print(f"  Error processing animated GIF {input_path.name}: {e}")
        return None


def save_with_size_limit(img: Image.Image, output_path: Path, format: str):
    """Save image, reducing quality until it fits under the size limit."""
    quality = 95

    while quality > 10:
        img.save(output_path, format=format, quality=quality, optimize=True)
        if output_path.stat().st_size <= MAX_SIZE_BYTES:
            break
        quality -= 5


class ImageHandler(FileSystemEventHandler):
    """Handle new images dropped into the input folder."""

    def __init__(self):
        self.processed_files = set()

    def on_created(self, event):
        if event.is_directory:
            return

        path = Path(event.src_path)

        # Check if it's a supported image
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return

        # Avoid processing the same file twice
        if path in self.processed_files:
            return

        # Wait a moment for the file to finish writing
        time.sleep(0.5)

        # Check if file still exists and is complete
        if not path.exists():
            return

        self.processed_files.add(path)
        optimize_image(path)


def process_existing_files():
    """Process any images already in the input folder."""
    for file_path in INPUT_FOLDER.iterdir():
        if file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
            optimize_image(file_path)


def main():
    ensure_folders()

    print("=" * 50)
    print("Discord Emoji Optimizer")
    print("=" * 50)
    print(f"Input folder:  {INPUT_FOLDER.absolute()}")
    print(f"Output folder: {OUTPUT_FOLDER.absolute()}")
    print("-" * 50)

    # Process existing files first
    existing_files = list(INPUT_FOLDER.glob("*"))
    image_files = [f for f in existing_files if f.suffix.lower() in SUPPORTED_EXTENSIONS]

    if image_files:
        print(f"Processing {len(image_files)} existing image(s)...")
        process_existing_files()
        print("-" * 50)

    print("Watching for new images... (Press Ctrl+C to stop)")
    print()

    # Set up folder watcher
    event_handler = ImageHandler()
    observer = Observer()
    observer.schedule(event_handler, str(INPUT_FOLDER), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        observer.stop()

    observer.join()
    print("Done!")


if __name__ == "__main__":
    main()
