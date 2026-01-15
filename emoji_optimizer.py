#!/usr/bin/env python3
"""
Discord Emoji Optimizer
Watches a folder for new images and automatically optimizes them for Discord emojis.

Features:
- Removes background automatically (keeps only the subject)
- Resizes to 128x128 max
- Compresses to under 256KB

Discord emoji requirements:
- Max size: 256KB
- Max dimensions: 128x128 pixels
- Formats: PNG, JPG, GIF
"""

import io
import time
from pathlib import Path
from typing import Optional
from PIL import Image
from rembg import remove
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


def remove_background(img: Image.Image) -> Image.Image:
    """Remove the background from an image, keeping only the subject."""
    # Convert to bytes for rembg
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)

    # Remove background
    output_bytes = remove(img_byte_arr.getvalue())

    # Convert back to PIL Image
    return Image.open(io.BytesIO(output_bytes))


def optimize_image(input_path: Path) -> Optional[Path]:
    """
    Optimize an image for Discord emoji use.
    Removes background, resizes, and compresses.
    Returns the output path if successful, None otherwise.
    """
    try:
        print(f"Processing: {input_path.name}")

        # Open the image
        with Image.open(input_path) as img:
            # Handle animated GIFs differently
            is_animated = getattr(img, 'is_animated', False)

            if is_animated:
                return optimize_animated_gif(input_path)

            # Convert to RGBA for processing
            if img.mode != 'RGBA':
                img = img.convert('RGBA')

            # Remove background
            print(f"  Removing background...")
            img = remove_background(img)

            # Resize to fit within 128x128 while maintaining aspect ratio
            img.thumbnail(MAX_DIMENSIONS, Image.Resampling.LANCZOS)

            # Create output path (always PNG for transparency)
            output_path = OUTPUT_FOLDER / f"{input_path.stem}_emoji.png"

            # Save with compression
            img.save(output_path, format='PNG', optimize=True)

            # If too large, try reducing colors
            if output_path.stat().st_size > MAX_SIZE_BYTES:
                img_quantized = img.quantize(colors=256, method=Image.Mediancut, dither=Image.Dither.FLOYDSTEINBERG)
                img_quantized.save(output_path, format='PNG', optimize=True)

            file_size = output_path.stat().st_size
            print(f"  Saved: {output_path.name} ({file_size / 1024:.1f}KB)")
            return output_path

    except Exception as e:
        print(f"  Error processing {input_path.name}: {e}")
        return None


def optimize_animated_gif(input_path: Path) -> Optional[Path]:
    """Optimize an animated GIF for Discord (background removal on each frame)."""
    try:
        output_path = OUTPUT_FOLDER / f"{input_path.stem}_emoji.gif"
        print(f"  Processing animated GIF...")

        with Image.open(input_path) as img:
            frames = []
            durations = []

            frame_count = 0
            try:
                while True:
                    frame_count += 1
                    print(f"  Processing frame {frame_count}...")

                    # Get frame and convert to RGBA
                    frame = img.copy().convert('RGBA')

                    # Remove background from frame
                    frame = remove_background(frame)

                    # Resize frame
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
                    optimize=True,
                    disposal=2  # Clear frame before rendering next
                )

                # If still too large, reduce frames
                if output_path.stat().st_size > MAX_SIZE_BYTES:
                    reduced_frames = frames[::2]
                    reduced_durations = [d * 2 for d in durations[::2]]

                    reduced_frames[0].save(
                        output_path,
                        save_all=True,
                        append_images=reduced_frames[1:],
                        duration=reduced_durations,
                        loop=img.info.get('loop', 0),
                        optimize=True,
                        disposal=2
                    )

                file_size = output_path.stat().st_size
                print(f"  Saved: {output_path.name} ({file_size / 1024:.1f}KB, {len(frames)} frames)")
                return output_path

    except Exception as e:
        print(f"  Error processing animated GIF {input_path.name}: {e}")
        return None


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
    print("Features: Background removal + Resize + Compress")
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
