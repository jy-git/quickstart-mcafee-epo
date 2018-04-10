#!/usr/bin/env python3
# Invoked by: Cloudwatch scheduled events
# delets the images associated with ec2 instance_id
import boto3
import os
import collections
import datetime
import re
import json

ec2_client = boto3.client('ec2')

#begins lambda function
def handler(event, context):
    try:
        instance_id = event['InstanceID']
        owner = event['Owner']
        vpc_id = event['VpcId']
        stack_name = event['mcafee:cloudformation:stack-name']

        print('delete image schedule with filters instance_id %s  vpc_id %s' % (instance_id, vpc_id))
        iam = boto3.client('iam')

        account_ids = list()
        try:
            iam.get_user()
        except Exception as e:
            # use the exception message to get the account ID the function executes under
            account_ids.append(re.search(r'(arn:aws:sts::)([0-9]+)', str(e)).groups()[1])

        print(account_ids)
        delete_on = datetime.date.today().strftime('%Y-%m-%d')
        filters = [
            {'Name': ('tag' + ':' + 'DeleteOn'), 'Values': [delete_on]},
            {'Name':  ('tag' + ':' + 'InstanceID'), 'Values': [instance_id]},
            {'Name':  ('tag' + ':' + 'Owner'), 'Values': [owner]},
            {'Name': ('tag' + ':' + 'vpc-id'), 'Values': [vpc_id]},
            {'Name': ('tag' + ':' + 'mcafee:cloudformation:stack-name'), 'Values': [stack_name]}
        ]
        images_response = ec2_client.describe_images(Owners=account_ids, Filters=filters)
        for image in images_response['Images']:
            print('deleting image %s' % image['ImageId'])
            ec2_client.deregister_image(ImageId=image['ImageId'])
    except Exception as e:
        print('Function failed due to exception.')
        print(str(e))
