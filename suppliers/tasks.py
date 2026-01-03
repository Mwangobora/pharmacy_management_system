from time import sleep
from celery import shared_task

@shared_task
def notify_customer(message):
    print("sending 10K emails...")
    sleep(10)
    print("emails sent to customer with message:", message)