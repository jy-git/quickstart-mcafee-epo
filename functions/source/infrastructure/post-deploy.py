#!/usr/bin/env python3
# Invoked by: Cloudformation custom actions
# Returns: Error or status message
#
# sends the post deployment email and attaches the ePO local agent handler  instance to the AH ASG
import boto3
import http.client
import urllib
import json
import uuid
import re
from botocore.exceptions import ClientError
from base64 import b64encode
import ssl

rg_client = boto3.client('resource-groups')
ssm = boto3.client('ssm')

def validate_email_params(user_data, email_data):
    if 'StackURL' not in user_data:
        raise Exception('UserData JSON must include the StackURL')
    if 'EPOConsoleURL' not in user_data:
        raise Exception('UserData JSON must include the EPOConsoleURL')
    if 'PipeLineURL' not in user_data:
        raise Exception('UserData JSON must include the PipeLineURL')
    if 'DashboardURL' not in user_data:
        raise Exception('UserData JSON must include the DashboardURL')
    if 'SenderEmailAddress' not in email_data:
        raise Exception('EmailData JSON must include the SenderEmailAddress')
    if 'ToEmailAddresses' not in email_data:
        raise Exception('EmailData JSON must include the ToEmailAddresses')
    if 'CcEmailAddress' not in email_data:
        raise Exception('EmailData JSON must include the CcEmailAddress')
    if 'SourceBucket' not in email_data:
        raise Exception('EmailData JSON must include the SourceBucket')
    if 'Prefix' not in email_data:
        raise Exception('EmailData JSON must include the Prefix')
    if 'HTMLEmailSourceKey' not in email_data:
        raise Exception('EmailData JSON must include the HTMLEmailSourceKey')
    if 'ComponentsJSONFile' not in email_data:
        raise Exception('EmailData JSON must include the ComponentsJSONFile')


def download_message(user_data, email_data):
    s3 = boto3.client('s3')

    key = email_data['Prefix'] + email_data['HTMLEmailSourceKey']
    response = s3.get_object(Bucket=email_data['SourceBucket'], Key=key)
    message = response['Body'].read().decode('utf-8')

    key = email_data['Prefix'] + email_data['ComponentsJSONFile']
    response = s3.get_object(Bucket=email_data['SourceBucket'], Key=key)
    components = json.loads(response['Body'].read().decode('utf-8'))

    message = re.sub('@url.epo.console@', user_data['EPOConsoleURL'], message)
    message = re.sub('@url.mcafee.stack@', user_data['StackURL'], message)
    message = re.sub('@url.mcafee.dashboard@', user_data['DashboardURL'], message)

    parameter_store_identifier = user_data['ParameterStoreIdentifier']

    for key in components:
        # Store the base build version number used at the time of stack creation.
        ssm.put_parameter(Name=parameter_store_identifier+'/buildinfo/'+key,Description=components[key]['Name']+' version',Value=components[key]['BuildVersion'],Type='String', Overwrite=True)
        message = re.sub("@"+key.lower()+".buildversion@", components[key]['BuildVersion'], message)

    print(components)
    print(user_data['EPOConsoleURL'])
    print(user_data['DashboardURL'])
    if '' != user_data['PipeLineURL']:
        print(user_data['PipeLineURL'])
    return message

def delete_parameter(name):
    # even delete fails dont pass the exception
    try:
        ssm.delete_parameter(Name=name)
    except Exception as e:
        str(e)

def delete_ssm_parameters(user_data, email_data):
    s3 = boto3.client('s3')
    key = email_data['Prefix'] + email_data['ComponentsJSONFile']
    response = s3.get_object(Bucket=email_data['SourceBucket'], Key=key)
    components = json.loads(response['Body'].read().decode('utf-8'))
    parameter_store_identifier = user_data['ParameterStoreIdentifier']

    for key in components:
        delete_parameter(parameter_store_identifier+'/buildinfo/'+key)

def get_email_address_list(email_address):
    email_address_list = []
    if email_address: # if email_address is not empty string or empty list
        email_address_list.append(email_address)
    return email_address_list

