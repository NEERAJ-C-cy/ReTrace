import io, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import imagehash
from PIL import Image, ImageOps


orig = Image.open(sys.argv[1]).convert("RGB")

def jpeg(img, q):
  buf = io.BytesIO(); img.save(buf, "JPEG", quality=q); buf.seek(0)
  return Image.open(buf).convert("RGB")

w, h = orig.size
variants = {
"resized 50%": orig.resize((w // 2, h // 2)),
"JPEG quality 30": jpeg(orig, 30),
"cropped 10% edges": orig.crop((w // 10, h // 10, w - w // 10, h - h // 
10)),
 "mirrored": ImageOps.mirror(orig),
}
for name, v in variants.items():
  dp = imagehash.phash(orig) - imagehash.phash(v)
  dd = imagehash.dhash(orig) - imagehash.dhash(v)
  print(f"{name:20s} pHash distance {dp:2d}   dHash distance {dd:2d}")