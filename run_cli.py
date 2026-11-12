"""Start the PennyPath command-line app."""
from pennypath.ui.cli import main

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nGoodbye!")