def send_email(sender_address, to_addresses, cc_addresses, subject, message):
    charset = 'UTF-8'
    ses = boto3.client('ses', region_name='us-west-2')

    response = ses.send_email(
        Destination={
            'ToAddresses': get_email_address_list(to_addresses),
            'CcAddresses': get_email_address_list(cc_addresses),
        },
        Message={
            'Body': {
                'Html': {
                    'Charset': charset,
                    'Data': message,
                }
            },
            'Subject': {
                'Charset': charset,
                'Data': subject,
            },
        },
        Source=sender_address
    )

def email_handler(user_data, request_type):
    # handle all the email notification error but never pass it down , no reason to fail the whole stack of it
    try:
        email_data = json.loads(user_data['EmailHandlerData'])
        print(email_data)
        if request_type == 'Create':
            message = ''
            subject = 'Welcome to McAfee ePO On Public Cloud'
            validate_email_params(user_data, email_data)
            message = download_message(user_data, email_data)
            send_email(email_data['SenderEmailAddress'], email_data['ToEmailAddresses'], email_data['CcEmailAddress'], subject, message)
        elif request_type == 'Delete':
            delete_ssm_parameters(user_data, email_data)

    except Exception as e:
        print('failed to send email to reciepents')
        print(str(e))

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


def get_resource_group(rg_name):
    try:
        response = rg_client.get_group(GroupName=rg_name)
        if 'Group' in response and 'Name' in  response['Group']:
            return response['Group']['Name']
        return None
    except Exception as e:
        print('get resource group failed for %s, %s' %(rg_name, str(e)))
        return None

def resource_group_handler(user_data, request_type):
    # handle the resource group creation
    try:
        print('Inside the resource group handler for request type %s' %(request_type))

        rg = json.loads(user_data['ResourceGroupHandlerData'])
        print(rg)
        if request_type == 'Create':
            rg_client.create_group(Name=rg['Name'], Description=rg['Description'], ResourceQuery=rg['ResourceQuery'], Tags=rg['Tags'])
        elif request_type == 'Update':
            if None != get_resource_group(rg['Name']):
                rg_client.update_group(GroupName=rg['Name'], Description=rg['Description'])
            else:
                print('resource group %s doesnt exists, creating one' %(rg['Name']))
                rg_client.create_group(Name=rg['Name'], Description=rg['Description'], ResourceQuery=rg['ResourceQuery'], Tags=rg['Tags'])
        elif request_type == 'Delete':
            if None != get_resource_group(rg['Name']):
                rg_client.delete_group(GroupName=rg['Name'])
            else:
                print('resource group %s doesnt exists' %(rg['Name']))
        else:
            print('invalid request')
    except Exception as e:
        print('failed to handle resource group request, %s' % str(e))

