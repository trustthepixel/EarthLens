"""Export preset place centers from the prepared pack for the Kali proxy."""

from __future__ import annotations

import json
from pathlib import Path

from tp.pack import PRESET_PLACES


def export(index_path='unseen_pack/index.json', output_path='attacker/places.json'):
    index = json.loads(Path(index_path).read_text(encoding='utf-8'))
    places = {row['place']: {'lon': float(row['center'][0]), 'lat': float(row['center'][1])}
              for row in index.get('places', []) if row.get('place') and row.get('center')}
    for name, (lon, lat, _foreign) in PRESET_PLACES.items():
        places.setdefault(name, {'lon': lon, 'lat': lat})
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(places, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
    return places


def main():
    export()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
