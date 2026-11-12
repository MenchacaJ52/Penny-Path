from pennypath.prompts import ask_float

GREEN, RED, RESET = "\033[32m", "\033[31m", "\033[0m"


class Account:
    """A balance that can be credited, debited, and transferred.
    Mutating methods return True on success and False if funds are insufficient."""
    LABEL = "Account"

    def __init__(self, balance: float = 0.0):
        self.balance = balance

    def add_balance(self, amount: float) -> bool:
        if amount <= 0:
            return False
        self.balance += amount
        print(f"{GREEN}New {self.LABEL.lower()} balance:{RESET} ${self.balance:,.2f}")
        return True

    def deduct_balance(self, amount: float) -> bool:
        if amount <= 0 or amount > self.balance:
            print(f"{RED}Insufficient funds{RESET}")
            return False
        self.balance -= amount
        print(f"{GREEN}New {self.LABEL.lower()} balance:{RESET} ${self.balance:,.2f}")
        return True

    def transfer(self, amount: float, target_account: "Account") -> bool:
        if amount <= 0 or amount > self.balance:
            print(f"{RED}Insufficient funds for transfer{RESET}")
            return False
        self.balance -= amount
        target_account.balance += amount
        print(f"{GREEN}Transferred ${amount:,.2f} to {target_account.LABEL.lower()}.{RESET}")
        return True

    def reset(self):
        self.balance = 0.0
        print(f"{self.LABEL} balance reset to $0.00")

    def menu(self, other: "Account"):
        """CLI menu for this account; `other` is the transfer destination."""
        while True:
            print(f"{GREEN}{self.LABEL.upper()} MENU{RESET}")
            print(f"Current {self.LABEL}: ${self.balance:,.2f}")
            print(f"1. Add to {self.LABEL}")
            print(f"2. Reset {self.LABEL} to $0")
            print("3. Deduct")
            print(f"4. Transfer to {other.LABEL}")
            print("5. Exit")

            option = input("Please choose an option: ").strip()
            if option == "1":
                self.add_balance(ask_float("How much would you like to add? $", allow_zero=False))
            elif option == "2":
                if input("Reset balance to $0? (yes/no): ").strip().lower() == "yes":
                    self.reset()
            elif option == "3":
                self.deduct_balance(ask_float("How much would you like to deduct? $", allow_zero=False))
            elif option == "4":
                self.transfer(ask_float("How much would you like to transfer? $", allow_zero=False), other)
            elif option == "5":
                break
            else:
                print(f"{RED}Invalid option{RESET}")


class SavingsAccount(Account):
    LABEL = "Savings"

    def add_savings(self, amount: float):
        self.balance += amount

    def savings_menu(self, checking_account):
        self.menu(checking_account)


class CheckingAccount(Account):
    LABEL = "Checking"

    def checking_menu(self, savings_account):
        self.menu(savings_account)


class WageAccount(Account):
    """Holds deposited wages until they are moved to savings."""
    LABEL = "Wage Account"

    def deposit_wage(self, amount: float):
        self.balance += amount
        print(f"${amount:,.2f} has been deposited into the wage account.")

    def withdraw_wage(self, amount: float, savings_account: SavingsAccount) -> bool:
        return self.transfer(amount, savings_account)
