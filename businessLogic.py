import requests
import json
import holidays
from leapsClass import OratsAPI
from leapsClass import LeapConfig
from leapsClass import CoveredCallConfig
from leapsClass import PMCoveredCall
from datetime import datetime, timedelta

"""
GLOBAL VARIABLES 
"""
# defines the date format from ORATS API to convert to python dateTime in several methods below
dateFormat = '%Y-%m-%d'


"""
METHODS
"""
def findLeap(leapConfig: LeapConfig, orats: OratsAPI, tickerList, tradeDate):

    dteMax = str(leapConfig.minDaysToExpire + 300)
    dteRange = str(leapConfig.minDaysToExpire) + "," + dteMax
    params = {'token': orats.token,
              'ticker': ",".join(tickerList),
              'tradeDate': tradeDate,
              'dte': dteRange,
              'fields': orats.fields,
              'delta': str(leapConfig.minDelta) + ",1"
              }
    resp = requests.get(orats.baseUrlStrikesHistory, params)
    obj = json.loads(resp.content)
    optionsChain = obj["data"]

    coveredCallList = []

    for ticker in tickerList:

        optionsChainST = [option for option in optionsChain if option["ticker"] == ticker]
        optionsChainST.reverse()

        if len(optionsChainST) < 1:
            continue

        for option in optionsChainST:

            pmCoveredCall = PMCoveredCall()

            breakEvenPrice = option["strike"] + option["callValue"]
            breakEvenPercentage = (breakEvenPrice - option["stockPrice"]) / option["stockPrice"] * 100

            if option["delta"] < leapConfig.minDelta:
                continue

            if breakEvenPercentage >= leapConfig.maxPercentToBreakEven:
                continue

            pmCoveredCall.delta = option["delta"]
            pmCoveredCall.breakEvenPrice = breakEvenPrice
            pmCoveredCall.ticker = ticker
            pmCoveredCall.breakEvenPercent = breakEvenPercentage
            pmCoveredCall.currStockPrice = option["stockPrice"]
            pmCoveredCall.daysToExpire = option["dte"]
            pmCoveredCall.expDate = option["expirDate"]
            pmCoveredCall.contractCost = option["callValue"] * 100
            pmCoveredCall.tradeDate = option["tradeDate"]

            coveredCallList.append(pmCoveredCall)
            break

    return coveredCallList;


def buildCoveredCalls(pmCoveredCallList, orats: OratsAPI, ccConfig : CoveredCallConfig, tickerList, startTradeDate):

    # retrieves the leap expiration date from the first ticker in the sequence. This is not perfect because
    # the leaps on different tickers may have different expirations, but it is likely close enough for the
    # high level estimations we are after
    pmExpDate = datetime.strptime(pmCoveredCallList[0].expDate,dateFormat)
    tradeDate = startTradeDate
    ccExpDate = datetime.strptime('2000-1-1', dateFormat)

    while ccExpDate < pmExpDate:

        # this checks to make sure there is at least one ticker that has not been assigned before
        # running through more option chains calls
            unassignedCoveredCallList = [cc for cc in pmCoveredCallList if cc.assigned == 'false']
            if len(unassignedCoveredCallList) < 1:
                break
            # this function calls the options chains for all of the tickers on a particular trade date from ORATS API
            optionsChain = getCoveredCallOptionsChain(orats, ccConfig, tradeDate, tickerList);

            # this for loop iterates through the various cc-leap objects and builds the covered call lists,
            # calculates premiums and checks whether the cc would have been assigned
            for ccItem in pmCoveredCallList:

                # filters the option chain to only include the current ticker being looked at
                optionChainST = [option for option in optionsChain if option["ticker"] == ccItem.ticker]

                # this updates the the global trade date (line 75) variable for the next options cycle by
                # looking at the expiration of the current option cycle - note: this will not be perfect as
                # some options will expire at different dates, but overall, it will be close
                tradeDate = getNextTradingDay(datetime.strptime(optionChainST[0]["expirDate"], dateFormat))

                # this conditional logic checks to see if the cc has been assigned based on the previous
                # cc that was made. If the stock price listed in the new options cycle is greater than
                # the strike price of the previous cc, then it is safe to assume that the previous cc
                # would have been assigned.
                if len(ccItem.sellOptionsList) > 0:
                    lastSellOption = ccItem.sellOptionsList[-1]
                    if lastSellOption["strike"] < optionChainST[0]["stockPrice"]:
                        ccItem.assigned = 'true'
                        ccItem.returnOnLeap = (lastSellOption["strike"] - ccItem.breakEvenPrice) * 100
                        ccItem.stockPriceWhenAssigned = optionChainST[0]["stockPrice"]
                        deltaDate = datetime.strptime(optionChainST[0]["expirDate"], dateFormat) - datetime.strptime(ccItem.tradeDate, dateFormat)
                        ccItem.daysToExpire = deltaDate.days
                        continue

                # If the previous cc is not assigned, this iterates through the options chain to find the next
                # cc that will be made based on the Covered Call criteria that have been configured, and the
                # breakeven price of the leap
                for option in optionChainST:

                    ccExpDate = datetime.strptime(option["expirDate"], dateFormat)

                    if option["delta"] > ccConfig.maxDelta:
                        continue
                    if option["strike"] < ccItem.breakEvenPrice or option["strike"] < ccItem.breakEvenPrice * (1 + ccConfig.minPercentAboveBreakEven):
                        continue

                    # calculates the premium made from executing the covered call, and adds to the total
                    # premium under the cc-leap strategy. Once a suitable option is found, the loop breaks
                    premium = option["callValue"] * 100
                    ccItem.totalPremiums = ccItem.totalPremiums + premium
                    ccItem.sellOptionsList.append(option)

                    break
    # once all cc option are in place this function will calculate the returns of the cc-leap investment
    pmCoveredCallList = calculateReturns(pmCoveredCallList)

    return pmCoveredCallList

