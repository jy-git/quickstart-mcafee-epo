#!/usr/bin/env python3
import json
import boto3
import cfnresponse

r53 = boto3.client('route53')
cfn = boto3.client('cloudformation')

def is_route53_domain_exist(domain_name):
    try:
        response = r53.get_hosted_zone_count()
        if '0' != response['HostedZoneCount']:
            response = r53.list_hosted_zones_by_name(DNSName=domain_name)
            if domain_name == response['HostedZones'][0]['Name']:
                return True
        return False
    except Exception as e:
        print(str(e))

def check_parameter_details(request_type, user_data):
    if request_type == 'Create':
        domain_name = user_data['DomainName']
        sub_domain_name = user_data['SubDomainName']
        if '' != domain_name and False == is_route53_domain_exist(domain_name + '.'):
          print(domain_name + ' is not in AWS route53 hosted zone')
          return False
        else:
          if True == is_route53_domain_exist(sub_domain_name + '.'):
            print(sub_domain_name + ' is already in AWS route53 hosted zone')
            return False
    return True

def check_stack_details(user_data, response):
    result = cfn.describe_stacks(StackName=user_data['StackName'])
    if 'Stacks'  in result:
        if 'RootId' in result['Stacks'][0]:
            root_stack_id = result['Stacks'][0]['RootId']
            root_stack_name = root_stack_id.split('/')[1]
            response['ParentStack'] = root_stack_name
            response['ParentStackID'] = root_stack_id
        else:
            response['ParentStack'] = user_data['StackName']
            response['ParentStackID'] = result['Stacks'][0]['StackId']
        return response
    return False

def handler(event, context):
    print('Received event: %s' % json.dumps(event))
    try:
        user_data = event.get('ResourceProperties')
        status = cfnresponse.SUCCESS
        response = {}
        request_type = event['RequestType']
        if request_type != 'Delete':
            if False == check_parameter_details(request_type, user_data):
                status = cfnresponse.FAILED
            else:
                response = check_stack_details(user_data, response)
                if False == response:
                    status = cfnresponse.FAILED
        cfnresponse.send(event, context, status, response, None)
    except Exception as e:
        print('Exception in handling the request, %s' % (str(e)))
        cfnresponse.send(event, context, cfnresponse.FAILED, {}, None)
