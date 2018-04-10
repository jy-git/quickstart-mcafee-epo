#!/usr/bin/env python3
import boto3
import http.client
import urllib
import json
import uuid

ec2 = boto3.client('ec2')


def attach_stack_vpc_details(vpc_id, private_subnet1, private_subnet2, public_subnet1, public_subnet2, response):
    vpc_response = ec2.describe_vpcs(VpcIds=[vpc_id],DryRun=False)
    vpcs = vpc_response['Vpcs']
    if len(vpcs) != 1:
        raise Exception('More than one vpc  returned; this should never happen')

    response['Data']['VPCCIDR'] = vpcs[0]['CidrBlock']

    rt_response = ec2.describe_route_tables(Filters=[{'Name':'vpc-id', 'Values':[vpc_id]}])
    rts_list = rt_response['RouteTables']
    if len(rts_list) < 2:
        raise Exception('At least two route table should be there; this should never happen')

    for rts in rts_list:
        for association in rts['Associations']:
            if 'SubnetId' in association:
                subnet_id = association['SubnetId']
                subnet_response = ec2.describe_subnets(SubnetIds=[subnet_id])
                if 'Subnets' in subnet_response:
                    if subnet_id == private_subnet1:
                        response['Data']['PrivateRouteTable1ID'] = association['RouteTableId']
                        response['Data']['PrivateSubnet1CIDR'] = subnet_response['Subnets'][0]['CidrBlock']
                    elif subnet_id == private_subnet2:
                        response['Data']['PrivateRouteTable2ID'] = association['RouteTableId']
                        response['Data']['PrivateSubnet2CIDR'] = subnet_response['Subnets'][0]['CidrBlock']
                    elif subnet_id == public_subnet1:
                        response['Data']['PublicSubnet1CIDR'] = subnet_response['Subnets'][0]['CidrBlock']
                    elif subnet_id == public_subnet2:
                        response['Data']['PublicSubnet2CIDR'] = subnet_response['Subnets'][0]['CidrBlock']

    return response

def attach_db_vpc_details(db_identifier, response):
    rds = boto3.client('rds')
    rds_response = rds.describe_db_instances(DBInstanceIdentifier=db_identifier)
    db_instances = rds_response['DBInstances']
    if len(db_instances) != 1:
        raise Exception('More than one DB instance returned; this should never happen')

    vpc_id =  db_instances[0]['DBSubnetGroup']['VpcId']

    vpc_response = ec2.describe_vpcs(VpcIds=[vpc_id],DryRun=False)
    vpcs = vpc_response['Vpcs']
    if len(vpcs) != 1:
        raise Exception('More than one vpc  returned; this should never happen')

    vpc_cidr = vpcs[0]['CidrBlock']
    rt_response = ec2.describe_route_tables(Filters=[{'Name':'vpc-id', 'Values':[vpc_id]}, {'Name':'association.main', 'Values':["true"]}])
    rts = rt_response['RouteTables']
    if len(rts) != 1:
        raise Exception('More than one main route table returned; this should never happen')

    vpc_rt_id = rts[0]['Associations'][0]['RouteTableId']
    response['Data'] = {'DBVPCID': vpc_id, 'DBVPCCIDR': vpc_cidr,'DBVPCRouteTableID': vpc_rt_id}

    return response

def handler(event, context):
    print('Received event: %s' % json.dumps(event))
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
        if event['RequestType'] == 'Delete':
            return send_response(event,response, status='SUCCESS', reason="")
        elif event['RequestType'] == 'Update' or event['RequestType'] == 'Create':
            props = event.get('ResourceProperties')
            try:
                response['Data'] = {}
                if 'DBInstanceIdentifier' in props and '' != props.get('DBInstanceIdentifier'):
                    db_identifier = props.get('DBInstanceIdentifier')
                    response = attach_db_vpc_details(db_identifier, response)
                if 'VPCID' in props and '' != props.get('VPCID'):
                    vpc_id = props.get('VPCID')
                    private_subnet1 = props.get('PrivateSubnet1ID')
                    private_subnet2 = props.get('PrivateSubnet2ID')
                    public_subnet1 = props.get('PublicSubnet1ID')
                    public_subnet2 = props.get('PublicSubnet2ID')
                    response = attach_stack_vpc_details(vpc_id, private_subnet1, private_subnet2, public_subnet1, public_subnet2,response)

                print(response)
                return send_response(event, response, status='SUCCESS', reason="Successfully got details of vpc")
            except Exception as e:
                print(response)
                print(str(e))
                return send_response(event, response, status='FAILED', reason="Failed to get details of vpc")
        else:
            return send_response(event, response, status='FAILED', reason="Invalid request type")
    except Exception as e:
        print(str(e))
        return send_response(event, response, status='FAILED', reason="Failed to get vpc details.")


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
