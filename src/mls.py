###############################################################################
# Imports

import sys
import json
import time
from datetime import datetime
from bcolors import bcolors
import copy

from argparser import get_parser
import config
import bitcoin
from chain_generator import (RandomLevelChainGenerator, ScriptedLevelChainGenerator)
from visualize_proof import visualize_proof
from rarity import rarity_report, print_rarity_report



###############################################################################
# Main functions

def Dissolve(chain):
    """
    Dissolves a blockchain by compressing it according to parameters K, chi and k.

    Args:
    - chain (list): The blockchain to dissolve, as a list of blocks.

    Returns:
    - dissolved_chain, level, proof_remainder (tuple): A tuple containing the dissolved compressed part of the chain (dissolved_chain), level of the proof (level), and the remainder of the proof (proof_remainder).

    Notes:
    - The dissolved chain (dissolved_chain) is the compressed part of the proof, a dictionary where keys represent levels and values are lists of blocks at that level.
    - The level of the proof (level) is an integer.
    - The remainder of the proof (proof_remainder) is a list of blocks.
    """
    proof_compressed = chain[:-k_args-chi_args]
    dissolved_chain = {}
    if len(proof_compressed) >= 2*K_args:
        level = get_proof_level(proof_compressed) # Get max level 'l' where there is at least 2*K blocks.
        dissolved_chain[level] = filter_chain_by_level(proof_compressed, level) # Keep all blocks at max level.

        for mu in range(level-1, -1, -1): # Keep relevant blocks in the compressed proof, from level-1 to level 0 included.
            b = filter_chain_by_level(proof_compressed, mu+1)[-K_args] # Get K-th block from the end at level directly above.
            chain_at_level_mu = filter_chain_by_level(proof_compressed, mu) # Get filtered chain at level mu.
            dissolved_chain[mu] = chain_at_level_mu[min(len(chain_at_level_mu) - 2*K_args, chain_at_level_mu.index(b)):] # Keep last 2*K blocks at that level, or more if index of b is smaller.
    else:
        level = 0
        dissolved_chain[0] = proof_compressed
    proof_remainder = chain[-k_args-chi_args:]
    return (dissolved_chain, level, proof_remainder)


def Compress(chain):
    """
    Compresses a blockchain using the Dissolve algorithm and returns the compressed chain.

    Args:
    - chain (list): The blockchain to compress, as a list of blocks.

    Returns:
    - proof_compressed + proof_remainder (list): The compressed version of the blockchain, as a list of blocks.

    Notes:
    - This function compresses the blockchain using the Dissolve algorithm.
    - The dissolved chain (dissolved_chain) is the compressed part of the proof, a dictionary where keys represent levels and values are lists of blocks at that level.
    - This function returns the compressed blockchain, as the concatenation of the compressed and remainder parts of the compressed blockchain.
    """
    (dissolved_chain, _, proof_remainder) = Dissolve(chain)
    proof_compressed = dissolved_chain_to_chain(dissolved_chain)
    return proof_compressed + proof_remainder


def Compare(proof, proof_prime):
    """
    Determine the best proof between two given proofs.

    Args:
    - proof (list): First blockchain proof, i.e. a list of blocks.
    - proof_prime (list): Second blockchain proof, i.e. a list of blocks.

    Returns:
    - proof OR proof_prime (list): The best proof between the two given proofs.

    Notes:
    - This function determines the best proof between two proofs based on their validity and difficulties after their last common ancestor.
    """
    if proof_not_valid(proof):
        return proof_prime
    if proof_not_valid(proof_prime):
        return proof

    dissolved_chain, level, proof_remainder = Dissolve(proof)
    dissolved_chain_prime, level_prime, proof_remainder_prime = Dissolve(proof_prime)

    M = intersection(dissolved_chain, dissolved_chain_prime)
    if not M.keys(): # If there are no levels with common blocks between the proofs, return the one with the higher score.
        if level_prime > level:
            return proof_prime
        return proof

    mu = min(M.keys()) # Pick mu as the minimum level with blocks in common.
    b = M[mu][-1] # The last block in common of proof and proof_prime at level mu, i.e. their last common ancestor.
    if chain_score(dissolved_chain_prime[mu][dissolved_chain_prime[mu].index(b):]) + chain_score(proof_remainder_prime) > chain_score(dissolved_chain[mu][dissolved_chain[mu].index(b):]) + chain_score(proof_remainder):
        return proof_prime
    return proof



