"""NIPoPoWs with variable mining difficulty, replayed over the Bitcoin header chain.

Modules:
    chain: blocks, their work and their level under each construction; synthetic chains and forks.
    proof: the prover, Dissolve and Compress.
    encoding: the bytes of each header, and the formula of their length.
    verify: the verifier, its checks and the comparison rules of both constructions.
    measure: the measurements on Bitcoin.
    gamma: the hashrate fluctuation gamma.
    node: headers, block sizes and the UTXO set of a Bitcoin Core node.
    figures: the figures, at the width of a paper column.
    cli: the command line.
"""

__version__ = '2.0.0.dev0'
