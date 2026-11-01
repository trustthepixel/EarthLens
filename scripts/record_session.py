"""Export the latest event records and their image artifacts for offline replay."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def record(count=40, events_path='events.jsonl', data_dir='events_data', output_dir='demo_session', max_bytes=3 * 1024 * 1024):
    source = Path(events_path)
    rows = []
    if source.exists():
        for line in source.read_text(encoding='utf-8').splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    rows = rows[-count:]
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    output_rows = []
    for row in rows:
        event_id = row.get('event_id')
        if event_id is not None:
            for suffix in ('rgb', 'heat'):
                name = f'{event_id}_{suffix}.png'
                image = Path(data_dir) / name
                if image.is_file():
                    shutil.copy2(image, destination / name)
            row = dict(row)
            row['rgb_image'] = f'{event_id}_rgb.png' if (destination / f'{event_id}_rgb.png').exists() else None
            row['heat_image'] = f'{event_id}_heat.png' if (destination / f'{event_id}_heat.png').exists() else None
        output_rows.append(row)
    (destination / 'events.json').write_text(json.dumps({'events': output_rows}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    size = sum(item.stat().st_size for item in destination.iterdir() if item.is_file())
    if size > max_bytes:
        raise ValueError(f'Demo session is {size} bytes, exceeding the {max_bytes}-byte limit.')
    return len(output_rows), size


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count', type=int, default=40)
    parser.add_argument('--events', default='events.jsonl')
    parser.add_argument('--data-dir', default='events_data')
    parser.add_argument('--output', default='demo_session')
    args = parser.parse_args(argv)
    if args.count < 1:
        parser.error('count must be positive')
    count, size = record(args.count, args.events, args.data_dir, args.output)
    print(f'Exported {count} events ({size} bytes) to {args.output}.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
