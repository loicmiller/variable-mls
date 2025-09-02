###############################################################################
# Imports

from decimal import Decimal
from bitcoinrpc.authproxy import AuthServiceProxy
from bcolors import bcolors
import time
import json
from datetime import datetime
import os
import sys
import socket
import glob
import errno
import sqlite3


###############################################################################
# Configurations

# RPC
RPC_USER = "miller"          # RPC username for Bitcoin node
RPC_PASSWORD = "bitcoin"     # RPC password for Bitcoin node
RPC_PORT = 8332              # RPC port for Bitcoin node
RPC_HOST = "127.0.0.1"       # RPC host address

# Snapshot and data storage
END_HEIGHT = 865043          # Final block height to process
DATA_FOLDER = "data/"        # Folder to store snapshot and database files
DB_FILE = "utxos.db"         # SQLite database filename

# Batch processing
BATCH_SIZE = 100             # Number of blocks to process per batch

# Retry logic
MAX_RETRIES = 3              # Maximum number of RPC retry attempts
RETRY_DELAY = 5              # Delay (seconds) between RPC retries

# Pickle chunking
CHUNK_SIZE = 5_000_000       # UTXO chunk size for pickling (for large sets)


###############################################################################
# UTXO utilities

def estimate_utxo_entry_size(script_len_bytes):
    """
    Estimate the serialized size of a UTXO entry in bytes.

    Args:
    - script_len_bytes (int): Length of the locking script in bytes.

    Returns:
    - size (int): Estimated size of the UTXO entry in bytes.

    Notes:
    - The estimate includes txid (32), vout (4), value (8),
      scriptPubKey (variable), and metadata (~4).
    """
    return 32 + 4 + 8 + script_len_bytes + 4


def format_snapshot_info(height, utxo_count, size_bytes):
    """
    Format a snapshot summary string for command-line output.

    Args:
    - height (int): Current block height.
    - utxo_count (int): Number of UTXOs in the snapshot.
    - size_bytes (int): Estimated size in bytes.

    Returns:
    - str: Colored terminal output.
    """
    size_kb = size_bytes / 1024
    return (
        bcolors.OKCYAN +
        f"[Block {height:6}]  UTXOs: {utxo_count:9,}  Estimated size: {size_kb:10,.2f} KB" +
        bcolors.ENDC
    )


def robust_batch_call(rpc, batch):
    """
    Execute a batch RPC call with automatic retries on failure.

    Args:
    - rpc (AuthServiceProxy): Active JSON-RPC connection to a Bitcoin node.
    - batch (list): List of RPC method calls with arguments (e.g. [["getblockhash", 100]]).

    Returns:
    - result (list): Results of the batch RPC call.

    Raises:
    - TimeoutError: If all retry attempts fail.
    - OSError: Propagated if an unrecoverable socket error occurs.

    Notes:
    - Retries up to MAX_RETRIES times on common transient errors
      (timeouts, broken pipes).
    - Waits RETRY_DELAY seconds between retries.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return rpc.batch_(batch)
        except (socket.timeout, TimeoutError, BrokenPipeError) as e:
            print(bcolors.WARNING + f"[Attempt {attempt}/{MAX_RETRIES}] RPC error: {e} — retrying in {RETRY_DELAY}s..." + bcolors.ENDC)
            time.sleep(RETRY_DELAY)
        except OSError as e:
            if e.errno == errno.EPIPE:
                print(bcolors.WARNING + f"[Attempt {attempt}/{MAX_RETRIES}] Broken pipe — retrying in {RETRY_DELAY}s..." + bcolors.ENDC)
                time.sleep(RETRY_DELAY)
            else:
                raise
    raise TimeoutError("RPC batch failed after maximum retries")



###############################################################################
# Data handling

def init_db(db_filename=None):
    """
    Initialize a SQLite database for storing UTXOs.

    Args:
    - db_filename (str, optional): Custom database filename. If None, uses default DB_FILE.

    Returns:
    - conn (sqlite3.Connection): Database connection object.

    Notes:
    - Creates a table `utxos` if it does not exist.
    - Schema:
        txid TEXT, vout INTEGER, value_sats INTEGER, script_len INTEGER
      with (txid, vout) as the primary key.
    - Data is stored in DATA_FOLDER with the specified filename.
    """
    if db_filename is None:
        db_filename = DB_FILE
    
    conn = sqlite3.connect(DATA_FOLDER + db_filename)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS utxos (
            txid TEXT NOT NULL,
            vout INTEGER NOT NULL,
            value_sats INTEGER NOT NULL,
            script_len INTEGER NOT NULL,
            PRIMARY KEY (txid, vout)
        )
    """)
    conn.commit()
    return conn


