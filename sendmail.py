#import urllib2
import os
import sys
import smtplib
import base64
import struct
import json
import cgi
import time
import os
import pickle
import logging.config
#from lxml import html, etree
from datetime import date, datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

###############################################################################
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGGER_CONF = os.path.join(BASE_DIR, 'logging.conf')

logging.config.fileConfig(LOGGER_CONF)
logger = logging.getLogger('comed')
###############################################################################
DEBUG = True

SEND_EMAIL = True

FROM          = 'Electricity Usage <admin@XXXXXXXXX.XX>'
TO_LEAK_FOUND = 'Hidden Pond <contact@XXXXXXXXX.XX>'
TO_NO_LEAK    = 'HP Admin <admin@XXXXXXXXX.XX>'
#TO_LEAK_FOUND = TO_NO_LEAK

LOGIN = 'admin@XXXXXXXXX.XX'
PASSWD = 'XXXXXXX'
SERVER = 'smtp.zoho.com'

PORT = 587


##############################################################################
def send_email(leak_found, text_message_list, html_message_list):
    try:
        new_text_msg = ""
        new_html_msg = ""

        if leak_found:
            new_text_msg = "Leaks found!\n"
            new_html_msg = "<b>Leaks found!\n"
        else:
            new_text_msg = "No leaks found.\n"
            new_html_msg = "<b>No leaks found.</b>\n"

        for msg in text_message_list:
            new_text_msg = new_text_msg + msg + "\n"

        for msg in html_message_list:
            new_html_msg = new_html_msg + msg + "\n"

        high_voltage_emoji = u"\U000026A1"
        emoji = high_voltage_emoji

        TO = TO_LEAK_FOUND if leak_found else TO_NO_LEAK

        msg = MIMEMultipart('alternative')
        msg['Subject'] = emoji + ' Electricity Usage ' + emoji if leak_found else 'No Electricity Leak!'
        msg['From'] = FROM
        msg['To'] = TO
        msg['Reply-To'] = FROM

        part1 = MIMEText(new_text_msg, 'plain')
        part2 = MIMEText(new_html_msg, 'html')

        msg.attach(part1)
        msg.attach(part2)

        logger.info('Connecting to {0}:{1} ...'.format(SERVER, PORT))
        s = smtplib.SMTP(SERVER, PORT)
        # s.set_debuglevel(1)
        s.ehlo()
        s.starttls()
        logger.info('Logging in ...')
        s.login(LOGIN, PASSWD)
        logger.info('Sending email ...')
        s.sendmail(FROM, [TO], msg.as_string())
        logger.info('Sent email!')
        s.quit()
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        exc = "{} at line {}".format(e, exc_tb.tb_lineno)
        logger.error(exc)

##############################################################################
def send_error_email(err_message_list):
    try:
        if len(err_message_list) < 1:
            return

        err_text_msg = ""
        err_html_msg = "<ul>"

        for msg in err_message_list:
            err_text_msg = err_text_msg + msg + "\n"
            err_html_msg = err_html_msg + "<li>" + msg + "</li>" + "\n"

        err_html_msg = err_html_msg + "</ul>"

        msg = MIMEMultipart('alternative')

        TO = TO_NO_LEAK

        msg['Subject'] = 'Electricity Leak script ERROR!'
        msg['From'] = FROM
        msg['To'] = TO
        msg['Reply-To'] = FROM

        part1 = MIMEText(err_text_msg, 'plain')
        part2 = MIMEText(err_html_msg, 'html')

        msg.attach(part1)
        msg.attach(part2)

        logger.info('Connecting to {0}:{1} ...'.format(SERVER, PORT))
        s = smtplib.SMTP(SERVER, PORT)
        # s.set_debuglevel(1)
        s.ehlo()
        s.starttls()
        logger.info('Logging in ...')
        s.login(LOGIN, PASSWD)
        logger.info('Sending email ...')
        s.sendmail(FROM, [TO], msg.as_string())
        logger.info('Sent email!')
        s.quit()
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        exc = "{} at line {}".format(e, exc_tb.tb_lineno)
        logger.error(exc)
