###############################################################################
# Imports

import math
import random
from typing import List, Dict



###############################################################################
# Core statistics for geometric chains

def sample_geometric_level(p: float) -> int:
    """
    Sample μ ~ Geometric(p) with P[μ = k] = (1 - p) * p^k.

    Args:
        p (float): Geometric parameter.

    Returns:
        int: Sampled level μ >= 0.
    """
    u = random.random()
    return int(math.log(1 - u) / math.log(p))

def geometric_log_likelihood(levels: List[int], p: float) -> float:
    """
    Compute the log-likelihood of a level sequence under a geometric distribution.

    P[μ = k] = (1 - p) * p^k

    Args:
        levels (List[int]): Block levels.
        p (float): Geometric parameter.

    Returns:
        float: Log-likelihood.
    """
    n = len(levels)
    return n * math.log(1 - p) + sum(levels) * math.log(p)

def geometric_z_score(levels: List[int], p: float) -> float:
    """
    Compute the Z-score of the sum of levels under a geometric distribution.

    Args:
        levels (List[int]): Block levels.
        p (float): Geometric parameter.

    Returns:
        float: Z-score.
    """
    n = len(levels)
    mean = p / (1 - p)
    var = p / (1 - p) ** 2
    S = sum(levels)
    return (S - n * mean) / math.sqrt(n * var)

def geometric_empirical_p_value(levels: List[int], p: float, trials: int = 10_000, seed: int = None) -> float:
    """
    Estimate the empirical p-value via Monte Carlo simulation.

    Args:
        levels (List[int]): Observed block levels.
        p (float): Geometric parameter.
        trials (int): Number of Monte Carlo trials.
        seed (int, optional): RNG seed.

    Returns:
        float: Empirical p-value.
    """
    if seed is not None:
        random.seed(seed)

    n = len(levels)
    observed_sum = sum(levels)

    count = 0
    for _ in range(trials):
        sim = [sample_geometric_level(p) for _ in range(n)]
        if sum(sim) >= observed_sum:
            count += 1

    return count / trials



###############################################################################
# Intelligent comparison and interpretation

def rarity_report(levels: List[int], p: float, trials: int = 10_000, seed: int = None) -> Dict[str, float | str]:
    """
    Compute and interpret multiple rarity measures for a geometric chain.

    Args:
        levels (List[int]): Block levels.
        p (float): Geometric parameter.
        trials (int): Monte Carlo trials for p-value.
        seed (int, optional): RNG seed.

    Returns:
        Dict[str, float | str]: Rarity metrics and interpretation.
    """
    ll = geometric_log_likelihood(levels, p)
    z = geometric_z_score(levels, p)
    pval = geometric_empirical_p_value(levels, p, trials, seed)

    # Interpretation (robust, paper-friendly)
    if abs(z) < 1:
        verdict = "typical"
    elif abs(z) < 2:
        verdict = "mildly atypical"
    elif abs(z) < 3:
        verdict = "rare"
    else:
        verdict = "extremely rare"

    # Cross-check consistency
    consistency = (
        "consistent"
        if (pval < 0.05) == (abs(z) > 1.96)
        else "borderline"
    )

    return {
        "log_likelihood": ll,
        "log_likelihood_per_block": ll / len(levels),
        "z_score": z,
        "empirical_p_value": pval,
        "verdict": verdict,
        "consistency": consistency,
    }

def print_rarity_report(report: dict) -> None:
    """
    Print an interpretative rarity report to the terminal.

    Args:
        report (dict): Output of rarity_report().
    
    Returns:
        A report is printed to the terminal.
    """
    ll = report["log_likelihood"]
    ll_pb = report["log_likelihood_per_block"]
    z = report["z_score"]
    pval = report["empirical_p_value"]
    verdict = report["verdict"]
    consistency = report["consistency"]

    print("\n" + "=" * 72)
    print("Rarity analysis of the generated chain")
    print("=" * 72)

    # ------------------------------------------------------------------
    # Log-likelihood
    # ------------------------------------------------------------------
    print("\nLog-likelihood:")
    print(f"  Total log-likelihood           : {ll:.3f}")
    print(f"  Log-likelihood per block       : {ll_pb:.3f}")
    print("  Interpretation:")
    print("    This measures how plausible the *exact sequence* of block levels")
    print("    is under the geometric model. The per-block value is stable and")
    print("    allows comparison across chains of different lengths.")

    # ------------------------------------------------------------------
    # Z-score
    # ------------------------------------------------------------------
    print("\nZ-score:")
    print(f"  Z = {z:.3f}")
    print("  Interpretation:")
    if abs(z) < 1:
        print("    The chain is extremely close to the expected average behavior.")
    elif abs(z) < 2:
        print("    The chain shows mild deviation from the average.")
    elif abs(z) < 3:
        print("    The chain is statistically rare (≈ 95% confidence).")
    else:
        print("    The chain is extremely rare (strong deviation from expectation).")

    # ------------------------------------------------------------------
    # Empirical p-value
    # ------------------------------------------------------------------
    print("\nEmpirical p-value (Monte Carlo):")
    print(f"  p-value ≈ {pval:.4f}")
    print("  Interpretation:")
    if pval > 0.2:
        print("    Such a chain is very common under the geometric model.")
    elif pval > 0.05:
        print("    Such a chain is somewhat uncommon, but not rare.")
    elif pval > 0.01:
        print("    Such a chain is rare.")
    else:
        print("    Such a chain lies in the extreme tail of the distribution.")

    # ------------------------------------------------------------------
    # Final verdict
    # ------------------------------------------------------------------
    print("\nFinal verdict:")
    print(f"  Classification                : {verdict}")
    print(f"  Metric consistency            : {consistency}")

    if verdict == "typical":
        print("  Overall interpretation:")
        print("    The chain is statistically indistinguishable from a typical")
        print("    realization of the geometric model.")
    else:
        print("  Overall interpretation:")
        print("    The chain exhibits statistically significant deviation from")
        print("    typical geometric behavior and may be considered rare.")

    print("=" * 72 + "\n")
