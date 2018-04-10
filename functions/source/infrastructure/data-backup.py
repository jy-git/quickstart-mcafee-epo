#!/usr/bin/env python3
import boto3
import os
import datetime

cw_logs = boto3.client('logs')

def handler(event, context):
    try:
        destination_bucket = os.environ['DATA_BACKUP_DESTINATION']
        stack_name = os.environ['STACK_NAME']

        current_time = datetime.datetime.utcnow()
        current_time_str = current_time.strftime("%Y%m%d%H%M%S")
        task_name = event['Type'] + '_LogBackup_' + current_time_str
        destination_prefix = 'logs/' + event['Type']+ '/' + current_time_str

        current_time_int = int((datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)).total_seconds() * 1000)
        from_time_int = int((datetime.datetime.utcnow() - datetime.timedelta(hours = 24) - datetime.datetime(1970, 1, 1)).total_seconds() * 1000)

        params = {
             'taskName': task_name,
             'logGroupName': event['LogGroupName'],
             'fromTime': from_time_int,
             'to': current_time_int,
             'destination': destination_bucket,
             'destinationPrefix': destination_prefix
         }

        response = cw_logs.create_export_task(**params)
        print(response)
    except Exception as e:
        print(str(e))