###############################################################################
# Helper functions

def dissolved_chain_to_chain(dissolved_chain):
    """
    Reconstructs the blockchain as a list of blocks, from a dissolved blockchain.

    Args:
    - dissolved_chain (dict): A dissolved blockchain, i.e. a dictionary where keys represent levels and values are lists of blocks at that level.

    Returns:
    - chain (list): The blockchain, as a list of blocks.
    """
    chain = []
    unique_block_heights = set() # Keep track of unique blocks across levels.

    for level_blocks in dissolved_chain.values():
        for block in level_blocks:
            if block.height not in unique_block_heights:
                chain.append(block)
                unique_block_heights.add(block.height)
    return sorted(chain, key=lambda block: block.height)

def filter_chain_by_level(chain, level):
    """
    Filter blocks in the chain based on the given level.

    Args:
    - chain (list): The blockchain, as a list of blocks.
    - level (int): The level to filter the blocks.

    Returns:
    - filtered_chain (list): The filtered chain containing only the blocks corresponding to the given level and above.
    """
    filtered_chain = []
    for block in chain: # Iterate through the blocks and add those corresponding to the given level or above it.
        if block.level >= level:
            filtered_chain.append(block)
    return filtered_chain


#######################################
## Proof information functions

def proof_not_valid(proof):
    """
    Checks if a given proof is valid or not.

    Args:
    - proof (list): The proof to be checked, as a list of blocks.

    Returns:
    - bool: False indicating that the proof is valid. For now, this function does not perform any validation and always returns False.
    """
    return False

def get_proof_level(proof):
    """
    Determines the level of the proof based on the number of blocks in each level.

    Args:
    - proof (list): The blockchain, as a list of blocks.

    Returns:
    - level (int): The level of the proof.

    Notes:
    - This function returns the highest level of the proof where there are at least 2*K blocks.
    - If no level satisfies the condition (at least 2*K blocks), returns 0.
    """
    level_count = {} # Dictionary to store the count of blocks for each level.

    # Count the number of blocks for each level.
    for block in proof:
        level_count[block.level] = level_count.get(block.level, 0) + 1
        for i in range(block.level): # A block of level block.level is also a block of levels below, so we increment them.
            level_count[i] = level_count.get(i, 0) + 1

    # Find the highest level with at least 2*K blocks, else return 0.
    for level in sorted(level_count.keys(), reverse=True):
        if level_count[level] >= 2*K_args:
            return level
    return 0


#######################################
## Proof set operator

def intersection(dissolved_chain, dissolved_chain_prime):
    """
    Compute the intersection of two dissolved blockchain proofs.

    Args:
    - dissolved_chain (dict): First dissolved blockchain proof, a dictionary where keys represent levels and values are lists of blocks at that level.
    - dissolved_chain_prime (dict): Second dissolved blockchain proof, a dictionary where keys represent levels and values are lists of blocks at that level.

    Returns:
    - proof_intersection (dict): The intersection of the two blockchain proofs, where keys represent levels and values are lists of blocks at that level.

    Notes:
    - The intersection of two proofs includes blocks that exist in both proofs at the same block level.
    - If a block level exists in both proofs but there are no common blocks, that level is not included in the intersection.
    - If a block level exists in one proof but not in the other, that level is not included in the intersection.
    """
    proof_intersection = {}
    common_levels = set(dissolved_chain.keys()) & set(dissolved_chain_prime.keys())

    for level in common_levels:
        dissolved_chain_blocks = dissolved_chain[level]
        dissolved_chain_prime_blocks = dissolved_chain_prime[level]

        # Find blocks that exist in both proofs at the same block level.
        intersection_blocks = [block for block in dissolved_chain_blocks if any(block.height == block_prime.height for block_prime in dissolved_chain_prime_blocks)]

        if intersection_blocks: # Do not add the level if there are no blocks in common.
            proof_intersection[level] = intersection_blocks
    return proof_intersection


#######################################
## Score function

def chain_score(chain):
    """
    Calculate the score of a blockchain by summing the difficulty of its blocks.

    Args:
    - chain (list): The blockchain, as a list of blocks.

    Returns:
    - int: The score of the blockchain.

    Notes:
    - If the blockchain is empty, the score is 0.
    """
    if not chain:
        return 0
    return sum([block.diff for block in chain])


