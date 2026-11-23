"""Size of the UTXO set at every height, replayed from the full blocks of a Bitcoin Core node.

A NIPoPoW carries the UTXO set its tip commits to, so its size matters as much as the headers. The replay keeps the
unspent outputs in SQLite and estimates the serialized size of each one as txid (32) + vout (4) + value (8) + its
script + about 4 bytes of metadata. It writes a checkpoint (JSON of the series, copy of the database) every few
thousand blocks and resumes from the last one. A full replay takes days and some 80 GB.

    python -m experiments.utxo_snapshot --datadir ~/.bitcoin --end 865042 --out-dir data/utxo
"""

import argparse
import glob
import json
import sqlite3
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from vmls.node import Node

BATCH_SIZE = 100  # Blocks per RPC request.
RETRIES = 3


def entry_size(script_bytes: int) -> int:
    """Estimated serialized size of an unspent output.

    Args:
        script_bytes: Length of its locking script.

    Returns:
        The size in bytes.
    """
    return 32 + 4 + 8 + script_bytes + 4


def checkpoint(out_dir: Path, series: dict, height: int, db: sqlite3.Connection, tag: str) -> Path:
    """Writes the series so far and a copy of the database.

    Args:
        out_dir: The directory.
        series: The lists height, utxo_count and estimated_size_bytes.
        height: Last height processed.
        db: The database.
        tag: 'checkpoint', 'interrupted', 'error' or 'completed'.

    Returns:
        The prefix of the files written.
    """
    db.commit()
    prefix = out_dir / f'{datetime.now():%Y-%m-%d-%H-%M-%S}-utxo-snapshot-up-to-{height}-{tag}'
    with open(prefix.with_suffix('.json'), 'w') as f:
        json.dump(series, f)
    backup = sqlite3.connect(prefix.with_suffix('.db'))
    db.backup(backup)
    backup.close()
    print(f'{prefix}.json and .db written', flush=True)
    return prefix


def resume(out_dir: Path) -> tuple[dict, sqlite3.Connection, int]:
    """Starts from the last checkpoint, or from scratch.

    Args:
        out_dir: The directory of the checkpoints.

    Returns:
        The series, the database and the next height to process.
    """
    for path in sorted(glob.glob(str(out_dir / '*-utxo-snapshot-up-to-*.json')), reverse=True):
        db_path = Path(path).with_suffix('.db')
        if db_path.exists():
            with open(path) as f:
                series = json.load(f)
            print(f'Resuming from {path}')
            return series, sqlite3.connect(db_path), series['height'][-1] + 1
    db = sqlite3.connect(out_dir / 'utxos.db')
    db.execute('CREATE TABLE IF NOT EXISTS utxos (txid TEXT NOT NULL, vout INTEGER NOT NULL, value_sats INTEGER NOT NULL, '
               'script_len INTEGER NOT NULL, PRIMARY KEY (txid, vout))')
    return {'height': [], 'utxo_count': [], 'estimated_size_bytes': []}, db, 0


def blocks(node: Node, heights: list[int]) -> list[dict]:
    """Full blocks with their transactions, retried on transient network errors.

    Args:
        node: The node.
        heights: The heights.

    Returns:
        The blocks, decoded with exact amounts.

    Raises:
        OSError: If every retry fails.
    """
    for attempt in range(1, RETRIES + 1):
        try:
            hashes = node.batch('getblockhash', [[h] for h in heights])
            return node.batch('getblock', [[h, 2] for h in hashes], parse_float=Decimal)
        except OSError as error:
            if attempt == RETRIES:
                raise
            print(f'RPC error ({error}), retry {attempt}/{RETRIES} in 5 s', flush=True)
            time.sleep(5)


def main() -> None:
    """Replays the blocks and writes the size of the UTXO set at each height."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--datadir', default=None, help='Data directory of the node, for its cookie.')
    parser.add_argument('--url', default='http://127.0.0.1:8332', help='URL of the node.')
    parser.add_argument('--end', type=int, required=True, help='Last height to process.')
    parser.add_argument('--checkpoint-every', type=int, default=5_000, help='Blocks between two checkpoints.')
    parser.add_argument('--out-dir', default='data/utxo', help='Directory of the checkpoints.')
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    node = Node(args.url, args.datadir, timeout=120)
    series, db, start = resume(out_dir)
    size = series['estimated_size_bytes'][-1] if series['height'] else 0
    height = start - 1
    try:
        for first in range(start, args.end + 1, BATCH_SIZE):
            heights = list(range(first, min(first + BATCH_SIZE, args.end + 1)))
            for height, block in zip(heights, blocks(node, heights)):
                for tx in block['tx']:
                    for vin in tx.get('vin', []):
                        if 'coinbase' in vin:
                            continue
                        row = db.execute('SELECT script_len FROM utxos WHERE txid=? AND vout=?', (vin['txid'], vin['vout'])).fetchone()
                        if row:
                            size -= entry_size(row[0])
                            db.execute('DELETE FROM utxos WHERE txid=? AND vout=?', (vin['txid'], vin['vout']))
                    for vout in tx.get('vout', []):
                        script = len(vout.get('scriptPubKey', {}).get('hex', '')) // 2
                        size += entry_size(script)
                        db.execute('INSERT OR REPLACE INTO utxos (txid, vout, value_sats, script_len) VALUES (?, ?, ?, ?)',
                                   (tx['txid'], vout['n'], int(vout['value'] * Decimal('1e8')), script))
                series['height'].append(height)
                series['utxo_count'].append(db.execute('SELECT COUNT(*) FROM utxos').fetchone()[0])
                series['estimated_size_bytes'].append(size)
                if height and height % args.checkpoint_every == 0:
                    checkpoint(out_dir, series, height, db, 'checkpoint')
    except KeyboardInterrupt:
        checkpoint(out_dir, series, height, db, 'interrupted')
        raise
    except Exception:
        checkpoint(out_dir, series, height, db, 'error')
        raise
    checkpoint(out_dir, series, height, db, 'completed')
    db.close()


if __name__ == '__main__':
    main()
