#!/usr/bin/env python3
# Invoked by: Cloudformation custom actions
# Returns: Error or status message
#
# setups the parameter store with required fields, verifies the email address
import boto3
import http.client
import urllib
import json
import uuid
from botocore.exceptions import ClientError

ssm = boto3.client('ssm')

def validate_user_data_for_parameter_store(user_data):
    if 'ParameterStoreIdentifier' not in user_data:
        raise Exception('UserData JSON must include the ParameterStoreIdentifier')

    if 'Parameters' not in user_data:
        raise Exception('UserData JSON must include the Parameters')

    return user_data

def add_stack_parameters(stack, stack_parameters):
    for item in stack['Parameters']:
        key = item['ParameterKey']
        value = item['ParameterValue']
        stack_parameters[key] = value
    return stack_parameters

def get_stack_parameters(stack_name):
    client = boto3.client('cloudformation')
    result = client.describe_stacks(StackName=stack_name)
    # convert them into proper formatting we want
    stack_parameters = {}
    if 'Stacks'  in result:
        stack_parameters = add_stack_parameters(result['Stacks'][0], stack_parameters)
        # add root stack parameters as well for completeness
        if 'RootId' in result['Stacks'][0]:
            root_stack_id = result['Stacks'][0]['RootId']
            root_stack_name = root_stack_id.split('/')[1]
            root_stack_result = client.describe_stacks(StackName=root_stack_name)
            if 'Stacks'  in result:
                stack_parameters = add_stack_parameters(root_stack_result['Stacks'][0], stack_parameters)
    return stack_parameters

def update_parameter(name, description, value, type):
    if value != '':
        ssm.put_parameter(Name=name,Description=description,Value=value,Type=type, Overwrite=True)
    else:
        print(name + ' value is empty')

def delete_parameter(name):
    # even delete fails dont pass the exception
    try:
        ssm.delete_parameter(Name=name)
    except Exception as e:
        str(e)

def update_parameter_store(stack_parameters, user_parameters, identifier):
    for k, v in stack_parameters.items():
        name = identifier + '/' + k
        update_parameter(name, '', v, 'String')
    for k, v in user_parameters.items():
        name = identifier + '/' + k
        update_parameter(name, v['Description'], v['Value'], v['Type'])

def delete_parameter_store(stack_parameters, user_parameters, identifier):
    for k, v in stack_parameters.items():
        name = identifier + '/' + k
        delete_parameter(name)

    for k, v in user_parameters.items():
        name = identifier + '/' + k
        delete_parameter(name)

# setups the parameter store
def setup_parameter_store_handler(user_data, request_type):
    print('handler parameter store started')
    validate_user_data_for_parameter_store(user_data)
    parameter_store_id = user_data['ParameterStoreIdentifier']
    user_parameters = json.loads(user_data['Parameters'])

    # extract cloudformation iam role from user data and set it in user parameters
    if 'BaseStack' in user_data:
        base_stack_name = user_data['BaseStack']
        user_parameters['BaseStack']['Value'] = base_stack_name
    if 'ParentStack' in user_data:
        parent_stack_name = user_data['ParentStack']
        user_parameters['ParentStack']['Value'] = parent_stack_name
    if 'PipelineMasterStackTemplateName' in user_data:
        pipeline_master_stack_template_name = user_data['PipelineMasterStackTemplateName']
        user_parameters['PipelineMasterStackTemplateName']['Value'] = pipeline_master_stack_template_name
    if 'PipelineMasterStackTemplateConfigName' in user_data:
        pipeline_master_stack_template_config_name = user_data['PipelineMasterStackTemplateConfigName']
        user_parameters['PipelineMasterStackTemplateConfigName']['Value'] = pipeline_master_stack_template_config_name
    if 'PipelineCloudformationIAMRoleARN' in user_data:
        pipeline_cfn_iam_role_arn = user_data['PipelineCloudformationIAMRoleARN']
        user_parameters['PipelineCloudformationIAMRoleARN']['Value'] = pipeline_cfn_iam_role_arn

    if 'StackName'  in user_data:
        stack_parameters = get_stack_parameters(user_data['StackName'])
    else:
        stack_parameters = {}

    if request_type == 'Create':
        update_parameter_store(stack_parameters, user_parameters, parameter_store_id)
    elif request_type == 'Update':
        if 'PipelineExecutionVersion' in user_parameters:
            item  = user_parameters.pop('PipelineExecutionVersion')
            print('PipelineExecutionVersion'+str(item))
        print(user_parameters)
        update_parameter_store(stack_parameters, user_parameters, parameter_store_id)
    elif request_type == 'Delete':
        delete_parameter_store(stack_parameters, user_parameters, parameter_store_id)
    print('handler parameter store finished')

def validate_user_data_for_email_verification(user_data):
    if 'SenderEmailAddress' not in user_data:
        raise Exception('UserData JSON must include the SenderEmailAddress')
    if 'ToEmailAddresses' not in user_data:
        raise Exception('UserData JSON must include the ToEmailAddresses')
    if 'CcEmailAddress' not in user_data:
        raise Exception('UserData JSON must include the CcEmailAddress')

def verify_email_address(sender_address, to_addresses, cc_addresses):
    ses = boto3.client('ses', region_name='us-west-2')
    verify_email_identity(ses, sender_address)
    verify_email_identity(ses, to_addresses)
    verify_email_identity(ses, cc_addresses)

def verify_email_identity(ses, email_address):
    if email_address is not None:
        ses.verify_email_identity(EmailAddress=email_address)

# handles the email verification
def email_verification_handler(user_data, request_type):
    try:
        if request_type == 'Create':
            validate_user_data_for_email_verification(user_data)
            verify_email_address(user_data['SenderEmailAddress'], user_data['ToEmailAddresses'], user_data['CcEmailAddress'])
        elif request_type == 'Delete' or request_type == 'Update':
            print('nothing to do for email handler in case of request type delete or update')
    except Exception as e:
        print('failed in email handler for verification')
        print(str(e))

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
        setup_parameter_store_handler(user_data, event['RequestType'])
        if 'VerifyEmailAddress' in user_data and 'yes' == user_data['VerifyEmailAddress']:
            email_verification_handler(user_data, event['RequestType'])
        return send_response(event, response, status='SUCCESS', reason='succesfully applied pre deployment actions')

    except ClientError as e:
        print(str(e))
        return send_response(event, response, status='FAILED', reason='failed to perform pre deployment actions')

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
