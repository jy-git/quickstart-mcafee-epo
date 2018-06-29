#!/usr/bin/env python3
import boto3
import http.client
import urllib
import json
import uuid

s3 = boto3.resource('s3')

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
        bucket_names = event['ResourceProperties']['BucketNames']
        if event['RequestType'] == 'Delete':
            print(bucket_names)
            for bucket_name in bucket_names:
                bucket = s3.Bucket(bucket_name)
                print('deleting data from bucket %s' % bucket_name)
                bucket.objects.all().delete()
                print('deleting all versions of bucket %s' % bucket_name)
                bucket.object_versions.all().delete()
                if 'DeleteBucket' in event['ResourceProperties']:
                    print('deleting bucket %s' % bucket_name)
                    bucket.delete()
            
        send_response(event, response, status='SUCCESS', reason="Successfully cleanup data")
    except Exception as e:
        print(str(e))
        reason_str = "Failed to cleanup data, error: " + str(e)
        return send_response(event, response, status='FAILED', reason=reason_str)


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