###############################################################################
# Auxiliary functions

def terminate_app(code, message=None):
    """
    Terminates the application with a specified exit code and optional message.

    Args:
    - code (int): The exit code to terminate the application with.
    - message (str, optional): An optional message to display before exiting.

    Returns:
    - None

    Notes:
    - This function prints a message indicating the exit code and optional message, then exits the program.
    """
    if message:
        print(f"Exiting program with code {code} - {message}")
    else:
        print(f"Exiting program with code {code}.")
    sys.exit(code)

def print_status(proof):
    """
    Prints output to the command line

    Args:
    - None

    Returns:
    - None

    Notes:
    - This function prints the elapsed time (in milliseconds) since the last time check.
    """
    # Calculate elapsed time since last check.
    global last_time_check
    current_time = time.time()
    if last_time_check == None:
        last_time_check = current_time
    elapsed_time = round((current_time - last_time_check) * 1_000, 3) # Elapsed time in ms.

    # Dissolve proof
    dissolved_chain, level, _ = Dissolve(proof)

    # Output status to command line.
    if verbose == 0:
        print(bcolors.WARNING + f"Proof compressed with new block [{proof[-1].height:06} ({proof[-1].level:3})] - {f'{proof[-1].block_hash:064X}'[:20]} - {elapsed_time} ms" + bcolors.ENDC) # Display height and level of new block.
    elif verbose >= 1:
        print("=============================")
        print(bcolors.WARNING + f"Added new block [{proof[-1].height:06} ({proof[-1].level:3})] - {proof[-1].block_hash:X} - {elapsed_time} ms" + bcolors.ENDC) # Display height and level of new block.
        print(bcolors.OKCYAN + f"Proof: score={chain_score(proof)}, size={len(proof)}, level={level}" + bcolors.ENDC)
        print(bcolors.OKCYAN + "Compressed part:" + bcolors.ENDC)
        for mu in range(level, -1, -1):
            level_string = ""
            for block in dissolved_chain[mu]:
                level_string += f"[{block.height:06} ({level:3})] "
            print(bcolors.FAIL + f"{mu:2} ({chain_score(dissolved_chain[mu]):3}) -     " + bcolors.OKCYAN + level_string + bcolors.ENDC)
        print()

    s = bcolors.OKGREEN + f'compress computation ({height=}, {proof_score=})' + bcolors.ENDC

    last_time_check = current_time # Update last_time_check.

def dump_data(targets, proof_sizes, proof_scores, proof_levels, timestamps, block_hashes, block_levels, proof_generation_latencies, K_last_blocks_difficulties, height, message=""):
    """
    Dump data to a JSON file with a filename based on timestamp, height, and an optional message.

    Args:
    - targets (list): List of block targets.
    - proof_sizes (list): List of sizes of the compressed proofs in number of blocks.
    - proof_scores (list): List of total scores of the compressed proofs.
    - proof_levels (list): List of levels of the compressed proofs.
    - timestamps (list): List of timestamps associated with the blocks.
    - block_hashes (list): List of hashes associated with the blocks.
    - block_levels (list): List of levels associated with the blocks.
    - proof_generation_latencies (list): List of proof generation latencies.
    - K_last_blocks_difficulties (list): List of `dict`s, each mapping level to the difficulties of the last K blocks for one iteration/proof.
    - height (list): List of block heights.
    - message (str, optional): An optional message to include in the filename.

    Returns:
    - None

    Notes:
    - This function dumps the provided data into a JSON file with a filename constructed based on the current timestamp,
    data height, and an optional message. If no message is provided, the filename includes only the timestamp and height.
    The optional message indicates how the execution finished.
    """
    # Flatten K_last_blocks_difficulties into lists.
    max_level = max(K_last_blocks_difficulties[-1].keys()) # Find max level.
    level_difficulty_lists = {} # Dictionary to store difficulties at each level.
    for mu in range(max_level + 1):
        level_difficulty_lists[f"level_{mu}_difficulty"] = [d.get(mu, 0) for d in K_last_blocks_difficulties]
    
    data = {
        'target': targets,
        'proof_size': proof_sizes,
        'proof_score': proof_scores,
        'proof_level': proof_levels,
        'timestamp': timestamps,
        'block_hash': block_hashes,
        'block_level': block_levels,
        'proof_generation_latency': proof_generation_latencies,
        **level_difficulty_lists
    }
    now = datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
    if message:
        with open(f'data/{now}-data-up-to-{height}-K-{K_args}-chi-{chi_args}-k-{k_args}-{message}.json', 'w') as f:
            json.dump(data, f)
    else:
        with open(f'data/{now}-data-up-to-{height}-K-{K_args}-chi-{chi_args}-k-{k_args}.json', 'w') as f:
            json.dump(data, f)



