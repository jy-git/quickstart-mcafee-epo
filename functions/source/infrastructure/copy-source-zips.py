#!/usr/bin/env python3
import json
import boto3
import cfnresponse

import os
import tempfile
import zipfile

from concurrent import futures
from io import BytesIO

s3 = boto3.client('s3')
s3_resource = boto3.resource('s3')

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
        print('artifacts zip is not copied into regional S3 bucket')
        return False

def delete_objects(bucket_name):
    print('deleting data from bucket %s' % bucket_name)
    bucket = s3_resource.Bucket(bucket_name)
    print('deleting data from bucket %s' % bucket_name)
    bucket.objects.all().delete()
    print('deleting all versions of bucket %s' % bucket_name)
    bucket.object_versions.all().delete()

def handler(event, context):
    print('Received event: %s' % json.dumps(event))
    try:
        source_bucket = event['ResourceProperties']['SourceBucket']
        dest_bucket = event['ResourceProperties']['DestBucket']
        artifacts_zip_key = event['ResourceProperties']['ArtifactsZIPKey']
        prefix = event['ResourceProperties']['Prefix']

        if event['RequestType'] == 'Delete':
            delete_objects(dest_bucket)
            cfnresponse.send(event, context, cfnresponse.SUCCESS, {}, None)
        else:
            print('sync-up with quick start bucket due version mismatch')
            if True == copy_source(source_bucket, dest_bucket, prefix, artifacts_zip_key):
                cfnresponse.send(event, context, cfnresponse.SUCCESS, {}, None)
            else:
                cfnresponse.send(event, context, cfnresponse.FAILED, {}, None)

    except Exception as e:
        print('Exception in handling the request, %s' % (str(e)))
        cfnresponse.send(event, context, cfnresponse.FAILED, {}, None)
