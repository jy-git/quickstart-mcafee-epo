#!/usr/bin/env python3
import json
import boto3

import os
import tempfile
import zipfile

from concurrent import futures
from io import BytesIO

s3 = boto3.client('s3')
s3_resource = boto3.resource('s3')
ssm = boto3.client('ssm')

def extract(bucket, prefix, filename):
    exract_status = 'success'
    try:
        s3.upload_fileobj(BytesIO(zipdata.read(filename)), bucket, prefix + filename)
    except Exception as e:
        print('failed to extract file:%s, %s' % (prefix + filename, str(e)))
        exract_status = 'fail'
    finally:
        return prefix + filename, exract_status

def extract_zip(bucket, prefix, artifacts_zip_key):
    global zipdata
    temp_file = tempfile.mktemp()
    s3.download_file(bucket, prefix + artifacts_zip_key, temp_file)
    zipdata = zipfile.ZipFile(temp_file)

    with futures.ThreadPoolExecutor(max_workers=4) as executor:
        future_list = [
            executor.submit(extract, bucket, prefix, filename)
            for filename in zipdata.namelist()
        ]

    result = {'success': [], 'fail': []}
    for future in future_list:
        filename, status = future.result()
        result[status].append(filename)

    if 0 == len(result['fail']):
        print('sucessfully extracted artifacts into bucket %s' % (bucket))
        return True
    else:
        print(result)
        return False

def copy_source(source_bucket, dest_bucket, prefix, artifacts_zip_key):
    key = prefix + artifacts_zip_key
    copy_source = {
        'Bucket': source_bucket,
        'Key': key
    }
    print('copy_source: %s' % copy_source)
    print('dest_bucket = %s'% dest_bucket)
    print('key = %s' % key)
    response = s3.copy_object(CopySource=copy_source, Bucket=dest_bucket, Key=key)
    print(response)
    if 'VersionId' in response:
        print('successfully downloaded mcafee artifacts zip from bucket %s' % (source_bucket))
        return extract_zip(dest_bucket, prefix, artifacts_zip_key)
    else:
        print("artifacts zip is not copied into regional S3 bucket")
        return False

def get_parameter_from_parameter_store(param):
    try:
        print(param)
        response = ssm.get_parameter(Name=param)
        print(response)
        if 'Parameter' in response:
            return response['Parameter']['Value']
        return None
    except Exception as e:
        print('Exception in get parameter, %s' % (str(e)))
        return None

def update_parameter(name, description, value):
    try:
        ssm.put_parameter(Name=name,Description=description,Value=value,Type="String", Overwrite=True)
    except Exception as e:
        print('Failed to update artifacts version ID in parameter store, %s', (str(e)))


def is_version_changed(source_bucket, prefix, artifacts_zip_key, artifacts_version_id_param):
    key = prefix + artifacts_zip_key
    response = s3.head_object(Bucket=source_bucket, Key=key)
    print(response)
    if 'VersionId' in response:
        cur_version_id = response['VersionId']
        print(cur_version_id)
        prev_version_id = get_parameter_from_parameter_store(artifacts_version_id_param)
        print(prev_version_id)
        if "0" == prev_version_id:
            prev_version_id = cur_version_id
            update_parameter(artifacts_version_id_param, "QS S3 Artifacts zip version ID.", cur_version_id)

        if cur_version_id != prev_version_id:
            update_parameter(artifacts_version_id_param, "QS S3 Artifacts zip version ID.", cur_version_id)
            return True
        else:
            return False
    else:
        print('There is no version on key %s' % artifacts_zip_key)
        return None

def handler(event, context):
  print('Received event: %s' % json.dumps(event))
  try:
      source_bucket = event["SourceBucket"]
      dest_bucket = event["DestinationBucket"]
      artifacts_zip_key = event["ArtifactsZIPKey"]
      artifacts_version_id_param = event['ArtifactsVersionIDSSMParameter']
      prefix = event["Prefix"]

      if True == is_version_changed(source_bucket, prefix, artifacts_zip_key, artifacts_version_id_param):
          copy_source(source_bucket, dest_bucket, prefix, artifacts_zip_key)
      else:
          print("There is no change in quick start artifacts")

  except Exception as e:
      print('Exception in handling the artifacts syncup event, %s' % (str(e)))
