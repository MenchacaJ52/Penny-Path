class Account:
    def __init__(self, balance=0):
        self.balance = balance

    def add_balance(self, amount):
        amount = float(input("Add to your account: "))
        self.balance += amount
        print("__________________________")
        print("\033[32mNew Account Balance:\033[0m ", self.balance)
        print("__________________________")

    def deduct_balance(self, amount):
        if amount > self.balance:
            print("__________________________")
            print("\033[31mInsufficient account fund\033[0m")
            print("__________________________")
        else:
            self.balance -= amount
            print("__________________________")
            print("\033[32mNew savings balance:\033[0m", self.balance)
            print("__________________________")

    def transfer(self, amount, target_account):
        if amount > self.balance:
            print("\033[31mInsufficient funds for transfer\033[0m")
        else:
            self.balance -= amount
            target_account.balance += amount
            print("-------------------")
            print("Transfer Successful")
            print("-------------------")


class SavingsAccount(Account):
    def __init__(self, balance=0):
        super().__init__(balance)

    def remove_savings(self):
        print("Savings Balance rest to $0.00")
        self.balance = 0

    def add_savings(self, amount):
        self.balance += amount

    def savings_menu(self, checking_account):
        while True:
            print("\033[32mSAVINGS MENU\033[0m")
            print("Current Savings: ", self.balance)
            print("1. Add Savings")
            print("2. Remove Savings")
            print("3. Deduct")
            print("4. Transfer")
            print("5. Exit")

            option = input("Please choose an option: ")

            if option == "1":
                amount = float(input("How much would you like to add: "))
                self.add_savings(amount)
            elif option == "2":
                self.remove_savings()
            elif option == "3":
                amount = float(input("How much would you like to deduct: "))
                self.deduct_balance(amount)
            elif option == "4":
                amount = float(input("How much would you like to transfer to checking?: "))
                self.transfer(amount, checking_account)
            elif option == "5":
                break
            else:
                print("\033[31mInvalid option\033[0m")


class CheckingAccount(Account):
    def __init__(self, balance=0):
        super().__init__(balance)

    def remove_checking(self):
        self.balance = 0
        print("Checking balance reset to $0.00")

    def checking_menu(self, savings_account):
        while True:
            print("\033[32mCHECKING MENU\033[0m")
            print("Current Checking: ", self.balance)
            print("1. Add to Checking")
            print("2. Remove Checking")
            print("3. Deduct")
            print("4. Transfer")
            print("5. Exit")

            option = input("Please choose an option: ")

            if option == "1":
                amount = float(input("Enter amount to add to checking: "))
                self.add_balance(amount)
            elif option == "2":
                self.remove_checking()
            elif option == "3":
                amount = float(input("Enter amount to deduct from checking: "))
                self.deduct_balance(amount)
            elif option == "4":
                amount = float(input("How much would you like to transfer to savings?: "))
                self.transfer(amount, savings_account)
            elif option == "5":
                break
            else:
                print("\033[31mInvalid Option\033[0m")


class WageAccount:
    def __init__(self):
        self.balance = 0

    def deposit_wage(self, amount):
        self.balance += amount
        print(amount, "has been deposited into the Wage Account.")
        print("Current wage account balance: ", self.balance)

    def withdraw_wage(self, amount, savings_account):
        if amount > self.balance:
            print("\033[31mInsufficient funds in wage account\033[0m")
        else:
            self.balance -= amount
            savings_account.balance += amount
            print(amount, "has been transfered to Savings Account")
            print("\033[32Remaining Wage Balance:\033[0m ", self.balance)
