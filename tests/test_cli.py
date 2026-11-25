"""Each subcommand on a tiny synthetic chain: it runs and writes what it says (vmls.cli)."""

import json
import random

import numpy as np
import pytest

from vmls.chain import GENESIS_TARGET
from vmls.cli import main

START = 1577836800  # 2020-01-01: the recent period of kstar and gamma starts here.


@pytest.fixture(scope='module')
def headers_file(tmp_path_factory):
    """Six epochs of headers at the genesis target, ten minutes apart, with hashes below the target."""
    rng = random.Random(1)
    headers = [{'hash': f'{rng.randrange(1, GENESIS_TARGET):064x}', 'bits': '1d00ffff', 'time': START + 600 * i}
               for i in range(6 * 2016)]
    path = tmp_path_factory.mktemp('headers') / 'headers.json'
    path.write_text(json.dumps(headers))
    return path


def result(path):
    return json.loads(path.read_text())['result']


def test_replay_build_time_sections_and_figures(headers_file, tmp_path):
    out = tmp_path / 'results'
    for construction in ('ccs2025', 'ours'):
        main(['replay', '--construction', construction, '--headers', str(headers_file), '-K', '8', '-k', '6', '-chi', '40',
              '--out-dir', str(out)])
    main(['build-time', '--headers', str(headers_file), '-K', '8', '-k', '6', '--step', '4000', '--repetitions', '1',
          '--out', str(out / 'build-time.json')])
    main(['sections', '--headers', str(headers_file), '-K', '8', '-k', '6', '--step', '4000',
          '--out', str(out / 'sections.json')])
    replays = sorted(out.glob('replay-*.json'))
    assert [p.name for p in replays] == ['replay-ccs2025-up-to-12095-K-8-k-6.json', 'replay-ours-up-to-12095-K-8-k-6.json']
    samples = result(replays[1])
    assert samples['verifier'] and all(v['winner'] == 1 for v in samples['verifier'] if v['fork'] == 'tip')
    assert {r['construction'] for r in result(out / 'build-time.json')} == {'ccs2025', 'ours'}
    main(['figures', '--results', str(out), '--out-dir', str(tmp_path / 'out')])
    names = {p.name for p in (tmp_path / 'out').iterdir()}
    assert {'time.pdf', 'proof-blocks.pdf', 'proof-sections.pdf', 'proof-sections-log.pdf', 'numbers.json'} <= names
    numbers = json.loads((tmp_path / 'out' / 'numbers.json').read_text())
    assert numbers['ours-K8']['proof_blocks'] > 0
    timings = tmp_path / 'timings'  # A replay without the verifier, run alone: its update times replace the first.
    main(['replay', '--construction', 'ours', '--headers', str(headers_file), '-K', '8', '-k', '6', '-chi', '40',
          '--no-verifier', '--out-dir', str(timings)])
    main(['figures', '--results', str(out), '--timings', str(timings), '--out-dir', str(tmp_path / 'out2')])
    merged = json.loads((tmp_path / 'out2' / 'numbers.json').read_text())
    alone = np.load(timings / 'replay-ours-up-to-12095-K-8-k-6.npz')['update_us']
    assert merged['ours-K8']['update_ms_last_epoch'] == pytest.approx(np.median(alone[-2016:]) / 1000)
    assert merged['ours-K8']['verifier_ms_headers'] == numbers['ours-K8']['verifier_ms_headers']


def test_results_are_never_overwritten(headers_file, tmp_path):
    out = tmp_path / 'attack.json'
    main(['attack', '--headers', str(headers_file), '-K', '8', '--out', str(out)])
    with pytest.raises(FileExistsError):
        main(['attack', '--headers', str(headers_file), '-K', '8', '--out', str(out)])
    assert result(out)['K'] == 8


def test_kstar(headers_file, tmp_path):
    main(['kstar', '--headers', str(headers_file), '--out', str(tmp_path / 'kstar.json')])
    k = result(tmp_path / 'kstar.json')
    assert k['levels'][0]['spread_recent'] == 1.0  # One target throughout.
    assert k['epsilon'][0]['adversary_share'] < k['adversary_share_limit'] < 0.5


def test_gamma_classic_recent(headers_file, tmp_path):
    main(['gamma', 'classic', '--headers', str(headers_file), '--since', '2020-01-02', '--out', str(tmp_path / 'g.json')])
    rows = result(tmp_path / 'g.json')['rows']
    assert rows and all(row['s'] > 0 for row in rows)