def load_last_snapshot():
    """
    Load the most recent UTXO snapshot data from JSON files.

    Returns:
    - Tuple or None: If found, returns (heights, utxo_counts, estimated_sizes, last_height).
                     If no valid snapshot found, returns None.

    Notes:
    - Searches for JSON files matching pattern "*-utxo-snapshot-up-to-*.json" in DATA_FOLDER.
    - Files are sorted in reverse order to find the most recent snapshot first.
    - Extracts the block height from the filename to determine resume point.
    """
    json_snapshots = sorted(glob.glob(f"{DATA_FOLDER}*-utxo-snapshot-up-to-*.json"), reverse=True) # Most recent first
    for json_file in json_snapshots: # Find the most recent valid snapshot
        with open(json_file, "r") as f:
            data = json.load(f)
        
        last_height = int(json_file.split("-up-to-")[1].split("-")[0])

        # Check for corresponding database file
        db_file = json_file.replace(".json", ".db")
        if not os.path.exists(db_file):
            print(bcolors.WARNING + f"Database file {db_file} not found, skipping..." + bcolors.ENDC)
            continue

        print(bcolors.WARNING + f"\nResuming from height {last_height} using {json_file} and {db_file}" + bcolors.ENDC)
        return (
            data["height"],
            data["utxo_count"],
            data["estimated_size_bytes"],
            last_height,
            db_file
        )

    print(bcolors.FAIL + "No valid snapshot found." + bcolors.ENDC)
    return None


