import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from os import path

if path.exists("./scraper-mail-password"):
    file = open("./scraper-mail-password", "r")
    password = file.read()
    file.close()
else:
    home = path.expanduser("~")
    file = open(home + "/project/kiwizzle/kiwizzle-credentials/scraper-mail-password", "r")
    password = file.read()
    file.close()


def send_mail(title, mail_content):
    title = "kiwizzle-api:" + title
    # The mail addresses and password
    sender_address = 'rlatjdwns1020@gmail.com'
    receiver_address = 'zbvs12@gmail.com'
    # Setup the MIME
    message = MIMEMultipart()
    message['From'] = sender_address
    message['To'] = receiver_address
    message['Subject'] = title
    # The body and the attachments for the mail
    message.attach(MIMEText(mail_content, 'plain'))
    # Create SMTP session for sending the mail
    session = smtplib.SMTP('smtp.gmail.com', 587)  # use gmail with port
    session.starttls()  # enable security
    session.login(sender_address, password)  # login with mail_id and password
    text = message.as_string()
    session.sendmail(sender_address, receiver_address, text)
    session.quit()
