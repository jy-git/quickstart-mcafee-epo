#!/usr/bin/env python3
# Invoked by: Cloudformation custom actions
# Returns: Error or status message
#
# performs the epcation server post deployment custom action to attach certificate to the ALB
import boto3
import http.client
import urllib
import json
import uuid
import re
from botocore.exceptions import ClientError
from base64 import b64encode
import ssl
import time

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

# epo applicaiton server ELB certificate handler for HTTPS termination at load balancer
def epo_elb_certifcate_handler(user_data, request_type):
    parent_stack_name = user_data['ParentStack']
    epo_hostname = user_data['EPOConsoleURL']
    epo_port = user_data['EPOConsolePort']
    epo_https_listener_arn = user_data['EPOHTTPSListenerARN']
    lah_https_listener_arn = user_data['LAHHTTPSListenerARN']
    ssl_policy = user_data['SslPolicy']

    if request_type == 'Create':
        ssm = boto3.client('ssm')

        parameter_store_identifier = user_data['ParameterStoreIdentifier']
        response = ssm.get_parameter(Name=parameter_store_identifier+'/EPOAdminUserName')
        epo_username = response['Parameter']['Value']
        response = ssm.get_parameter(Name=parameter_store_identifier+'/EPOAdminPassword', WithDecryption=True)
        epo_password = response['Parameter']['Value']

        auth_string = epo_username + ':' + epo_password
        auth = b64encode(auth_string.encode()).decode("ascii")
        headers = { 'Authorization' : 'Basic %s' %  auth }
        # Remote command to get ePO App server ELB certificate
        # NOTE: using self signed genereted AH remote command,
        # it may confuse suers for now but in future we will intorduce new remote command to generate cert for other purpose
        epo_cert_remote_cmd_path = '/remote/epo.command.createEPOLBCertificate?commonName=EPO_ELB_' + parent_stack_name
        https = http.client.HTTPSConnection(epo_hostname, epo_port, context=ssl._create_unverified_context())
        https.request('POST', epo_cert_remote_cmd_path, headers=headers)
        response = https.getresponse()
        print(response.status, response.reason)
        certs_out = response.read().decode()

        if -1 == certs_out.find('BEGIN CERTIFICATE'):
            print("trying to generate AH certificate as a fallback")
            ah_cert_remote_cmd_path = '/remote/epo.command.createAgentHandlerCertificate?commonName=EPO_ELB_' + parent_stack_name

            https = http.client.HTTPSConnection(epo_hostname, epo_port, context=ssl._create_unverified_context())
            https.request('POST', ah_cert_remote_cmd_path, headers=headers)
            response = https.getresponse()
            print(response.status, response.reason)
            certs_out = response.read().decode()

        if -1 != certs_out.find('BEGIN CERTIFICATE'):
            epo_elb_cert = re.search(r"^([-]+BEGIN CERTIFICATE[-]+\s+(.*?)\s+[-]+END CERTIFICATE[-]+)", certs_out, re.MULTILINE| re.DOTALL).group(1)
            epo_elb_key  = re.search(r"^([-]+BEGIN RSA PRIVATE KEY[-]+\s+(.*?)\s+[-]+END RSA PRIVATE KEY[-]+)", certs_out, re.MULTILINE| re.DOTALL).group(1)

            #upload the certifcate into IAM
            iam_client = boto3.client('iam')

            response = iam_client.upload_server_certificate(ServerCertificateName=('EPO_ELB_' + parent_stack_name),CertificateBody=epo_elb_cert,PrivateKey=epo_elb_key)
            print(response)
            if 'ServerCertificateMetadata' in response:
                elb_client = boto3.client('elbv2')
                epo_elb_cert_arn = response['ServerCertificateMetadata']['Arn']
                print(epo_elb_cert_arn)
                # wait 60 secs before attaching IAM cert to listener. upload may take time.
                time.sleep(60)
                result = elb_client.modify_listener(ListenerArn=epo_https_listener_arn, Protocol='HTTPS',SslPolicy=ssl_policy,Certificates=[{'CertificateArn':epo_elb_cert_arn}])
                print(result)
                if 'Listeners' in result and epo_https_listener_arn == result['Listeners'][0]['ListenerArn'] or epo_https_listener_arn == result['Listeners'][1]['ListenerArn']:
                    print('updated ePO app server load balancer app server https listener with certifcates')
                else:
                    raise Exception('failed to update ePO Application server app server load balancer https listener with certifcates')

                result = elb_client.modify_listener(ListenerArn=lah_https_listener_arn, Protocol='HTTPS',SslPolicy=ssl_policy,Certificates=[{'CertificateArn':epo_elb_cert_arn}])
                print(result)
                if 'Listeners' in result and lah_https_listener_arn == result['Listeners'][0]['ListenerArn'] or lah_https_listener_arn == result['Listeners'][1]['ListenerArn']:
                    print('updated ePO app server load balancer local ah https listener with certifcates')
                else:
                    raise Exception('failed to update ePO Application server load balancer local ah https listener with certifcates')

            else:
                raise Exception('failed to upload certificate to IAM')
        else:
            raise Exception('failed to get eP app server load balancer certificate')
    elif request_type == 'Update':
        print('nothing to do for EPO appserver elb certificate handler in case of update request type')
    elif request_type == 'Delete':
        iam_client = boto3.client('iam')
        iam_client.delete_server_certificate(ServerCertificateName=('EPO_ELB_' + parent_stack_name))


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
        epo_elb_certifcate_handler(user_data, request_type)
        return send_response(event, response, status='SUCCESS', reason="succesfully applied epo applicaiton server post deployment actions")
    except ClientError as e:
        print(str(e))
        return send_response(event, response, status='SUCCESS', reason="Was not able to epo applicaiton server post deployment actions")
