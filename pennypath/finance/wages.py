from pennypath.prompts import ask_float, ask_int

GREEN, RED, RESET = "\033[32m", "\033[31m", "\033[0m"


class Wages:
    def __init__(self):
        self.weekly_wage = 0.0

    @property
    def monthly_income(self) -> float:
        return self.weekly_wage * 52 / 12

    def set_wage(self):
        print(f"{GREEN}Set Weekly Wage{RESET}")
        print("---------------")
        self.weekly_wage = ask_float("Set Weekly Wage: $", allow_zero=False)
        print(f"{GREEN}Weekly wage has been set to:{RESET} ${self.weekly_wage:,.2f}")

    def deposit_wage(self, wage_account, weeks=1):
        for _ in range(weeks):
            wage_account.deposit_wage(self.weekly_wage)

    def wage_menu(self, wage_account, savings_account):
        while True:
            print(f"{GREEN}Wages Menu{RESET}")
            print("----------")
            print(f"Wage account balance: ${wage_account.balance:,.2f}")
            print("1. Set Weekly Wage")
            print("2. Deposit to Wage Account")
            print("3. Transfer Wages to Savings")
            print("0. Exit")
            option = input("Choose an option: ").strip()

            if option == "1":
                self.set_wage()
            elif option == "2":
                if self.weekly_wage <= 0:
                    print(f"{RED}Please set weekly wage before depositing.{RESET}")
                else:
                    weeks = ask_int("Enter number of weeks to deposit wages: ", minimum=1, maximum=520)
                    self.deposit_wage(wage_account, weeks)
            elif option == "3":
                amount = ask_float("Enter amount to transfer to savings: $", allow_zero=False)
                wage_account.withdraw_wage(amount, savings_account)
            elif option == "0":
                print("Exiting Wages Menu.")
                break
            else:
                print(f"{RED}Invalid option{RESET}")