def dump_data(heights, utxo_counts, estimated_sizes, dump_height, conn=None, message=""):
    """
    Dump UTXO snapshot data to a JSON file.

    Args:
    - heights (list): List of block heights.
    - utxo_counts (list): Number of UTXOs at each height.
    - estimated_sizes (list): Estimated snapshot sizes at each height (bytes).
    - dump_height (int): The height up to which data is dumped.
    - conn (sqlite3.Connection, optional): Database connection to backup.
    - message (str, optional): Optional suffix for filenames (e.g. "interrupted").

    Returns:
    - snapshot_prefix (str): The prefix used for the JSON filename.
    """
    os.makedirs(DATA_FOLDER, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")

    if message:
        snapshot_prefix = f"{DATA_FOLDER}{timestamp}-utxo-snapshot-up-to-{dump_height}-{message}"
    else:
        snapshot_prefix = f"{DATA_FOLDER}{timestamp}-utxo-snapshot-up-to-{dump_height}"

    # Save JSON data
    data = {
        "height": heights,
        "utxo_count": utxo_counts,
        "estimated_size_bytes": estimated_sizes
    }

    with open(f"{snapshot_prefix}.json", "w") as f:
        json.dump(data, f)

    # Save database backup if connection provided
    if conn:
        backup_db = sqlite3.connect(f"{snapshot_prefix}.db")
        conn.backup(backup_db)
        backup_db.close()

    print(bcolors.OKGREEN + f"\nData + UTXO set saved to:\n{snapshot_prefix}.json and .db" + bcolors.ENDC)
    return snapshot_prefix


###############################################################################
# Main

def main():
    """
    Main function to estimate UTXO snapshot sizes by processing Bitcoin blocks.

    Returns:
    - None

    Notes:
    - Connects to a Bitcoin RPC node and processes blocks from start_height to END_HEIGHT.
    - Maintains a SQLite database of UTXOs, adding new outputs and removing spent ones.
    - Calculates running estimates of UTXO set size in bytes.
    - Supports resuming from previous snapshots by loading the most recent checkpoint.
    - Creates periodic checkpoints every 50,000 blocks and handles interruptions gracefully.
    - Uses batch RPC calls for improved performance when fetching block data.
    - Outputs progress information with colored terminal formatting.
    """
    print(bcolors.HEADER + "Starting UTXO snapshot estimation with batch RPC..." + bcolors.ENDC)

    # Setup RPC connection
    rpc_url = f"http://{RPC_USER}:{RPC_PASSWORD}@{RPC_HOST}:{RPC_PORT}"
    rpc = AuthServiceProxy(rpc_url, timeout=120)

    # Try to resume from last snapshot
    resume_data = load_last_snapshot()
    if resume_data:
        heights, utxo_counts, estimated_sizes, start_height, db_file = resume_data
        start_height += 1 # Resume from next block
        current_est_size = estimated_sizes[-1] if estimated_sizes else 0
        conn = sqlite3.connect(db_file) # Load existing database
        c = conn.cursor()
    else: # Start fresh
        print(bcolors.HEADER + "No previous snapshot found. Starting from genesis block..." + bcolors.ENDC)
        heights = []
        utxo_counts = []
        estimated_sizes = []
        start_height = 0
        current_est_size = 0 # Running total of UTXO size
        conn = init_db() # Initialize database connection and cursor
        c = conn.cursor()

    try:
        for batch_start in range(start_height, END_HEIGHT + 1, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, END_HEIGHT + 1)
            current_batch_range = list(range(batch_start, batch_end))

            # Fetch block hashes in batch
            blockhash_batch = [["getblockhash", h] for h in current_batch_range]
            block_hashes = robust_batch_call(rpc, blockhash_batch)

            # Fetch blocks in batch
            getblock_batch = [["getblock", bh, 2] for bh in block_hashes]
            blocks = robust_batch_call(rpc, getblock_batch)

            # Process each block in the batch
            for height, block in zip(current_batch_range, blocks):
                for tx in block["tx"]:
                    txid = tx["txid"]

                    # Remove spent outputs
                    for vin in tx.get("vin", []):
                        if "coinbase" in vin: # Skip coinbase transactions (they don't spend existing UTXOs)
                            continue

                        c.execute('SELECT script_len FROM utxos WHERE txid=? AND vout=?', (vin["txid"], vin["vout"]))
                        row = c.fetchone()
                        if row:
                            script_len = row[0]
                            current_est_size -= estimate_utxo_entry_size(script_len)
                            c.execute('DELETE FROM utxos WHERE txid=? AND vout=?', (vin["txid"], vin["vout"]))

                    # Add new outputs
                    for vout in tx.get("vout", []):
                        value_sats = int(vout["value"] * Decimal("1e8"))
                        script_len = len(vout.get("scriptPubKey", {}).get("hex", "")) // 2
                        current_est_size += estimate_utxo_entry_size(script_len)
                        c.execute('INSERT OR REPLACE INTO utxos (txid, vout, value_sats, script_len) VALUES (?, ?, ?, ?)', (txid, vout["n"], value_sats, script_len))

                c.execute("SELECT COUNT(*) FROM utxos")
                count = c.fetchone()[0]
                est_size = current_est_size

                heights.append(height)
                utxo_counts.append(count)
                estimated_sizes.append(est_size)

                print(format_snapshot_info(height, count, est_size))

                # Periodic data dump every 50,000 blocks
                if height > 0 and height % 50_000 == 0:
                    conn.commit()  # Ensure all changes are committed before backup
                    dump_data(heights, utxo_counts, estimated_sizes, height, conn=conn, message=f"checkpoint")

    except KeyboardInterrupt:
        print(bcolors.WARNING + "\nInterrupted by user — dumping data..." + bcolors.ENDC)
        conn.commit()  # Ensure all changes are committed before backup
        dump_data(heights, utxo_counts, estimated_sizes, heights[-1] if heights else 0, conn=conn, message="interrupted")
        sys.exit(1)

    except Exception as e:
        print(bcolors.FAIL + f"\nUnexpected error: {str(e)} — dumping data..." + bcolors.ENDC)
        conn.commit()  # Ensure all changes are committed before backup
        dump_data(heights, utxo_counts, estimated_sizes, heights[-1] if heights else 0, conn=conn, message="error")
        raise

    conn.commit()
    conn.close()

    dump_data(heights, utxo_counts, estimated_sizes, heights[-1] if heights else 0, conn=conn, message="completed")
    print(bcolors.OKGREEN + "\nEstimation completed successfully." + bcolors.ENDC)



###############################################################################
# Entrypoint

if __name__ == "__main__":
    main()