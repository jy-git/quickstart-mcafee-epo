#!/usr/bin/env python3
# Invoked by: SSM or SNS topic to update the image ID in the ASG
# Returns: Error or status message
#
# setups the ASG image id
import boto3
import http.client
import urllib
import json
import datetime
import time
import os

asg_client = boto3.client('autoscaling')

def validate_user_data(user_data):
    if 'AutoScalingGroupName' not in user_data:
        raise Exception('UserData  must include the AutoScalingGroupName')
    if 'ImageId' not in user_data:
        raise Exception('UserData  must include the ImageId')

def create_launch_configuration(instance_id, lc, new_image_id):
    try:
        timeStamp = time.time()
        timeStampString = datetime.datetime.fromtimestamp(timeStamp).strftime('%Y-%m-%d-%H-%M-%S')
        new_launch_config_name = lc['LaunchConfigurationName'] + new_image_id + '-' + timeStampString
        #The new launch configuration derives attributes from the instance, with the exception of the block device mapping.
        response = asg_client.create_launch_configuration(
            InstanceId = instance_id,
            LaunchConfigurationName=new_launch_config_name,
            ImageId=new_image_id,
            BlockDeviceMappings= lc['BlockDeviceMappings'])
        print(response)
        if None != response:
            return new_launch_config_name
        else:
            print('failed to create launch config with name %s and image_id %s' %(new_launch_config_name, new_image_id))
            return None
    except Exception as e:
        print('failed to create launch configuration with image id %s, %s' %(new_image_id, str(e)))
        return None


def update_parameter(name, description, value, type):
    try:
        ssm = boto3.client('ssm')
        ssm.put_parameter(Name=name,Description=description,Value=value,Type=type, Overwrite=True)
    except Exception as e:
        print('Failed to update image id for epo in parameter store')


def handler(event, context):
    print("Received event: " + json.dumps(event, indent=2))
    try:
        user_data = event
        validate_user_data(user_data)
        asg_name = user_data['AutoScalingGroupName']
        new_image_id = user_data['ImageId']
        image_parameter_name = os.environ['IMAGE_PARAMETER_NAME']

        print('Updating ASG %s with image id %s' %(asg_name, new_image_id))
        groups = asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name]).get('AutoScalingGroups', [])
        if len(groups) != 0:
            instance_id = groups[0]['Instances'][0]['InstanceId']
            lc_name = groups[0]['LaunchConfigurationName']
            lcs = asg_client.describe_launch_configurations(LaunchConfigurationNames=[lc_name]).get('LaunchConfigurations', [])
            if len(lcs) != 0:
                lc = lcs[0]
                new_launch_config_name = create_launch_configuration(instance_id, lc, new_image_id)
                if None != new_launch_config_name:
                    response = asg_client.update_auto_scaling_group(AutoScalingGroupName=asg_name,LaunchConfigurationName=new_launch_config_name)
                    if None != response:
                        update_parameter(image_parameter_name, '', new_image_id, 'String')
                        asg_client.delete_launch_configuration(LaunchConfigurationName=lc['LaunchConfigurationName'])
                        return ''
                    else:
                        print('failed to update autoscaling group')
                else:
                    print('failed to create launh config')
            else:
                print('failed to get any launc config')
        else:
            print('failed to get any ASG')
        return ''
    except Exception as e:
        print('Failed to update the ASG with image id, %s' % (str(e)))
        return ''
