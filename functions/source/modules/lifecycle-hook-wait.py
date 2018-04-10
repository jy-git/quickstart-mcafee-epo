#!/usr/bin/env python3
import boto3
import http.client
import urllib
import json
import uuid
import time

client = boto3.client('autoscaling')


# Wait max 3 mints
def waitForInstanceCountToZero(asg_name):
    count = 18
    while --count:
        groups = client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
        for grp in groups['AutoScalingGroups']:
            instances = grp['Instances']
            inst_count = len(instances)
            if inst_count == 0:
                return 0
        time.sleep(10)        
    else:
        return 1

def handler(event, context):
    response = {
        'StackId': event['StackId'],
        'RequestId': event['RequestId'],
        'LogicalResourceId': event['LogicalResourceId'],
        'Status': 'SUCCESS'
    }
    if 'PhysicalResourceId' in event:
        response['PhysicalResourceId'] = event['PhysicalResourceId']
    else:
        response['PhysicalResourceId'] = str(uuid.uuid4())

    try:
        print(event)
        #return send_response(event, response, status='SUCCESS', reason="Successfully got details of RDS instance identifier")

        if event['RequestType'] == 'Delete' or event['RequestType'] == 'Create':
            return send_response(event,response, status='SUCCESS', reason="")
        elif event['RequestType'] == 'Update':
            try:
                asg_name = event['OldResourceProperties']['AutoScalingGroupName']
                result = client.update_auto_scaling_group(AutoScalingGroupName=asg_name, MinSize=0, MaxSize=0, DesiredCapacity=0)
                print(result)
                if result['ResponseMetadata']['HTTPStatusCode'] == 200:
                    ret = waitForInstanceCountToZero(asg_name)
                    if ret == 0:
                        return send_response(event, response, status='SUCCESS', reason="Successfully set min/max/desired for old ASG")
                    else:
                        return send_response(event, response, status='FAILED', reason="Tiemout on get instance count")
                else:
                    return send_response(event, response, status='FAILED', reason="Failed to set ASG min/max/desired for old ASG")
            except Exception as e:
                print(response)
                print(str(e))
                return send_response(event, response, status='FAILED', reason="Exception on execution")
        else:
            return send_response(event, response, status='FAILED', reason="Invalid request type")
    except Exception as e:
        print(str(e))
        return send_response(event, response, status='FAILED', reason="Main Exception.")


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
