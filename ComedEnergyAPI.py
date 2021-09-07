import datetime
import json
import logging.config
import os
import platform
import pprint
import re
import requests
import urllib3
from http import HTTPStatus
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

###############################################################################
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGGER_CONF = os.path.join(BASE_DIR, 'logging.conf')

logging.config.fileConfig(LOGGER_CONF)
logger = logging.getLogger('comed')

VERIFY_SSL = True 
HOST = 'https://secure.comed.com'
TIMEOUT = 2
RETRY_COUNT = 20
###############################################################################

USER_AGENT='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.97 Safari/537.36'

# Class
class SessionData:
    session = None
    retry = None
    adapter = None
    samlResponse = None
    relayState = None
    authHeaders = None
    accountNumbers = list()
    accountAddresses = dict()

    def __init__(self):
        if not VERIFY_SSL:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.session = requests.Session()
        self.retry = Retry(total=None, connect=10, read=10, redirect=10, status=10, backoff_factor=0.5)
        self.adapter = HTTPAdapter(max_retries=self.retry)
        self.session.mount('http://', self.adapter)
        self.session.mount('https://', self.adapter)

    def __del__(self):
        if self.session:
            self.session.close()
            self.session = None
        if self.adapter:
            self.adapter.close()
            self.adapter = None
        self.reset()

    def reset(self):
        self.accountNumbers.clear()
        self.accountAddresses.clear()

# Method
def loginToComedAndAuthSAML(comedUsername, comedPassword, sessionData):
    loginData = {
        'USER': comedUsername,
        'PASSWORD': comedPassword,
    }

    loginHeaders = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'en-US,en;q=0.9',
        'Cache-Control': 'max-age=0',
        'Connection': 'keep-alive',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Host': 'secure.comed.com',
        'Origin': 'https://secure.comed.com',
        'Referer': 'https://secure.comed.com/Pages/Login.aspx',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': USER_AGENT
    }

    #urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    mySessionData = sessionData
    session = mySessionData.session

    # Login.
    adaptorURL = HOST + '/pages/adaptor.aspx'
    logger.debug("POSTing to {0}".format(adaptorURL))
    postResponse = session.post(adaptorURL, data=loginData, headers=loginHeaders, allow_redirects=True, verify=VERIFY_SSL)
    logger.debug('POST response URL: {0}'.format(postResponse.url))

    if re.search(r"invalidLogin=true", postResponse.url):
        raise Exception("invalid login")

    # Get configuration.
    getConfigurationURL = HOST + '/api/Services/MyAccountService.svc/GetConfiguration'
    logger.debug('GET url {0}'.format(getConfigurationURL))
    configResponse = session.get(getConfigurationURL, allow_redirects=True, verify=VERIFY_SSL, timeout=TIMEOUT)
    configInfo = json.loads(configResponse.text)
    EU_API_URL = configInfo['euApiUrl']
    EU_API_ROUTE_PREFIX = configInfo['euApiRoutePrefix']
    logger.debug("EU_API_URL: {0}, EU_API_ROUTE_PREFIX: {1}".format(EU_API_URL, EU_API_ROUTE_PREFIX))

    # Get session.
    getSessionURL = HOST + '/api/Services/MyAccountService.svc/GetSession'
    logger.debug('GET url {0}'.format(getSessionURL))
    sessionResponse = session.get(getSessionURL, allow_redirects=True, verify=VERIFY_SSL, timeout=TIMEOUT)
    sessionInfo = json.loads(sessionResponse.text)

    if not sessionInfo['isResidential']:
        raise Exception("the account for {} is not residential!".format(comedUsername))

    oauthToken = sessionInfo['token']

    """
    getWebUserNameURL = HOST + '/api/Services/MyAccountService.svc/GetWebUserName'
    logger.debug('GET url {0}'.format(getWebUserNameURL))
    userNameResponse = session.get(getWebUserNameURL, allow_redirects=True, verify=VERIFY_SSL)
    usernameInfo = json.loads(userNameResponse.text)
    logger.info('UserName: {0}'.format(usernameInfo))
    """

    # Get usage info.
    getUsageInfoURL = HOST + '/api/Services/MyAccountService.svc/GetUsageInfo'
    logger.debug('GET url {0}'.format(getUsageInfoURL))
    usageInfoResponse = session.get(getUsageInfoURL, allow_redirects=True, verify=VERIFY_SSL, timeout=TIMEOUT)
    usageInfo = json.loads(usageInfoResponse.text)['GetUsageInfoResult']

    if usageInfo['ErrorCode']:
        raise Exception(usageInfo['ErrorMessage'])

    ##pprint.pprint(usageInfo)

    authHeaders = {
        'Authorization' : 'Bearer ' + oauthToken,
        'Accept': 'application/json, text/plain, */*',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'en-US,en;q=0.9,pl;q=0.8',
        'Connection': 'keep-alive',
        'Cache-Control': 'max-age=0',
        'Host': 'secure.comed.com',
        'opco': 'ComEd',
        'Referer': 'https://secure.comed.com/MyAccount/MyBillUsage/pages/secure/ViewMyUsage.aspx',
        'User-Agent': USER_AGENT,
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-Mode': 'cors',
    }

    mySessionData.authHeaders = authHeaders

    accountsURL = HOST + '/.euapi/mobile/custom/auth/accounts'
    logger.debug('GET url: {0}'.format(accountsURL))
    accountsResponse = session.get(accountsURL, headers=authHeaders, allow_redirects=True, verify=VERIFY_SSL, timeout=TIMEOUT)
    accountsInfo = json.loads(accountsResponse.text)

    if not accountsInfo['success']:
        raise Exception("failed to get accounts info!")

    ##pprint.pprint(accountsInfo)

    datas = accountsInfo['data']
    for data in datas:
        accountNumber = data['accountNumber']
        address = data['address']
        customerNumber = data['customerNumber']
        isResidential = data['isResidential']
        isActive = data['status'] == 'Active'
        if isActive == False:
            raise Exception("account {0} is not active!".format(accountNumber))

        logger.info("Found account {0}, customer {1} at {2}!".format(accountNumber, customerNumber, address))

        mySessionData.accountNumbers.append(accountNumber)
        mySessionData.accountAddresses[accountNumber] = address

    return mySessionData