###############################################################################
# Main

if __name__ == '__main__':
    """
    Main execution block of the blockchain compression algorithm.

    This block handles the main execution flow of the program. It parses command-line arguments using the argparse module,
    loads blockchain headers using the bitcoin module, iterates through the blocks, compresses the blockchain using the Dissolve algorithm,
    handles interrupts, and dumps data to a JSON file upon completion.

    Command-line arguments:
    - version (str): Print the version of the program.
    - verbose (int): Increase output verbosity.

    - unstable_part_length (int): Length of the unstable part (common prefix parameter, 'k').
    - uncompressed_part_length (int): Length of the uncompressed part ('χ').
    - security_parameter (int): Value for the security parameter ('K').
    
    - quiet (bool): Toggle for suppressing non-essential output.
    - dump_data (bool): Toggle for dumping execution data to the data/ folder.

    - load_from_headers (bool): Toggle for loading blockchain headers.
    - headers (str): Path to the blockchain headers file.

    - chain (str): Type of blockchain to use ('bitcoin', 'random', or 'scripted').
    - p (float): Geometric distribution parameter for random chain.
    - seed (int): Seed for random chain generation.
    - levels (list): Comma-separated list of block levels (e.g. 0,0,3,0,1,0,5).

    - step (bool): Toggle for executing the algorithm step by step, waiting for user input at each iteration.
    - print_step (int): Size of steps for printing output to command line.
    - break_at (int): Optional argument to specify the block height at which execution should stop.

    Global variables:
    - verbose (int): Global variable storing the verbosity level.
    - k (int): The common prefix parameter, i.e. the length of the unstable part.
    - chi (int): The length of the uncompressed part.
    - K (int): The security parameter, i.e. half the number of blocks required for (a level of) the proof.
    - last_time_check (float): Global variable storing the timestamp of the last time check.

    Returns:
    - Terminates the application with an exit code using the terminate_app() function.
    """
    # Argument parser
    parser = get_parser() # Create a parser.
    args = parser.parse_args() # Parse arguments.
    if args.headers != config.HEADERS_FILE_PATH:
        args.load_from_headers = True
    print(args)

    # Verbose
    global verbose
    verbose = args.verbose

    # Track time for command line output.
    global last_time_check
    last_time_check = None

    # Argument parser - Mining in Logarithmic Space parameters
    global K_args, chi_args, k_args
    k_args = args.unstable_part_length # Global variable for k (int): The common prefix parameter, i.e. the length of the unstable part.
    chi_args = args.uncompressed_part_length # Global variable for χ (int): The length of the uncompressed part.
    K_args = args.security_parameter # Global variable for K (int): The security parameter, i.e. half the number of blocks required for (a level of) the proof.

    # Argument parser - Toggles
    quiet = args.quiet

    # Argument parser - Block loading
    config.HEADERS_FILE_PATH = args.headers
    bitcoin.LOAD_FROM_HEADERS_FILE = args.load_from_headers

    # Data collectors
    targets = []
    proof_sizes = []
    proof_scores = []
    proof_levels = []
    timestamps = []
    block_hashes = []
    block_levels = []
    proof_generation_latencies = []
    K_last_blocks_difficulties = [] # List of `dict`s, each mapping level to the difficulties of the last K blocks for one iteration/proof.

    proof = [] # Bitcoin blockchain.
    proof_score = 0 # Proof score.
    old_proof = [] # Keep track of old proof for Compare comparison.

    full_chain = [] # Keep track of full chain for visualization.

    # Chain initialization and length
    if args.chain == "bitcoin":
        headersNumber = bitcoin.load_headers(args.break_at)
    else:
        # Synthetic chains: define chain length
        if args.chain == "random":
            if args.break_at is None:
                terminate_app(2, "--break-at is required for random chain")
            headersNumber = args.break_at
        elif args.chain == "scripted":
            if args.levels is None:
                terminate_app(2, "--levels is required for scripted chain")
            headersNumber = len(args.levels)
        else:
            terminate_app(2, "Unknown chain type")

    # Chain generator selection
    chain = None
    if args.chain == "random":
        from chain_generator import RandomLevelChainGenerator
        chain = RandomLevelChainGenerator(p=args.p, seed=args.seed)

    elif args.chain == "scripted":
        from chain_generator import ScriptedLevelChainGenerator
        if args.levels is None:
            terminate_app(2, "--levels is required for scripted chain")
        chain = ScriptedLevelChainGenerator(args.levels)

    try:
        print("Starting compression loop...")
        for height in range(headersNumber):
            last_time_check = time.time() # Store time for print_time_since_last_time_check().

            # Get new block.
            if chain is None:
                # Bitcoin mode (default)
                b = bitcoin.get_block_by_height(height)
                if height == 0:  # Set level of genesis block to infinity: 256.
                    b.level = 256
            else:
                # Synthetic chain
                b = chain.get_block_by_height(height)

            # Add new block to proof.
            proof.append(copy.deepcopy(b))
            full_chain.append(copy.deepcopy(b))

            # Compress the proof.
            proof = Compress(proof)

            # Measure proof generation latency for this iteration and record it.
            proof_generation_latency = (time.time() - last_time_check) * 1_000
            proof_generation_latencies.append(proof_generation_latency)

            # Data collection - Adding data for new block and new proof.
            targets += [b.target]
            proof_sizes += [len(proof)]
            proof_scores += [chain_score(proof)]
            proof_levels += [get_proof_level(proof)]
            timestamps += [b.timestamp]
            block_hashes += [b.block_hash]
            block_levels += [b.level]

            # Data collection - Adding data for last K blocks difficulties at every level.
            dissolved_chain, level, _ = Dissolve(proof)
            current_k_difficulties = {}
            for mu in dissolved_chain:
                last_k_blocks = dissolved_chain[mu][-K_args:] # Get last K blocks at level mu
                current_k_difficulties[mu] = chain_score(last_k_blocks) # Store their difficulties
            K_last_blocks_difficulties.append(copy.deepcopy(current_k_difficulties))

            # Choose best proof by comparing scores with Compare.
            if height > k_args+chi_args: # Only compare after k+χ blocks, otherwise they are equal.
                proof = copy.deepcopy(Compare(old_proof, proof))

            # Since we add blocks incrementally from history, we should never choose the old proof.
            if old_proof == proof:
                if args.dump_data:
                    dump_data(targets, proof_sizes, proof_scores, proof_levels, timestamps, block_hashes, block_levels, proof_generation_latencies, K_last_blocks_difficulties, height, "equals")
                terminate_app(2, "Previous proof selected, this should not happen.")

            # Store current proof as old_proof for comparison at next iteration.
            old_proof = copy.deepcopy(proof)

            # Print status.
            if not quiet:
                if height % args.print_step == 0: # Print only at each print step.
                    print_status(proof)
            
            if (args.break_at is not None) and (height > args.break_at): #  Argument parser - Break at specified height.
                break
            if args.step: # Argument parser - Stop at each step, awaiting user input.
                input()

    except KeyboardInterrupt: # Still get data dump if execution is interrupted.
            if args.dump_data:
                dump_data(targets, proof_sizes, proof_scores, proof_levels, timestamps, block_hashes, block_levels, proof_generation_latencies, K_last_blocks_difficulties, height, "interrupted")
            terminate_app(2, "Keyboard Interrupt")

    # Execution complete, dump data and exit.
    if args.dump_data:
        dump_data(targets, proof_sizes, proof_scores, proof_levels, timestamps, block_hashes, block_levels, proof_generation_latencies, K_last_blocks_difficulties, height, "completed")

    if not quiet:
        dissolved_chain, _, _ = Dissolve(proof)

        # Rarity report
        levels = [b.level for b in full_chain[1:]]  # exclude genesis
        p = args.p
        report = rarity_report(levels, p, trials=20_000, seed=0)
        print_rarity_report(report)

        visualize_proof(full_chain, proof, dissolved_chain, k_args, chi_args, K_args, title=f"MLS compressed proof (|proof| = {len(proof)})")

    print("Execution complete!")
    terminate_app(0)

###############################################################################