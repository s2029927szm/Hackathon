import json
import re
import shutil
from pathlib import Path
root = Path.cwd()
dishes = json.loads((root / 'dishes_50.json').read_text(encoding='utf-8'))
files = {}
for path in (root / 'FoodPic').iterdir():
    if not path.is_file():
        continue
    match = re.fullmatch(r'(\d+)\.\s*(.+)', path.stem)
    if not match or path.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp'}:
        raise ValueError(f'Unexpected image: {path.name}')
    did = int(match[1])
    if did in files:
        raise ValueError(f'Duplicate image ID: {did}')
    files[did] = (path, match[2].strip())
assert set(files) == {d['id'] for d in dishes}, 'Image IDs must match the 50 dish IDs'
for dish in dishes:
    assert files[dish['id']][1] == dish['name'], (dish['id'], files[dish['id']][1], dish['name'])
out = root / 'FoodCompass-Web/assets/dishes'
out.mkdir(exist_ok=True)
manifest = []
for dish in dishes:
    source, _ = files[dish['id']]
    filename = f"dish-{dish['id']:02d}{source.suffix.lower()}"
    shutil.copy2(source, out / filename)
    manifest.append({'id':dish['id'], 'name':dish['name'], 'image':'dishes/' + filename, 'source':source.name})
(out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
p = root / 'app(1).py'
s = p.read_text(encoding='utf-8')
start = s.index('# Existing local artwork')
end = s.index('SESSION_STORE:', start)
s = s[:start] + '''# Bind supplied artwork by both dish ID and name to prevent accidental swaps.
with open(BASE_DIR / "FoodCompass-Web" / "assets" / "dishes" / "manifest.json", encoding="utf-8") as f:
    image_manifest = json.load(f)
DISH_IMAGES = {entry["id"]: entry for entry in image_manifest}
if len(DISH_IMAGES) != len(image_manifest) or set(DISH_IMAGES) != {d["id"] for d in ALL_DISHES}:
    raise ValueError("Dish image manifest IDs do not match the dataset")
for dish in ALL_DISHES:
    entry = DISH_IMAGES[dish["id"]]
    if entry["name"] != dish["name"]:
        raise ValueError(f"Dish image name mismatch for ID {dish['id']}")
    if not (BASE_DIR / "FoodCompass-Web" / "assets" / entry["image"]).is_file():
        raise ValueError(f"Missing image for dish {dish['id']}")
    dish["image"] = entry["image"]
    dish["image_url"] = "/assets/" + entry["image"]
    dish["image_kind"] = "dish_illustration"
    dish["image_note"] = "Supplied artwork for " + dish["name"]

''' + s[end:]
p.write_text(s, encoding='utf-8')
p = root / 'verify_integration.py'
s = p.read_text(encoding='utf-8').replace("assert len({d['image'] for d in catalog}) > 8", "assert len({d['image'] for d in catalog}) == 50\nassert all(d['image_kind'] == 'dish_illustration' for d in catalog)").replace("== 'food-1.jpg'", "== 'dishes/dish-01.png'").replace("== 'food-0.jpg'", "== 'dishes/dish-31.png'")
p.write_text(s, encoding='utf-8')
print('Matched all 50 IDs and names; copied artwork and wrote manifest.')
