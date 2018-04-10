#!/usr/bin/env python3
# Invoked by: Cloudwatch scheduled events
# creates a backup AMI's with the running instance
import boto3
import os
import collections
import datetime
import time
import json

ec2_client = boto3.client('ec2')


def create_ami(instance_id, owner, stack_name, vpc_id, retention_days):
    try:
        print(instance_id, owner, stack_name, vpc_id, retention_days)
        timeStamp = time.time()
        timeStampString = datetime.datetime.fromtimestamp(timeStamp).strftime('%Y-%m-%d-%H-%M-%S')
        image_name = instance_id + '-' + timeStampString
        image = ec2_client.create_image(InstanceId=instance_id, Name=image_name, NoReboot=True)
        if 'ImageId' in image:
            image_id = image['ImageId']
            print('Retaining image %s of instance %s for %d days' % (image_id, instance_id,retention_days))
            delete_date = datetime.date.today() + datetime.timedelta(days=retention_days)
            delete_fmt = delete_date.strftime('%Y-%m-%d')
            print('Will delete %s on %s' % (image_id, delete_fmt))
            # below code is to create the name and current date as instance name
            ec2_client.create_tags( Resources=[image_id],
                Tags=[
                {'Key': 'DeleteOn', 'Value': delete_fmt},
                {'Key': 'Name', 'Value': image_name },
                {'Key': 'vpc-id', 'Value': vpc_id },
                {'Key': 'Owner', 'Value': owner },
                {'Key': 'InstanceID', 'Value': instance_id },
                {'Key': 'mcafee:cloudformation:stack-name', 'Value': stack_name}
                ]
            )
            return image_id
        else:
            print('Failed to create Image ')
    except Exception as e:
        print('Failed to create image for %s, %s' % (instance_id, str(e)))
        return None

def handler(event, context):
    print("Received event: " + json.dumps(event, indent=2))
    try:
        instance_id = event['InstanceID']
        stack_name = event['mcafee:cloudformation:stack-name']
        owner = event['Owner']
        vpc_id = event['VpcId']
        retention_days = int(event['RetentionPeriodInDays'])

        print('Create AMI backup request for EC2 instance %s' %(instance_id))
        image_id = create_ami(instance_id, owner, stack_name, vpc_id, retention_days)
        if None != image_id:
            print('Image created for %s instance ' % (instance_id))
        else:
            print('failed to create the image for %s instance ' % (instance_id))

    except Exception as e:
        print('Failed to create the AMI as backup %s' % (str(e)))