# function to find the next trading day, skips weekends and uses the python holiday library to skip US holidays as well
def getNextTradingDay(day_now: datetime):

    while day_now in holidays.US() or day_now.isoweekday() > 5:
        day_now += timedelta(days=1)

    return day_now


# calculates various ROI metrics based on the outcome of the cc-leap investment, takes in a list of the cc-leap objects
def calculateReturns(pmList: list[PMCoveredCall]):

    for pm in pmList:

        if pm.returnOnLeap == 0:
            lastStockPrice = pm.sellOptionsList[-1]["stockPrice"]
            pm.returnOnLeap = (lastStockPrice - pm.breakEvenPrice) * 100
        pm.totalReturn = pm.returnOnLeap + pm.totalPremiums
        pm.totalReturnPercent = (pm.totalReturn / pm.contractCost) * 100
        dailyReturn = pm.totalReturn / pm.daysToExpire
        pm.annualReturnDollars = dailyReturn * 365
        pm.annualReturnPercent = pm.annualReturnDollars / pm.contractCost * 100

    return pmList


# API call to ORATS to retrieve the option chains for multiple tickers based on the convered call criteria
# as well as the trade date that is iterated through when building the cc-leap object
def getCoveredCallOptionsChain(orats : OratsAPI, ccConfig : CoveredCallConfig, tradeDate, tickerList):

    dteMax = str(ccConfig.minDaysToExpire + 25)
    dteRange = str(ccConfig.minDaysToExpire) + "," + dteMax
    params = {'token': orats.token,
              'ticker': ",".join(tickerList),
              'tradeDate': tradeDate,
              'dte': dteRange,
              'fields': orats.fields,
              'delta': str(ccConfig.minDelta) + "," + str(ccConfig.maxDelta)
              }
    resp = requests.get(orats.baseUrlStrikesHistory, params)
    obj = json.loads(resp.content)
    optionsChain = obj["data"]

    return optionsChain;


# function to retreive the stock price on the day that the LEAPS expires
def getStockPriceOnLeapExpiration(orats: OratsAPI, tickerList, expireDates):

    for tradeDate in expireDates:
        params = {'token': orats.token,
                  'ticker': ",".join(tickerList),
                  'tradeDate': tradeDate,
                  'dte': 1,
                  'fields': "ticker, stockPrice",
                  }
        resp = requests.get(orats.baseUrlStrikesHistory, params)
        obj = json.loads(resp.content)
        optionsChain = obj["data"]


# retrieves the tradeHistoryWindows for the stocks that will be considered in the cc-leap simlulation
def getTickerTradeHistoryWindows(orats: OratsAPI, tickerList):

    params = {'token': orats.token,
              'ticker': ",".join(tickerList)
              }
    resp = requests.get(orats.baseUrlTickers, params)
    obj = json.loads(resp.content)

    return obj['data']


# checks to make sure the tickers in the query will have data when calling the ORATS api
def checkThatTickerFallInTradeWindow(orats: OratsAPI, tickerList, startTradeDate):

    tickerTradeHistory = getTickerTradeHistoryWindows(orats, tickerList)
    updatedTickerList = tickerList
    removedTickers = []

    for ticker in tickerList:

        tickerWindow = [tw for tw in tickerTradeHistory if tw["ticker"] == ticker]

        if len(tickerWindow) > 0:
            if datetime.strptime(tickerWindow[0]["min"], dateFormat) > datetime.strptime(startTradeDate, dateFormat):
                updatedTickerList.remove(ticker)
                removedTickers.append(ticker)

    if len(removedTickers) > 0:
        print("The following ticker(s) were removed from your query due to ORATS ticker history limitations: " + ",".join(removedTickers))

    return updatedTickerList







