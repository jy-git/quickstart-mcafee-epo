#!/usr/bin/env python3
import boto3
import http.client
import urllib
import json
import uuid

ssm = boto3.client('ssm')

def validate_user_data(user_data):
    if 'EPOImageIdParam' not in user_data:
        raise Exception('UserData JSON must include the EPOImageIdParam')
    if 'EPOInstanceTypeParam' not in user_data:
        raise Exception('UserData JSON must include the EPOInstanceTypeParam')
    if 'EPOInstanceSizeParam' not in user_data:
        raise Exception('UserData JSON must include the EPOInstanceSizeParam')
    if 'UsePreviousValue' not in user_data:
        raise Exception('UserData JSON must include the UsePreviousValue')
    if 'PassedParameters' not in user_data:
        raise Exception('UserData JSON must include the PassedParameters')


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

def delete_parameter(name):
    try:
        ssm.delete_parameter(Name=name)
    except Exception as e:
        print(str(e))
        print('Failed to delete image id for epo in parameter store')

def update_parameter(name, description, value, type):
    try:
        ssm.put_parameter(Name=name,Description=description,Value=value,Type=type, Overwrite=True)
    except Exception as e:
        print('Failed to update image id for epo in parameter store')

def get_parameter(name):
    try:
        response = ssm.get_parameter(Name=name)
        if 'Parameter' in response:
            return response['Parameter']['Value']
        return None
    except Exception as e:
        print('Parameter %s not found in parameter store' %(name))
        return None

def sync_instance_parameters(user_data):
    new_params = json.loads(user_data['PassedParameters'])
    # Note - we are only overriding as of now ePO Image ID as this is the only reason it will replace the EPOInstance, thats the theory
    image_id = get_parameter(user_data['EPOImageIdParam'])
    if None == image_id:
        update_parameter(user_data['EPOImageIdParam'], 'Used EPO Image Id', new_params['EPOImageId'], 'String')
    else:
        new_params['EPOImageId'] = image_id
    return new_params

def handler(event, context):
    print("Received event: " + json.dumps(event, indent=2))
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
        if event['RequestType'] == 'Delete':
            delete_parameter(user_data['EPOImageIdParam'])
            return send_response(event,response, status='SUCCESS', reason="Successfully deleted EPO Image ID from paramstore")
        elif event['RequestType'] == 'Update' or event['RequestType'] == 'Create':
            # If UsePreviousValue is 1 which means use it from existing
            if "0" != user_data['UsePreviousValue']:
                new_params = sync_instance_parameters(user_data)

            response['Data'] = {'EPOImageId': new_params['EPOImageId'], 'EPOInstanceType': new_params['EPOInstanceType'], 'EPOInstanceSize': new_params['EPOInstanceSize']}
            print(response['Data'])
            return send_response(event, response, status='SUCCESS', reason="Successfully synced of ePO Instance parameters")
        else:
            raise Exception('Invalid Request Type.')
    except Exception as e:
        print(str(e))
        return send_response(event, response, status='FAILED', reason="Failed to sync ePO instance parameters")
