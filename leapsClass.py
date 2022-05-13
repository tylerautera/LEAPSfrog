import json

class PMCoveredCall:
    def __init__(self):
        self.ticker = ""
        self.expDate = ""
        self.tradeDate = ""
        self.daysToExpire = 0
        self.breakEvenPrice = 0
        self.breakEvenPercent = 0
        self.totalPremiums = 0
        self.delta = 0
        self.strikePrice = 0
        self.contractCost = 0
        self.currStockPrice = 0
        self.assigned = 'false'
        self.returnOnLeap = 0
        self.sellOptionsList = []
        self.annualReturnPercent = 0
        self.annualReturnDollars = 0
        self.totalReturn = 0
        self.totalReturnPercent = 0
        self.stockPriceWhenAssigned = 0

    def addOptionAndPremium(self,callOption):
        self.totalPremiums = self.totalPremiums + callOption["callValue"]
        self.sellOptionsList.append(callOption)

    def toJSON(self):
        return json.dumps(self, default=lambda o: o.__dict__,
                          sort_keys=True, indent=4)


class LeapConfig:
    def __init__(self):
        self.minDaysToExpire = 0
        self.minDelta = 0
        self.maxPercentToBreakEven = 0

class CoveredCallConfig:
    def __init__(self):
        self.minDaysToExpire = 0
        self.maxDelta = 0
        self.minDelta = 0
        self.minPercentAboveBreakEven = 0


class OratsAPI:
    def __init__(self):
        self.baseUrlStrikesHistory = "https://api.orats.io/datav2/hist/strikes"
        self.baseUrlTickers = "https://api.orats.io/datav2/tickers"
        self.token = "024cad0b-01df-4cbc-bf80-77366753bb73"
        self.fields = "ticker,tradeDate,expirDate,dte,strike,stockPrice,callValue,delta,gamma"
