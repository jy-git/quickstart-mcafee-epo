#!/usr/bin/env python3
# Invoked by: Code Pipeline
# Returns: Error or status message
#
# sends an update email to the user
# This should always callback to the CodePipeline API to indicate success or failure

import boto3
import os
import zipfile
import json
import uuid
from botocore.client import Config
import re

code_pipeline = boto3.client('codepipeline')

def put_job_success(job_id, message):
    print('Putting job success')
    code_pipeline.put_job_success_result(jobId=job_id)

def put_job_failure(job_id, message):
    print('Putting job failure')
    code_pipeline.put_job_failure_result(jobId=job_id,failureDetails={'message': message, 'type': 'JobFailed'})


def get_user_data(job_data):
    try:
        user_data = json.loads(job_data['actionConfiguration']['configuration']['UserParameters'])
    except Exception as e:
        raise Exception('UserParameters could not be decoded as JSON')
    if 'SenderEmailAddress' not in user_data:
        raise Exception('UserData JSON must include the SenderEmailAddress')
    if 'ToEmailAddresses' not in user_data:
        raise Exception('UserData JSON must include the ToEmailAddresses')
    if 'CcEmailAddress' not in user_data:
        raise Exception('UserData JSON must include the CcEmailAddress')
    if 'SourceBucket' not in user_data:
        raise Exception('UserData JSON must include the SourceBucket')
    if 'Prefix' not in user_data:
        raise Exception('UserData JSON must include the Prefix')
    if 'HTMLEmailSourceKey' not in user_data:
        raise Exception('UserData JSON must include the HTMLEmailSourceKey')
    if 'ComponentsJSONFile' not in user_data:
        raise Exception('UserData JSON must include the ComponentsJSONFile')
    return user_data

def download_message(user_data):
    s3 = boto3.client('s3')

    key = user_data['Prefix'] + user_data['HTMLEmailSourceKey']
    response = s3.get_object(Bucket=user_data['SourceBucket'], Key=key)
    message = response['Body'].read().decode('utf-8')

    key = user_data['Prefix'] + user_data['ComponentsJSONFile']
    response = s3.get_object(Bucket=user_data['SourceBucket'], Key=key)
    components = json.loads(response['Body'].read().decode('utf-8'))

    print(components)
    ssm = boto3.client('ssm')
    parameter_store_identifier = user_data['ParameterStoreIdentifier']

    message = re.sub('@url.mcafee.pipeline.console@', user_data['PipelineURL'], message)
    for key in components:
        response = ssm.get_parameter(Name=parameter_store_identifier+'/buildinfo/'+key)
        print(response)
        if 'epo' != key.lower():
            message = re.sub("@"+key.lower()+".buildversion.from@", response['Parameter']['Value'], message)
            message = re.sub("@"+key.lower()+".buildversion.to@", components[key]['BuildVersion'], message)

        ssm.put_parameter(Name=parameter_store_identifier+'/buildinfo/'+key,Description=components[key]['Name']+' version',Value=components[key]['BuildVersion'],Type='String', Overwrite=True)

    return message

def get_email_address_list(email_address):
    email_address_list = []
    if email_address: # if email_address is not empty string or empty list
        email_address_list.append(email_address)
    return email_address_list

def send_email(sender_address, to_addresses, cc_addresses, subject, message):
    charset = 'UTF-8'
    ses = boto3.client('ses', region_name='us-west-2')
    response = ses.send_email(
        Destination={
            'ToAddresses': get_email_address_list(to_addresses),
            'CcAddresses': get_email_address_list(cc_addresses),
        },
        Message={
            'Body': {
                'Html': {
                    'Charset': charset,
                    'Data': message,
                }
            },
            'Subject': {
                'Charset': charset,
                'Data': subject,
            },
        },
        Source=sender_address
    )

def email_handler(job_data):
    #print(event)
    # handle all the email notification error but never pass it down , no reason to fail the whole stack of it
    try:
        message = ''
        subject = 'McAfee ePO On Public Cloud - Updated'
        # Extract the user data
        user_data = get_user_data(job_data)
        message = download_message(user_data)
        send_email(user_data['SenderEmailAddress'], user_data['ToEmailAddresses'], user_data['CcEmailAddress'], subject, message)
    except Exception as e:
        print('failed to send email to reciepents')
        print(str(e))


def handler(event, context):
    try:
        print(event)
        print('Starting post update actions')
        # Extract the Job ID
        job_id = event['CodePipeline.job']['id']

        # Extract the Job Data
        job_data = event['CodePipeline.job']['data']

        # pass it to email handler
        email_handler(job_data)

        put_job_success(job_id, '')
        return 'Done'
    except Exception as e:
        print('Function failed due to exception.')
        print(str(e))
        put_job_failure(job_id, 'Function exception: ' + str(e))
