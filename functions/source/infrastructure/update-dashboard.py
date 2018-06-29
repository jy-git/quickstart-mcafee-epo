#!/usr/bin/env python3
# Invoked by: Cloudformation custom actions
# Returns: Error or status message
#
# updates the AWS CloudWatch dashboard
import boto3
import http.client
import urllib
import json
import uuid
import re
from botocore.exceptions import ClientError

cloudwatch = boto3.client('cloudwatch')

#def validate_user_data(user_data):

def render_dashboard_template(user_data):
    s3 = boto3.client('s3')
    response = s3.get_object(Bucket=user_data['SourceBucket'], Key=user_data['DashboardPath'])
    dashboard_body = response['Body'].read().decode('utf-8')

    dashboard_body = re.sub('@qss3bucket@', user_data['SourceBucket'], dashboard_body)
    dashboard_body = re.sub('@qss3keyprefix@', user_data['KeyPrefix'], dashboard_body)

    dashboard_body = re.sub('@epo_elb_name@', user_data['EPOELBName'], dashboard_body)
    dashboard_body = re.sub('@epo_console_url@', user_data['EPOConsoleURL'], dashboard_body)

    dashboard_body = re.sub('@region@', user_data['Region'], dashboard_body)
    dashboard_body = re.sub('@stack_name@', user_data['ParentStack'], dashboard_body)
    dashboard_body = re.sub('@public_hosted_zone_id@', user_data['HostedZoneID'], dashboard_body)
    dashboard_body = re.sub('@datastore_bucket_name@', user_data['DatastoreBucketName'], dashboard_body)


    # e.g https://us-west-2.console.aws.amazon.com/cloudformation/home?region=us-west-2#/stacks?filter=active&stackId=arn:aws:cloudformation:us-west-2:811797731536:stack%2Fpsdashboard%2F419bb9c0-442a-11e8-99ac-50a68a0e328e
    stack_url = 'https://' + user_data['Region'] + '.console.aws.amazon.com/cloudformation/home?region=' + user_data['Region'] + '#/stacks?filter=active&stackId=' + user_data['ParentStackID']
    dashboard_body = re.sub('@stack_url@', stack_url, dashboard_body)

    dashboard_body = re.sub('@epo_system_check_alarm_arn@', user_data['EPOSystemCheckAlarmARN'], dashboard_body)
    dashboard_body = re.sub('@epo_status_check_alarm_arn@', user_data['EPOStatusCheckAlarmARN'], dashboard_body)
    dashboard_body = re.sub('@epo_instance_id@', user_data['EPOInstanceID'], dashboard_body)

    dashboard_body = re.sub('@ah_elb_name@', user_data['AHELBName'], dashboard_body)
    dashboard_body = re.sub('@ah_asg_name@', user_data['AHASGName'], dashboard_body)
    dashboard_body = re.sub('@ah_scaling_alarm_arn@', user_data['AHScaleAlarmARN'], dashboard_body)

    dashboard_body = re.sub('@rds_instance_id@', (user_data['DBInstanceIdentifier']).lower(), dashboard_body)

    dashboard_body = re.sub('@dxl_elb_name@', user_data['DXLELBName'], dashboard_body)
    dashboard_body = re.sub('@dxl_asg_name@', user_data['DXLASGName'], dashboard_body)
    dashboard_body = re.sub('@dxl_scaling_alarm_arn@', user_data['DXLScaleAlarmARN'], dashboard_body)

    dashboard_body = re.sub('@stack_az_1@', user_data['AvailabilityZone1'], dashboard_body)
    dashboard_body = re.sub('@stack_az_2@', user_data['AvailabilityZone2'], dashboard_body)

    return dashboard_body

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
        user_data = event['ResourceProperties']
        if event['RequestType'] == 'Delete':
            return send_response(event,response, status='SUCCESS', reason="")
        elif event['RequestType'] == 'Update' or event['RequestType'] == 'Create':
            dashboard_body = render_dashboard_template(user_data)
            result = cloudwatch.put_dashboard(DashboardName=user_data['DashboardName'], DashboardBody=dashboard_body)
            print(result)
            return send_response(event, response, status='SUCCESS', reason="Successfully updated the details of dashboard")
        else:
            return send_response(event, response, status='FAILED', reason="Invalid request type")
    except ClientError as e:
        print(str(e))
        return send_response(event, response, status='SUCCESS', reason="was not able to update dashboard")

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
