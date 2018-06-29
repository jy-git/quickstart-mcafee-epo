#!/usr/bin/env python3
import boto3
import json
import logging
import time
import os
import time

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
ssm_client = boto3.client("ssm")

def check_response(response):
    try:
        if response['ResponseMetadata']['HTTPStatusCode'] == 200:
            return True
        else:
            return False
    except KeyError:
        return False

def send_command(instance_id, hook_component, paramspath):
    try:
        if hook_component == 'dxl':
            response = ssm_client.send_command(
                                InstanceIds = [ instance_id ],
                                DocumentName = "AWS-RunShellScript",
                                TimeoutSeconds = 120,
                                Parameters={
                                        'commands':[
                                            'python dxl-deprovision.py --paramspath ' + paramspath
                                            ],
                                        'executionTimeout': ['600'],
                                        'workingDirectory':[
                                            '/home/centos/provision'
                                        ]
                                    }
                                )
        else:
            response = ssm_client.send_command(
                                InstanceIds = [ instance_id ],
                                DocumentName = "AWS-RunPowerShellScript",
                                TimeoutSeconds = 120,
                                Parameters={
                                        'commands':[
                                            'node ah-deprovision.js --paramspath ' + paramspath + ' --region '+ os.environ['AWS_REGION']
                                            ],
                                        'executionTimeout': ['600'],
                                        'workingDirectory':[
                                            'C:/Program Files (x86)/McAfee/HostedePO'
                                        ]
                                    }
                                )
        if check_response(response):
            logger.info("command sent: %s successfully", response)
            return response['Command']['CommandId']
        else:
            logger.error("failed to send command: %s", response)
            return None
    except Exception as e:
        logger.error("failed to process command, exception: %s", str(e))
        return None

def check_command(command_id, instance_id):
    count = 36 # max 3 mints
    while --count:

        response_iterator = ssm_client.list_command_invocations(
                                                                CommandId = command_id,
                                                                InstanceId = instance_id,
                                                                Details=False
                                                                )
        if check_response(response_iterator):
            if len(response_iterator['CommandInvocations']) != 0:
                response_iterator_status = response_iterator['CommandInvocations'][0]['Status']
                if response_iterator_status != 'Pending':
                    if response_iterator_status == 'Success':
                        logging.info( "Status: %s", response_iterator_status)
                        return True
                    elif response_iterator_status == 'InProgress':
                        logging.info( "Status: %s", response_iterator_status)
                    else:
                        logging.error("ERROR: status: %s", response_iterator)
                        return False
        time.sleep(5)
    else:
        logging.error("ERROR: Timeout in retrieving command status")
        return False

def update_lifecycle(lifecycle_hook, auto_scaling_group, instance_id, status):
    asg_client = boto3.client('autoscaling')
    try:
        response = asg_client.complete_lifecycle_action(
            LifecycleHookName=lifecycle_hook,
            AutoScalingGroupName=auto_scaling_group,
            LifecycleActionResult=status,
            InstanceId=instance_id
            )
        if check_response(response):
            logger.info("lifecycle hook %s processed: %s", status, response)
        else:
            logger.error("failed to %s lifecycle hook: %s", status, response)
    except Exception as e:
        logger.error("failed to %s lifecycle hook, exception: %s", status, str(e))
        return None


def handler(event, context):
    try:
        logger.info(json.dumps(event))
        record = event['Records'][0]
        message_str = record['Sns']['Message']
        message = json.loads(message_str)

        if 'LifecycleHookName' in message:
            lifecycle_hook = message['LifecycleHookName']
            auto_scaling_group = message['AutoScalingGroupName']
            instance_id = message['EC2InstanceId']
            metadata = message['NotificationMetadata']
            hook_component = metadata.split('|')[0]
            paramspath = metadata.split('|')[1]
            logger.info(hook_component)
            logger.info(paramspath)
            command_id = send_command(instance_id, hook_component, paramspath)
            if command_id != None:
                if check_command(command_id, instance_id):
                    logging.info("ASG lifecycle hook lambda executed correctly")
                    update_lifecycle(lifecycle_hook, auto_scaling_group, instance_id, 'CONTINUE')
                else:
                    update_lifecycle(lifecycle_hook, auto_scaling_group, instance_id, 'ABANDON')
            else:
                update_lifecycle(lifecycle_hook, auto_scaling_group, instance_id, 'ABANDON')
        else:
            logging.error("no valid JSON message")
    except Exception as e:
        logging.error("Error: %s", str(e))
