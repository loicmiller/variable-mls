###############################################################################
# Imports

import argparse
import config



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
    parser.add_argument("-k", "--unstable-part-length", type=int, metavar="K_PARAMETER",
                        default=1, help="Length of the unstable part (common prefix parameter, 'k').")
    parser.add_argument("-m", "--security-parameter", type=int, metavar="M_PARAMETER",
                        default=2, help="Value for the security parameter ('m').")

    # Toggles
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="Suppress non-essential output.")
    parser.add_argument("-d", "--dump-data", action="store_true",
                        help="Dump execution data to the data/ folder.")

    # Bitcoin block loading
    parser.add_argument("--load-from-headers", action="store_true", help="Load data from headers.")
    parser.add_argument("--headers", type=str, metavar="HEADERS_FILE_PATH", default=config.HEADERS_FILE_PATH, help="Path to the headers file. If --load-from-headers is set and this is not provided, default path from config will be used.")

    # Execution
    parser.add_argument("--step", action="store_true", help="Stop at each step, awaiting user input.")
    parser.add_argument("-s", "--print-step", type=int, metavar="STEP_SIZE", default=1, help="Size of steps for printing output to command line.")
    parser.add_argument("-b", "--break-at", type=int, metavar="HEIGHT", default=None, help="Stop execution at specified block height.")

    return parser