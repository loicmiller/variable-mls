"""NIPoPoWs with variable mining difficulty, measured on the Bitcoin header chain.

Modules:
    chain: headers, blocks, difficulties and levels (real and blind).
    nipopow: the prover (Dissolve, Compress) and the verifier rules.
    synthetic: synthetic chains and competing proofs.
    sizes: the byte model of headers, proofs and Merkle paths.
    cost: the hashing work of a prover and a verifier.
    gamma: the hashrate fluctuation gamma, as the gamma notebook estimates it.
    gamma_bound: gamma(s, w), a worst case with exact confidence intervals.
    node: reading headers from a Bitcoin Core node.
    style: the look of the figures.
"""

__version__ = '2.0.0'
