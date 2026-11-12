"""Validated console input for the CLI — re-asks instead of crashing on bad input."""

RED, RESET = "\033[31m", "\033[0m"


def ask_float(prompt: str, minimum: float | None = 0.0, allow_zero: bool = True) -> float:
    """Prompt until the user enters a number >= minimum (and > 0 unless allow_zero)."""
    while True:
        raw = input(prompt).strip().replace("$", "").replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            print(f"{RED}Please enter a number.{RESET}")
            continue
        if minimum is not None and value < minimum:
            print(f"{RED}Please enter a value of at least {minimum:g}.{RESET}")
        elif not allow_zero and value == 0:
            print(f"{RED}Please enter a value greater than zero.{RESET}")
        else:
            return value


def ask_int(prompt: str, minimum: int = 0, maximum: int | None = None) -> int:
    """Prompt until the user enters a whole number within [minimum, maximum]."""
    while True:
        raw = input(prompt).strip()
        if raw.lstrip("-").isdigit():
            value = int(raw)
            if value >= minimum and (maximum is None or value <= maximum):
                return value
        bound = f"between {minimum} and {maximum}" if maximum is not None else f"of at least {minimum}"
        print(f"{RED}Please enter a whole number {bound}.{RESET}")


def ask_choice(prompt: str, options: list[str]) -> str:
    """Show a numbered menu of options and return the chosen one."""
    for i, opt in enumerate(options, 1):
        print(f"    {i}. {opt.title()}")
    return options[ask_int(prompt, 1, len(options)) - 1]