# Method
def getAccountInfo(sessionData, accountNumber):
    session = sessionData.session
    authHeaders = sessionData.authHeaders

    viewAccountHeaders = {
        'Accept' : 'application/json, text/plain, */*',
        'Accept-Encoding' : 'gzip, deflate, br',
        'Accept-Language' : 'en-US,en;q=0.9',
        'Cache-Control': 'max-age=0',
        'Connection': 'keep-alive',
        'Content-Type' : 'application/json;charset=UTF-8',
        'Host': 'secure.comed.com',
        'opco': 'ComEd',
        'Origin': 'https://secure.comed.com',
        'Referer': 'https://secure.comed.com/Pages/ChangeAccount.aspx',
        'Sec-Fetch-Dest' : 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': USER_AGENT
    }

    viewAccountData = json.dumps({
        'accountNumber': accountNumber 
    })

    viewAccountURL = HOST + "/api/Services/AccountList.svc/ViewAccount"
    logger.debug("POSTing to {0}".format(viewAccountURL))
    viewAccountResponse = session.post(viewAccountURL, data=viewAccountData, headers=viewAccountHeaders, allow_redirects=True, verify=VERIFY_SSL)
    viewAccountInfo = json.loads(viewAccountResponse.text)
    assert not viewAccountInfo['isPasswordProtected'], "account is password protected"

    accountURL = HOST + "/.euapi/mobile/custom/auth/accounts/" + accountNumber
    logger.debug("GET url: {0}".format(accountURL))
    accountResponse = session.get(accountURL, headers=authHeaders, allow_redirects=True, verify=VERIFY_SSL, timeout=TIMEOUT)
    accountInfo = json.loads(accountResponse.text)

    if accountInfo['success'] is not True:
        pprint.pprint(accountInfo)
        raise Exception("Account {} info response failed".format(accountNumber))

    accountInfoData = accountInfo['data']
    amiAccountId = accountInfoData['amiAccountIdentifier']
    amiCustomerId = accountInfoData['amiCustomerIdentifier']
    addressLine = accountInfoData['addressLine']
    city = accountInfoData['city']
    state = accountInfoData['state']
    zipCode = accountInfoData['zipCode']

    # Go to energy use URL for the account.
    energyUseURL = 'https://cec.opower.com/ei/x/e/energy-use-details?utilityCustomerId=' + amiAccountId
    energyUseResponse = retryGet(session, energyUseURL, 'Energy Use URL')
    if energyUseResponse.status_code != HTTPStatus.OK:
        logger.error("energy-use-details response code {}, URL {}".format(energyUseResponse.status_code,energyUseResponse.url))

    # this will redirect to a url like:
    # https://secure.comed.com/Pages/spsso.aspx?SAMLRequest=asdf
    samlRequestURL = energyUseResponse.url
    samlRequestResponse = retryGet(session, samlRequestURL, 'SAML request URL')

    # need to pull the SAMLResponse and RelayState from the request response so we can use it in the next one
    samlResponse = samlRequestResponse.text.split("SAMLResponse:'")[1].split("'")[0]
    relayState = samlRequestResponse.url.split('&')[-1].split('=')[1]

    data = {
        'SAMLResponse': samlResponse,
        'RelayState': relayState
    }

    # this will authenticate the session
    samlURL = 'https://sso2.opower.com/sp/ACS.saml2'
    samlPostResponse = retryPost(session, samlURL, data, "SAML auth URL")

    utilityAccountUuid = amiAccountId
    try:
        result = re.search(r"uuid.*?\"(?P<uuid>[\d\w-]+)\"", samlPostResponse.text, re.DOTALL)
        utilityAccountUuid = result.group('uuid')
        logger.debug('found Utility Account UUID: {0}'.format(utilityAccountUuid))
    except Exception as e:
        logger.error(e)

    # return the auth'd session so it can be used for other requests
    return utilityAccountUuid

