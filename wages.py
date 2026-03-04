class Wages:
    def __init__(self):
        self.weekly_wage = 0

    def set_wage(self):
        print("\033[32mSet Weekly Wage\033[0m")
        print("---------------")
        self.weekly_wage = float(input("Set Weekly Wage: "))
        print("\033[32mWeekly wage as been set to:\033[0m", self.weekly_wage)

    def deposit_wage(self, wage_account, weeks=1):
        for week in range(1, weeks + 1):
            wage_account.deposit_wage(self.weekly_wage)

    def wage_menu(self, wage_account, savings_account):
        while True:
            print("\033[32mWages Menu\033[0m")
            print("----------")
            print("1. Set Weekly Wage")
            print("2. Deposit to Wage Account")
            print("3. Transfer Wages to Savings")
            print("0. Exit")
            option = input("Choose an option: ")

            if option == "1":
                self.set_wage()
            elif option == "2":
                if self.weekly_wage <= 0:
                    print("\033[31mPlease set weekly wage before depositing.\033[0m")
                else:
                    weeks = int(input("Enter number of weeks to deposit wages: "))
                    if weeks > 0:
                        self.deposit_wage(wage_account, weeks)
                    else:
                        print("\033[31mNumber of weeks must be greater than zero.\033[0m")
            elif option == "3":
                transfer_amount = float(input("Enter amount to transfer to savings: "))
                wage_account.withdraw_wage(transfer_amount, savings_account)
            elif option == "0":
                print("Exiting Wages Menu.")
                break
            else:
                print("\033[31mInvalid option\033[0m")
