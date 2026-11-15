"""Create a multi-size Windows .ico from the approved LUMAVUN artwork."""
from pathlib import Path
from PIL import Image

root = Path(__file__).resolve().parents[1]
source = root / "assets" / "lumavun.png"
destination = root / "assets" / "lumavun.ico"
if not source.is_file():
    raise SystemExit("Missing LUMAVUN premium icon source: " + str(source))

with Image.open(source) as picture:
    image = picture.convert("RGBA")
    # Use Lanczos filtering; maintain the brand design at each Windows icon size.
    image.save(destination, format="ICO", sizes=[
        (16,16),(24,24),(32,32),(48,48),(64,64)
    ])
print("Created", destination, destination.stat().st_size, "bytes")
