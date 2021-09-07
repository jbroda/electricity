import datetime
import os
import sys
import pprint
import re
import logging.config
import ComedEnergyAPI
import sendmail 
from datetime import date, datetime, timedelta

###############################################################################
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LOGGER_CONF = os.path.join(BASE_DIR, 'logging.conf')
CRED_FILE = os.path.join(BASE_DIR, 'cred.txt')
NBSP = '&nbsp;'
MAX_NORMAL_USAGE = 100

logging.config.fileConfig(LOGGER_CONF)
logger = logging.getLogger('comed')
###############################################################################

# Fix timezone
def fix_tz(d):
    if ":" == d[-3:-2]:
        d = d[:-3]+d[-2:]
    return d

# Method
def main():
    try:
        sessionData = ComedEnergyAPI.SessionData()

        isLeakFound = False

        text_message_list = list()
        html_message_list = list()
        error_message_list = list()

        creds = open(CRED_FILE).readlines()

        for cred in creds:
            if re.match('^#', cred):
                continue

            (comedUser, comedPwd) = cred.strip().split(':')

            # Login to ComEd.
            try:
                logger.info("Connecting with user '{0}' ...".format(comedUser))
                ComedEnergyAPI.loginToComedAndAuthSAML(comedUser, comedPwd, sessionData)
            except Exception as e:
                exc_type, exc_obj, exc_tb = sys.exc_info()
                exc = "{} at line {}".format(e, exc_tb.tb_lineno)
                logger.error(exc)
                error_message_list.append("Failed to login with {}: {}".format(comedUser, exc))
                continue

            # Use the last 36 hours.
            now = datetime.now()
            startDate = now - timedelta(hours=24*3)
            endDate = now
            dataPeriod = 'hour'

            for accountNumber in sessionData.accountNumbers:
                accountAddress = sessionData.accountAddresses[accountNumber]

                logger.debug("processing account {0} at {1}".format(accountNumber, accountAddress))

                try:
                    utilityAccountUuid = ComedEnergyAPI.getAccountInfo(sessionData, accountNumber)
                except Exception as e:
                    exc_type, exc_obj, exc_tb = sys.exc_info()
                    exc = "{} at line {}".format(e, exc_tb.tb_lineno)
                    logger.error(exc)
                    error_message_list.append("Failed to get usage for account {} with {}: {}".format(accountNumber, comedUser, exc))
                    continue

                usageJson = ComedEnergyAPI.sendUsageRequest(
                    sessionData, accountNumber, startDate, endDate, dataPeriod, utilityAccountUuid)

                #pprint.pprint(usageJson)

                if 'error' in usageJson:
                    details = usageJson['error']['details']
                    logger.error(details)
                    error_message_list.append("Failed to get usage at {}: {}".format(accountAddress, details))
                    continue

                totalUsage = 0.0
                unit = usageJson['unit']

                readStartTime = 0
                readEndTime = 0

                reads = usageJson['reads']

                if len(reads) < 1:
                    no_reads_msg = "There are no reads at {} between {} and {}".format(accountAddress, startDate, endDate)
                    logger.info(no_reads_msg)
                    error_message_list.append(no_reads_msg)
                    continue

                for data in reads:
                    startTime = datetime.strptime(fix_tz(data['startTime']), '%Y-%m-%dT%H:%M:%S.%f%z')
                    endTime   = datetime.strptime(fix_tz(data['endTime']), '%Y-%m-%dT%H:%M:%S.%f%z')

                    readStartTime = startTime if readStartTime == 0 else readStartTime
                    readEndTime = endTime

                    usage = float(data['value'])
                    totalUsage = totalUsage + usage
                    logger.debug("usage {} {}, start {}, end {}, diff {}".format(usage, unit, startTime, endTime, endTime - startTime))


                logger.info("Account {} total usage {} {} between {} and {}".
                    format(accountNumber, round(totalUsage,2), unit, readStartTime, readEndTime))

                isAlarm = totalUsage > MAX_NORMAL_USAGE

                isLeakFound = isLeakFound or isAlarm

                # Text
                startTag = lambda isAlarm : "_" if isAlarm else ""
                endTag   = lambda isAlarm : "_" if isAlarm else ""

                textAccountAddress = ' '.join(accountAddress.split()[:2])
                textAccountAddress = "{:>16}".format(textAccountAddress)

                text_message_list.append("{}{:06.2f}{} {} at {} from {:%a, %b %d, %Y at %H:%M %p} to {:%a, %b %d, %Y at %H:%M %p}".
                    format(startTag(isAlarm), round(totalUsage,2), endTag(isAlarm), unit, textAccountAddress, readStartTime, readEndTime))

                # HTML
                startTag = lambda isAlarm : "<b><font color='red'>" if isAlarm else "<b>"
                endTag   = lambda isAlarm : "</b></font>"           if isAlarm else "</b>"

                htmlAccountAddress = ' '.join(accountAddress.split()[:2])
                htmlAccountAddress = "{:>16}".format(htmlAccountAddress).replace(" ", NBSP)

                html_message_list.append("<li>{}{:06.2f}{} {} at {} from {:<b>%a, %b %d, %Y</b> at %H:%M %p} to {:<b>%a, %b %d, %Y</b> at %H:%M %p}</li>".
                    format(startTag(isAlarm), round(totalUsage,2), endTag(isAlarm), unit, htmlAccountAddress, readStartTime, readEndTime))

            # Log out from ComEd.
            ComedEnergyAPI.logOut(sessionData)

            sessionData.reset()

        # Text
        text_message_list.sort(reverse=True)

        # HTML
        html_message_list.sort(reverse=True)
        html_message_list.insert(0, "<tt><ol>")
        html_message_list.append("</ol></tt>")

        logger.info("sending report email ...")
        sendmail.send_email(isLeakFound, text_message_list, html_message_list)

        logger.info("sending error report email ...")
        sendmail.send_error_email(error_message_list)

    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        exc = "{} at line {}".format(e, exc_tb.tb_lineno)
        logger.error(exc)
        errors = list()
        errors.append(str(exc))
        sendmail.send_error_email(errors)

if __name__ == "__main__":
    start_dt = datetime.now()
    main()
    end_dt = datetime.now()
    elapsed = end_dt - start_dt
    logger.info("running time: {0} sec".format(elapsed.seconds))
