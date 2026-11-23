import numpy as np
from scipy.stats import binomtest

from vmls.gamma import ROUND_SECONDS
from vmls.gamma_bound import DAY, TARGET_SPACING, Chain, bracket, cells, ratio_bounds, simulate_chain


def test_interval_is_the_exact_binomial_one():
    # With equal exposures, the ratio is pi / (1 - pi).
    for n_a, n_b, alpha in ((10, 30, 0.05), (144, 100, 0.001), (1, 0, 0.05), (0, 7, 0.05), (2000, 2100, 1e-6)):
        ci = binomtest(n_a, n_a + n_b).proportion_ci(1 - alpha, method='exact')
        _, low, high = ratio_bounds(np.array([n_a]), np.array([n_b]), np.array([1.0]), np.array([1.0]), alpha)
        assert abs(low[0] - ci.low / (1 - ci.low)) < 1e-6 * (1 + low[0])
        if n_b > 0:
            assert abs(high[0] - ci.high / (1 - ci.high)) < 1e-6 * high[0]


def test_exposure_by_hand():
    # One day at difficulty 2, then one at difficulty 4.
    chain = Chain(np.array([0.0, 2.0 * DAY]), np.array([0.0, float(DAY)]), np.array([2.0, 4.0]))
    start = chain.exposure(np.array([0.0]))[0]
    assert abs(chain.exposure(np.array([2.0 * DAY]))[0] - start - (DAY / 2 + DAY / 4)) < 1e-6
    assert abs(chain.exposure(np.array([1.5 * DAY]))[0] - start - (DAY / 2 + DAY / 8)) < 1e-6
    # The same hashrate gives half the blocks at twice the difficulty: the ratio is 1.
    point, _, _ = ratio_bounds(np.array([100]), np.array([50]), np.array([DAY / 2.0]), np.array([DAY / 4.0]), 0.05)
    assert abs(point[0] - 1) < 1e-12


def test_exposure_keeps_its_precision_over_the_whole_chain():
    # A day at the difficulty of 2026, after years at difficulty 1.
    day_2026 = 1.5e14
    chain = Chain(np.array([0.0, 400.0 * DAY]), np.array([0.0, 300.0 * DAY]), np.array([1.0, day_2026]))
    measured = np.diff(chain.exposure(np.array([350.0 * DAY, 351.0 * DAY])))[0]
    assert abs(measured / (DAY / day_2026) - 1) < 1e-9


def test_pairs_are_those_a_brute_force_finds():
    w_seconds, s_rounds = DAY, int(5 * DAY / ROUND_SECONDS)
    times = np.sort(np.random.default_rng(0).uniform(0, 40 * DAY, 5000))
    chain = Chain(times, np.array([times[0]]), np.array([1.0]))
    positions, _, _ = cells(chain, w_seconds)
    brute = sum(1 for i in range(len(positions)) for j in range(i + 1, len(positions))
                if positions[j] >= positions[i] + w_seconds - 1e-6
                and positions[j] + w_seconds - positions[i] <= s_rounds * ROUND_SECONDS + 1e-6)
    assert bracket(chain, s_rounds, 1)['pairs'] == brute


def test_simulated_hashrate_comes_out():
    chain, _, grid, _, weighted = simulate_chain('dip-14', 150, 1)
    positions, n, e = cells(chain, 3 * DAY)
    estimate = n / e * TARGET_SPACING
    truth = (np.interp(positions + 3 * DAY, grid, weighted) - np.interp(positions, grid, weighted)) / e
    assert np.median(np.abs(estimate / truth - 1)) < 0.05


def test_interval_holds_a_known_drop():
    chain, _, grid, _, weighted = simulate_chain('dip-7', 150, 2)
    result = bracket(chain, 72_000, 3)
    assert result['lower'] <= 2.0 <= result['upper']