def remote_command_handler(user_data, request_type):
    try:
        cmd_data = json.loads(user_data['RemoteCommandHandlerData'])
        print(cmd_data)
        if request_type == 'Create':
            group_name = 'vgroup_' + cmd_data['ParentStackName']
            epo_dns_name = cmd_data['EPOURL']
            ah_url = cmd_data['AHURL']
            ah_elb_url = cmd_data['AHURL']
            dxl_elb_url = user_data['DXLELBURL']
            dxl_port = cmd_data['DXLPort']
            if '' == cmd_data['DomainName']:
                epo_dns_name = user_data['EPOELBURL']
                ah_elb_url = user_data['AHELBURL']

            parameter_store_identifier = user_data['ParameterStoreIdentifier']
            response = ssm.get_parameter(Name=parameter_store_identifier+'/EPOAdminUserName')
            epo_username = response['Parameter']['Value']
            response = ssm.get_parameter(Name=parameter_store_identifier+'/EPOAdminPassword', WithDecryption=True)
            epo_password = response['Parameter']['Value']

            epo_hostname = user_data['EPOELBURL']
            epo_port = cmd_data['EPOConsolePort']

            auth_string = epo_username + ':' + epo_password
            auth = b64encode(auth_string.encode()).decode("ascii")
            headers = { 'Authorization' : 'Basic %s' %  auth }

            # Remote command to set AH virtual group
            ah_remote_cmd_path = '/remote/AgentMgmt.createAgentHandlerGroup?groupName=' + group_name + '&enabled=true&loadBalancerSet=true&virtualIP=' + ah_url + '&virtualDNSName=' + ah_elb_url + '&virtualNetBiosName=' + ah_url
            https = http.client.HTTPSConnection(epo_hostname, epo_port, context=ssl._create_unverified_context())
            https.request('POST', ah_remote_cmd_path, headers=headers)
            response = https.getresponse()
            print(response.status, response.reason)

            # Remote command to set DXL loadbalancer info
            dxl_remote_cmd_path = '/remote/DxlBrokerMgmt.setLoadBalancerInfo?dnsName=' + dxl_elb_url + '&ipAddress=' + dxl_elb_url + '&port=' + dxl_port
            https = http.client.HTTPSConnection(epo_hostname, epo_port, context=ssl._create_unverified_context())
            https.request('POST', dxl_remote_cmd_path, headers=headers)
            response = https.getresponse()
            print(response.status, response.reason)

            # Remote command to set ePO DNS name for Agent deployment url
            epo_remote_cmd_path = '/remote/EPOCore.setAgentDeploymentURLServerCmd?agentDeploymentURLServer=' + epo_dns_name
            https = http.client.HTTPSConnection(epo_hostname, epo_port, context=ssl._create_unverified_context())
            https.request('POST', epo_remote_cmd_path, headers=headers)
            response = https.getresponse()
            print(response.status, response.reason)

        elif request_type == 'Delete' or request_type == 'Update':
            print('nothing to do for remote command handler in case of update or delete request type')

    except Exception as e:
        print('failed to execute remote commands %s' %(str(e)))
        raise Exception('Provisioning of DXL and AH failed to set the virtual groups')

# Register Local AgentHandler with  AgentHandler's LoadBalancer
def localah_registration_handler(user_data, request_type):
    elb_client = boto3.client('elb')
    ah_loadbalancer_id = user_data['LocalAHRegistrationHandlerData']['AHELBName']
    epo_instance_id = user_data['LocalAHRegistrationHandlerData']['EPOInstanceID']
    print('Performing action %s with ePOInstanceId %s and AHELBName %s' %(request_type, epo_instance_id, ah_loadbalancer_id))
    if 'Create' == request_type or 'Update'==  request_type:
        response = elb_client.register_instances_with_load_balancer(LoadBalancerName= ah_loadbalancer_id, Instances= [ {'InstanceId':epo_instance_id}])
        if 'Instances' in response and (len(response['Instances']) > 0):
            print('Registered epo instance id '+ epo_instance_id+ ' with AgentHandler LoadBalancer '+ ah_loadbalancer_id + ' successfully')
        else:
            print('Failed to register instance with response %s' %(response))
    elif 'Delete' == request_type:
        response = elb_client.deregister_instances_from_load_balancer(LoadBalancerName= ah_loadbalancer_id, Instances= [ {'InstanceId':epo_instance_id}])
        if 'Instances' in response and (len(response['Instances']) > 0):
            print('Deregistered epo instance id '+ epo_instance_id+ ' with AgentHandler LoadBalancer '+ ah_loadbalancer_id + ' successfully')
        else:
            print('Failed to de-register instance with response %s' %(response))
    else:
        print('Unknown request type for localah_registration_handler')

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
        request_type = event['RequestType']

        if 'RemoteCommandHandlerData' in user_data:
            remote_command_handler(user_data, request_type)
        if 'EmailHandlerData' in user_data:
            email_handler(user_data, request_type)
        if 'ResourceGroupHandlerData' in user_data:
            resource_group_handler(user_data, request_type)
        if 'LocalAHRegistrationHandlerData' in user_data:
            localah_registration_handler(user_data,request_type)
        return send_response(event, response, status='SUCCESS', reason="succesfully applied post deployment actions")
    except ClientError as e:
        print(str(e))
        return send_response(event, response, status='SUCCESS', reason="Was not able to apply post deployment actions")
