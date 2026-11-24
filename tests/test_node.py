"""RPC credentials and header exports, without a node (vmls.node)."""

import pytest

from vmls.node import credentials, extends, save_headers


def test_cookie_comes_first(tmp_path):
    (tmp_path / '.cookie').write_text('__cookie__:secret\n')
    config = tmp_path / 'rpc.env'
    config.write_text('VMLS_RPC_USER=alice\nVMLS_RPC_PASSWORD=other\n')
    assert credentials(tmp_path, config, {}) == ('__cookie__', 'secret')


def test_config_file_then_environment(tmp_path):
    config = tmp_path / 'rpc.env'
    config.write_text('# a comment\nVMLS_RPC_USER=alice\nVMLS_RPC_PASSWORD=from-file\n')
    assert credentials(tmp_path, config, {'VMLS_RPC_PASSWORD': 'from-env'}) == ('alice', 'from-file')
    assert credentials(None, tmp_path / 'missing', {'VMLS_RPC_USER': 'bob', 'VMLS_RPC_PASSWORD': 'x'}) == ('bob', 'x')


def test_no_credentials(tmp_path):
    with pytest.raises(RuntimeError):
        credentials(tmp_path, tmp_path / 'missing', {})


def test_extends():
    a = [{'hash': 'a', 'bits': '1', 'time': 1}]
    b = a + [{'hash': 'b', 'bits': '1', 'time': 2}]
    assert extends(b, a)
    assert not extends(a, b)
    assert not extends([{'hash': 'x', 'bits': '1', 'time': 1}], a)


def test_save_never_overwrites(tmp_path):
    headers = [{'hash': 'a', 'bits': '1', 'time': 1}] * 3
    path = save_headers(headers, tmp_path)
    assert path.name == 'headers-up-to-2.json'
    with pytest.raises(FileExistsError):
        save_headers(headers, tmp_path)


def test_block_files_are_read_with_their_xor_key(tmp_path):
    import hashlib

    import numpy as np

    from vmls.node import MAGIC, block_sizes
    blocks_dir = tmp_path / 'blocks'
    blocks_dir.mkdir()
    key = bytes(range(1, 9))
    headers, records = [], b''
    for i, body in enumerate([b'a' * 120, b'b' * 300, b'c' * 90]):
        header = bytes([i]) * 80
        block = header + body
        headers.append({'hash': hashlib.sha256(hashlib.sha256(header).digest()).digest()[::-1].hex(), 'bits': '1d00ffff',
                        'time': i})
        records += MAGIC + len(block).to_bytes(4, 'little') + block
    records += bytes(64)  # Preallocated zeros at the end of the file.
    (blocks_dir / 'xor.dat').write_bytes(key)
    (blocks_dir / 'blk00000.dat').write_bytes(bytes(b ^ key[i % 8] for i, b in enumerate(records)))
    headers.append({'hash': '00' * 32, 'bits': '1d00ffff', 'time': 3})  # Not in the files.
    assert block_sizes(tmp_path, headers, threads=2).tolist() == [200, 380, 170, -1]
