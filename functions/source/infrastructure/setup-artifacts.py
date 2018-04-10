#!/usr/bin/env python3
# Invoked by: Code Pipeline
# Returns: Error or status message
#
# Fills a config.json configuration with dynamic parameters so that pipeline stacks can read the value from there,
# puts into the output artifacts
#
# This should always callback to the CodePipeline API to indicate success or failure


import boto3
import os
import zipfile
import json
import uuid
from botocore.client import Config

config_files = ["assets/pipeline/config/master-config.json", "assets/pipeline/config/config.json", "assets/pipeline/config/pipeline-config.json"]

config_data = [None]*len(config_files)

s3 = boto3.client('s3', config=Config(signature_version='s3v4'))
code_pipeline = boto3.client('codepipeline')
ssm_client = boto3.client('ssm')

def put_job_success(job_id, message):
    print('Putting job success')
    code_pipeline.put_job_success_result(jobId=job_id)

def put_job_failure(job_id, message):
    print('Putting job failure')
    code_pipeline.put_job_failure_result(jobId=job_id,failureDetails={'message': message, 'type': 'JobFailed'})


def get_user_data(job_data):
    try:
        user_data = json.loads(job_data['actionConfiguration']['configuration']['UserParameters'])
    except Exception as e:
        raise Exception('UserParameters could not be decoded as JSON')

    if 'ParameterStoreIdentifier' not in user_data:
        raise Exception('UserParameters JSON must include the ParameterStoreIdentifier')

    return user_data


def get_parmeters_from_parameter_store(parameter_store_identifier):
    ssm = boto3.client('ssm')
    next_token = None
    # convert them into proper formatting we want
    store_parameters = {'Parameters': {}}
    while True:
        params = {
            'Path': parameter_store_identifier,
            'Recursive': True,
            'WithDecryption': True
        }
        if next_token is not None:
            params['NextToken'] = next_token

        response = ssm.get_parameters_by_path(**params)

        if len(response['Parameters']) == 0:
            break
        for item in response['Parameters']:
            key = item['Name'].split('/')[-1]
            value = item['Value']
            store_parameters['Parameters'][key] = value
        if 'NextToken' not in response:
            break
        next_token = response['NextToken']

    return store_parameters


def download_configurations(job_data):
    input_artifact = job_data['inputArtifacts'][0]
    input_location = input_artifact['location']['s3Location']
    input_bucket = input_location['bucketName']
    input_key = input_location['objectKey']
    input_id = input_key.split('/')[-1]

    archive_path = "/tmp/{0}".format(input_id)

    print('Getting configurations from :  %s/%s ' % (input_bucket, input_key))
    print('Writing artifact to %s' % (archive_path))

    s3.download_file(input_bucket, input_key, archive_path)
    with zipfile.ZipFile(archive_path, 'r') as archive:
        for i in range(len(config_files)):
            config_data[i] = json.load(archive.open(config_files[i]))

def populate_configurations(store_parameters):
    # lets iterate through store_parameters
    print('Updating pipeline configurations')
    for i in range(len(config_files)):
        config = config_data[i]
        for key, value in config['Parameters'].items():
            if key in store_parameters['Parameters']:
                config['Parameters'][key] = store_parameters['Parameters'][key]

def upload_configurations(job_data):
    print('Uploading pipeline configurations')
    output_artifact = job_data['outputArtifacts'][0]
    output_location = output_artifact['location']['s3Location']
    output_bucket = output_location['bucketName']
    output_key = output_location['objectKey']

    archive_path = "/tmp/{0}".format(uuid.uuid4())
    archive = zipfile.ZipFile(archive_path, mode='w')

    for i in range(len(config_files)):
        body = json.dumps(config_data[i])
        archive.writestr(config_files[i], body, compress_type=zipfile.ZIP_DEFLATED)

    archive.close()
    s3.upload_file(archive_path, output_bucket, output_key)
    print('Wrote artifact to %s/%s' % (output_bucket,output_key))

def get_parameter_from_parameter_store(param):
    try:
        response = ssm_client.get_parameter(Name=param)
        if 'Parameter' in response:
            return response['Parameter']['Value']
        return None
    except Exception as e:
        return None


def put_parameter_into_parameter_store(name, description, value, type):
    try:
        ssm_client.put_parameter(Name=name,Description=description,Value=value,Type=type, Overwrite=True)
    except Exception as e:
        print('failed to put parameter %s into store, %s' % (name, str(e)))
        return None

def handle_stage_transitition(job_data):
    pipeline_name = os.environ['PIPELINE_NAME']
    pipeline_execution_parameter = os.environ['PIPELINE_EXECUTION_VERSION_PARAMETER']
    update_stage_name = os.environ['UPDATE_START_STAGE']

    print('checking stage transitions for pipeline %s, parameter = %s , update_stage = %s' % (pipeline_name, pipeline_execution_parameter, update_stage_name))

    try:
        version = 0
        pipeline_execution_version = get_parameter_from_parameter_store(pipeline_execution_parameter)
        # this is the first time pipeline is created, so its already in sync
        #just disable the stage transition to continue, update the parameter
        if "0" == pipeline_execution_version:
            print('Disabling the stage transition')
            response = code_pipeline.disable_stage_transition(pipelineName=pipeline_name, stageName=update_stage_name,
                                        transitionType='Inbound', reason='Pipeline is just created and have latest artifacts')
            print(response)
        # or enable the transition to the next stage and update the parameter
        else:
            print('Enabling the stage transition')
            response = code_pipeline.enable_stage_transition(pipelineName=pipeline_name, stageName=update_stage_name, transitionType='Inbound')
            print(response)
        version = (int(pipeline_execution_version) + 1)
        put_parameter_into_parameter_store(pipeline_execution_parameter, 'Pipeline execution version', str(version), 'String')
    except Exception as e:
        print('failed to handler stage transition but continuing the pipeline, %s' % (str(e)) )
        return None

def handler(event, context):
    try:
        print('Starting update to the configuration')

        # Extract the Job ID
        job_id = event['CodePipeline.job']['id']

        # Extract the Job Data
        job_data = event['CodePipeline.job']['data']

        # Extract the user data
        user_data = get_user_data(job_data)

        # Extract parameter from parameter store
        store_parameters = get_parmeters_from_parameter_store(user_data['ParameterStoreIdentifier'])

        # download default configurations from input artifacts
        download_configurations(job_data)

        # populate the config with store_parameters
        populate_configurations(store_parameters)

        # upload the configuration in the output artifacts of this action
        upload_configurations(job_data)

        # handle the stage tranisitions
        handle_stage_transitition(job_data)

        put_job_success(job_id, '')
        return 'Done'
    except Exception as e:
        print('Function failed due to exception.')
        print(str(e))
        put_job_failure(job_id, 'Function exception: ' + str(e))
