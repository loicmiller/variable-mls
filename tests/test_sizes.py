from vmls.chain import sha256
from vmls.sizes import draft_leaves, header_size, merkle_path, merkle_root, n_levels, proof_size, spv_size

HEIGHT, k = 865_042, 323


def test_header_sizes():
    assert n_levels(HEIGHT) == 20
    assert header_size('ccs', HEIGHT, k) == 80 + 32 * 20
    assert header_size('ccs-merkle', HEIGHT, k) == 112
    assert header_size('draft', HEIGHT, k) == 80 + 28 + 32 * 323 + 128 * 20 == 13_004
    assert header_size('draft-merkle', HEIGHT, k) == 140


def test_merkle_paths():
    assert draft_leaves(HEIGHT, k) == 403
    assert merkle_path(403) == 9 * 32
    assert merkle_path(1) == 32


def test_proof_size_counts_paths_only_where_needed():
    D, X, Omega = [10, 20], [30, 31], [32]
    assert proof_size('draft-merkle', D, X, Omega, k) == 5 * 140 + 2 * 2 * (32 + merkle_path(draft_leaves(10, k))) + 2 * (32 + merkle_path(draft_leaves(30, k)))
    assert spv_size(HEIGHT) == 80 * 865_043


def test_merkle_root():
    a, b, c = b'a' * 32, b'b' * 32, b'c' * 32
    assert merkle_root([a]) == a
    assert merkle_root([a, b]) == sha256(a + b)
    assert merkle_root([a, b, c]) == sha256(sha256(a + b) + sha256(c))
