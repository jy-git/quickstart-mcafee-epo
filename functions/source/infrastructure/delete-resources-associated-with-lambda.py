#!/usr/bin/env python3
# Invoked by: Cloudformation custom actions
# Returns: Error or status message
#
# deletes the resources assocated with lambda like eni
import boto3
import http.client
import urllib
import json
import uuid
import threading
from time import sleep

def handler(event, context):
    print(event)
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
        if event['RequestType'] == 'Delete':
            user_data = event['ResourceProperties']
            # setup ec2 client
            ec2client = boto3.client('ec2')

            # loop through all ENI's in the Security Group send by CloudFormation
            enis = ec2client.describe_network_interfaces(Filters=[{'Name': 'group-id','Values': [user_data['SecurityGroup']]}])
            for eni in enis['NetworkInterfaces']:
                print('ENI description : '+eni['Description'])
                # We only care about ENI's created by Lambda
                if eni['Description'].startswith('AWS Lambda VPC ENI: '):

                    # Check if the eni is still attached and attempt to detach
                    if 'Attachment' in eni.keys():
                        print('Detaching ENI...')
                        ec2client.detach_network_interface(AttachmentId=eni['Attachment']['AttachmentId'])
                        print(ec2client.describe_network_interfaces(NetworkInterfaceIds=[eni['NetworkInterfaceId']])['NetworkInterfaces'][0].keys())
                        # Max wait for 5 minutes
                        retry_attempts = 0
                        while (retry_attempts < 30)  and 'Attachment' in ec2client.describe_network_interfaces(NetworkInterfaceIds=[eni['NetworkInterfaceId']])['NetworkInterfaces'][0].keys():
                          print('eni still attached, waiting 10 seconds...')
                          sleep(10)
                          retry_attempts += 1

                        # Delete the eni
                        print('Deleting ENI %s' % eni['NetworkInterfaceId'])
                        ec2client.delete_network_interface(NetworkInterfaceId=eni['NetworkInterfaceId'])

            return send_response(event, response, status='SUCCESS', reason='Successfully deleted the resources associated with lambda')
        else:
            return send_response(event, response, status='SUCCESS', reason="Nothing to do for request type other than delete")
    except Exception as e:
        print(str(e))
        return send_response(event, response, status='SUCCESS', reason="Failed to delete resources associated with lambda")

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
            print("Failed to send the response to the provdided URL")
