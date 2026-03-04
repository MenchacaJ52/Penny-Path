class Affordability:
    def __init__(self):
        self.max_allowable_payment = ""
        self.monthly_payment = ""
        self.inc = ""
        self.ammt = ""
        self.yint = ""
        self.mnth = ""
        self.intrt = ""

    def check_affordability(self):
        self.inc = int(input("What is your income?"))
        self.ammt = int(input("how much money is the item"))
        self.yint = int(input("What is the annual interest rate?"))
        self.mnth = int(input("How many Months is the loan?"))
        self.intrt = self.yint / 100 / 12
        if self.intrt > 0:
            self.monthly_payment = self.ammt * (self.intrt * (1 + self.intrt) ** self.mnth) / (
                    (1 + self.intrt) ** self.mnth - 1)
        else:
            self.monthly_payment = self.ammt / self.mnth
        self.max_allowable_payment = self.inc * .36
        if self.monthly_payment <= self.max_allowable_payment:
            print(f"\033[32mYou can afford the loan. Your monthly payment will be ${self.monthly_payment:.2f}.\033[0m")
        else:
            print(
                f"\033[31mYou cannot afford the loan. Your monthly payment would be ${self.monthly_payment:.2f}, "
                f"but the maximum allowable payment is ${self.max_allowable_payment:.2f}.\033[0m")