# Method
def retryGet(session, url, desc, params=None):
    keepTrying = True
    retryCount = 0
    response = dict() 
    while keepTrying:
        try:
            logger.debug("GET url: {0}".format(url))
            response = session.get(url, params=params, allow_redirects=True, verify=VERIFY_SSL, timeout=2)
            keepTrying = False
        except Exception as e:
            retryCount += 1
            if retryCount > 10:
                raise e
            logger.error("connection to {} timed out! re-trying {} ...".format(desc, retryCount))
    return response

# Method
def retryPost(session, url, data, desc):
    keepTrying = True
    retryCount = 0
    response = dict() 
    while keepTrying:
        try:
            logger.debug("POST url: {0}".format(url))
            response = session.post(url, data=data, verify=VERIFY_SSL, timeout=2)
            keepTrying = False
        except Exception as e:
            retryCount += 1
            if retryCount > RETRY_COUNT:
                raise e
            logger.error("connection to {} timed out! re-trying {} ...".format(desc, retryCount))
    return response

# Method
def sendUsageRequest(sessionData, accountNumber, startDate, endDate, dataPeriod, utilityAccountUuid):
    authedSession = sessionData.session

    startDateStr = datetime.datetime.strftime(startDate, '%Y-%m-%dT%H:00+0000')
    endDateStr = datetime.datetime.strftime(endDate, '%Y-%m-%dT%H:00+0000')

    requestParams = {
        'startDate': startDateStr,
        'endDate': endDateStr,
        'aggregateType': dataPeriod, # hour, day, bill
        'includePtr':'false' 
    }

    host = 'https://cec.opower.com'
    #url = '/ei/edge/apis/DataBrowser-v1/cws/cost/utilityAccount/'
    url = '/ei/edge/apis/DataBrowser-v1/cws/usage/utilityAccount/'

    requestDataURL = '{0}{1}{2}'.format(host, url, utilityAccountUuid)
    response = retryGet(authedSession, requestDataURL, desc="Request Data URL", params=requestParams)

    responseJson = {'error' : {'details' : response.text}}

    try:
        responseJson = json.loads(response.text)
    except Exception as e:
        logger.error(e)

    return responseJson

# Method
def logOut(sessionData):
    try:
        logger.debug("logging out ...")
        logoutURL = HOST + '/api/Services/MyAccountService.svc/Logout'
        logoutResponse = retryPost(sessionData.session, logoutURL, data=None, desc="Logout URL")
        if not logoutResponse.text:
            logger.error("log out failed: {}".format(logoutResponse.text))
        logger.debug("logged out")
    except Exception as e:
        logger.error(e)
