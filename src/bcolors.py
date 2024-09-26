# Source: https://stackoverflow.com/questions/287871/how-do-i-print-colored-text-to-the-terminal
class bcolors:
    """
    A class to define ANSI escape codes for text color and formatting in terminal.

    Attributes:
    - HEADER (str): ANSI escape code for header color.
    - OKBLUE (str): ANSI escape code for blue color.
    - OKCYAN (str): ANSI escape code for cyan color.
    - OKGREEN (str): ANSI escape code for green color.
    - WARNING (str): ANSI escape code for warning color.
    - FAIL (str): ANSI escape code for fail/error color.
    - ENDC (str): ANSI escape code to end color/formatting.
    - BOLD (str): ANSI escape code for bold text.
    - UNDERLINE (str): ANSI escape code for underlined text.
    """
    HEADER = '\033[95m'   # Purple color
    OKBLUE = '\033[94m'   # Blue color
    OKCYAN = '\033[96m'   # Cyan color
    OKGREEN = '\033[92m'  # Green color
    WARNING = '\033[93m'  # Yellow color
    FAIL = '\033[91m'     # Red color
    ENDC = '\033[0m'      # End color/formatting
    BOLD = '\033[1m'      # Bold text
    UNDERLINE = '\033[4m' # Underlined text
