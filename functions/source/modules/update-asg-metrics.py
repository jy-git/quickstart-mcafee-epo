#!/usr/bin/env python3
# Invoked by: Cloudformation custom actions
# Returns: Error or status message
#
# setups the ASG details
import boto3
import http.client
import urllib
import json
import uuid
from botocore.exceptions import ClientError

def validate_user_data(user_data):
    if 'AutoScalingGroupName' not in user_data:
        raise Exception('UserData  must include the AutoScalingGroupName')
    if 'DesiredCapacity' not in user_data:
        raise Exception('UserData  must include the DesiredCapacity')
    if 'MaxSize' not in user_data:
        raise Exception('UserData must include the MaxSize')
    if 'MinSize' not in user_data:
        raise Exception('UserData must include the MinSize')
    if 'HealthCheckGracePeriod' not in user_data:
        raise Exception('UserData must include the HealthCheckGracePeriod')

def update_asg_details(user_data):
    client = boto3.client('autoscaling')
    print('Updating ASG %s with details' % (user_data['AutoScalingGroupName']))
    response = client.update_auto_scaling_group(AutoScalingGroupName=user_data['AutoScalingGroupName'],
                                                MinSize=(int)(user_data['MinSize']),
                                                MaxSize=(int)(user_data['MaxSize']),
                                                DesiredCapacity=(int)(user_data['DesiredCapacity']),
                                                HealthCheckGracePeriod=(int)(user_data['HealthCheckGracePeriod']))
    if None != response:
        print('ASG %s updated with passed details' %  (user_data['AutoScalingGroupName']))
    else:
        print('Failed to update %s ASG with passed details' % (user_data['AutoScalingGroupName']))


def send_response(request, response, status=None, reason=None):
    if status is not None:
        response['Status'] = status

    if reason is not None:
        response['Reason'] = reason

    if 'ResponseURL' in request and request['ResponseURL']:
        try:
            url= urllib.parse.urlparse(request['ResponseURL'])
            body = json.dumps(response)
            https = http.client.HTTPSConnection(url.hostname)
            https.request('PUT', url.path + '?' + url.query, body)
        except Exception as e:
            print(str(e))
            print('Failed to send the response to the provdided URL')

def handler(event, context):
    response = {
        'StackId': event['StackId'],
        'RequestId': event['RequestId'],
        'LogicalResourceId': event['LogicalResourceId'],
        'Status': 'SUCCESS'
    }

    print('Performing Action %s' % (event['RequestType']))
    if 'PhysicalResourceId' in event:
        response['PhysicalResourceId'] = event['PhysicalResourceId']
    else:
        response['PhysicalResourceId'] = str(uuid.uuid4())

    try:
        user_data = event['ResourceProperties']
        validate_user_data(user_data)
        print(user_data)
        if 'Delete' == event['RequestType'] :
            return send_response(event,response, status='SUCCESS', reason='Nothing to do for delete')
        elif event['RequestType'] == 'Update' or event['RequestType'] == 'Create':
            update_asg_details(user_data)
            return send_response(event, response, status='SUCCESS', reason='Successfully updated ASG with requested details')
        else:
            raise Exception('Invalid Request Type.')
    except ClientError as e:
        print(str(e))
        return send_response(event, response, status='FAILED', reason='failed to update ASG details')
