###############################################################################
# Imports

import argparse
from email import parser
import config



###############################################################################
# Helper functions

def parse_levels(levels_str: str):
    """
    Parse a comma-separated list of block levels.

    Args:
        levels_str (str): Comma-separated levels string.

    Returns:
        list[int]: Parsed block levels.
    """
    return [int(x) for x in levels_str.split(",") if x.strip()]



###############################################################################
# Argument parser

def get_parser():
    """
    Create an argument parser for Variable MLS.

    Returns:
    - parser (argparse.ArgumentParser): The argument parser object.
    """
    parser = argparse.ArgumentParser(description="Variable MLS on Bitcoin implementation", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--version", action="version", version='%(prog)s 1.0')
    parser.add_argument("-v", "--verbose", action="count", default=0, help="Increase output verbosity.")

    # Mining in Logarithmic Space parameters
    parser.add_argument("-k", "--unstable-part-length", type=int, metavar="COMMON_PREFIX_PARAMETER",
                        default=323, help="Length of the unstable part (common prefix parameter, 'k').")
    parser.add_argument("-chi", "--uncompressed-part-length", type=int, metavar="UNCOMPRESSED_PART_LENGTH",
                        default=4032, help="Length of the uncompressed part ('χ').")
    parser.add_argument("-K", "--security-parameter", type=int, metavar="SECURITY_PARAMETER",
                        default=208, help="Value for the security parameter ('K').")

    # Toggles
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="Suppress non-essential output.")
    parser.add_argument("-d", "--dump-data", action="store_true",
                        help="Dump execution data to the data/ folder.")
    parser.add_argument("--dump-proof", type=str, default=None, help="Dump final proof structure to a JSON file.")

    # Chain generation
    parser.add_argument("--chain", type=str, choices=["bitcoin", "random", "scripted"],
                        default="bitcoin", help="Chain source: bitcoin (default), random, or scripted.")
    parser.add_argument("--p", type=float, default=0.5, help="Geometric distribution parameter for random chain.")
    parser.add_argument("--seed", type=int, default=None, help="Seed for random chain generation.")
    parser.add_argument("--levels", type=parse_levels, default=None, help="Comma-separated list of block levels (e.g. 0,0,3,0,1,0,5).")

    # Bitcoin block loading
    parser.add_argument("--load-from-headers", action="store_true", help="Load data from headers.")
    parser.add_argument("--headers", type=str, metavar="HEADERS_FILE_PATH", default=config.HEADERS_FILE_PATH,
                        help="Path to the headers file. If --load-from-headers is set and this is not provided, default path from config will be used.")

    # Execution
    parser.add_argument("--step", action="store_true", help="Stop at each step, awaiting user input.")
    parser.add_argument("-s", "--print-step", type=int, metavar="STEP_SIZE", default=1, help="Size of steps for printing output to command line.")
    parser.add_argument("-b", "--break-at", type=int, metavar="HEIGHT", default=None, help="Stop execution at specified block height.")

    return parser