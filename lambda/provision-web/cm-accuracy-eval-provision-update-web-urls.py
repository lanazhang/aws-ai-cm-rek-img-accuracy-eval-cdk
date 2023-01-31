'''
Function for CloudFormation custom resource to setup A2I relates services
on_create:
1. Check if workteam exists - create Cognito user pool, domain, client if not
2. Add users to the Cognito user pool
3. Create workforce if doesn't exist
4. Create workteam if doesn't exist
5. Crate A2I human ui template

on_delete:
1. Delete A2I human ui template
Leave the workforce, workteam and cognito user pool
'''
import json
import boto3
import os, time

S3_WEB_BUCKET_NAME = os.environ.get("S3_WEB_BUCKET_NAME")
S3_JS_PREFIX = 'static/js/'

APIGW_URL_PLACE_HOLDER = os.environ.get("APIGW_URL_PLACE_HOLDER")
COGNITO_USER_POOL_ID_PLACE_HOLDER = os.environ.get("COGNITO_USER_POOL_ID_PLACE_HOLDER")
COGNITO_USER_IDENTITY_POOL_ID_PLACE_HOLDER = os.environ.get("COGNITO_USER_IDENTITY_POOL_ID_PLACE_HOLDER")
COGNITO_REGION_PLACE_HOLDER = os.environ.get("COGNITO_REGION_PLACE_HOLDER")
COGNITO_USER_POOL_CLIENT_ID_PLACE_HOLDER = os.environ.get("COGNITO_USER_POOL_CLIENT_ID_PLACE_HOLDER")

APIGW_URL = os.environ.get("APIGW_URL")
COGNITO_REGION = os.environ.get("COGNITO_REGION")
COGNITO_USER_IDENTITY_POOL_ID = os.environ.get("COGNITO_USER_IDENTITY_POOL_ID")

CLOUD_FRONT_DISTRIBUTION_ID = os.environ.get("CLOUD_FRONT_DISTRIBUTION_ID")

S3_BUCKET_NAME = os.environ["S3_BUCKET_NAME"]
S3_BUCKET_TEMP_FILE_KEY = os.environ["S3_BUCKET_TEMP_FILE_KEY"]

s3 = boto3.client('s3')
cloudfront = boto3.client('cloudfront')

def on_event(event, context):
  print(event)
  request_type = event['RequestType']
  if request_type == 'Create': return on_create(event)
  if request_type == 'Update': return on_update(event)
  if request_type == 'Delete': return on_delete(event)
  raise Exception("Invalid request type: %s" % request_type)

def on_create(event):
  cognito_user_pool_id, cognito_user_client_id = None, None
  # Get temp file from data bucket
  s3_data = s3.get_object(Bucket=S3_BUCKET_NAME, Key=S3_BUCKET_TEMP_FILE_KEY)
  a2i_data = json.loads(s3_data['Body'].read())
  if a2i_data is not None:
    cognito_user_pool_id = a2i_data["CognitoUserPoolId"]
    cognito_user_client_id = a2i_data["CognitoClientId"]

  # Get files from s3 buckets
  s3_response = s3.list_objects(Bucket=S3_WEB_BUCKET_NAME, Prefix=S3_JS_PREFIX)
  if s3_response is not None and "Contents" in s3_response and len(s3_response["Contents"]) > 0:
    for obj in s3_response["Contents"]:
      # Download JS files to the local drive
      file_name = obj["Key"].split('/')[-1]
      print(file_name)
      s3_obj = s3.download_file(S3_WEB_BUCKET_NAME, obj["Key"], f"/tmp/{file_name}")
      
      # read file
      txt = ""
      with open(f"/tmp/{file_name}", 'r') as f:
        txt = f.read()
      if txt is not None and len(txt) > 0:
        # Replace keywords
        txt = txt.replace(APIGW_URL_PLACE_HOLDER, APIGW_URL)
        txt = txt.replace(COGNITO_USER_POOL_ID_PLACE_HOLDER, cognito_user_pool_id)
        txt = txt.replace(COGNITO_USER_IDENTITY_POOL_ID_PLACE_HOLDER, COGNITO_USER_IDENTITY_POOL_ID)
        txt = txt.replace(COGNITO_REGION_PLACE_HOLDER, COGNITO_REGION)
        txt = txt.replace(COGNITO_USER_POOL_CLIENT_ID_PLACE_HOLDER, cognito_user_client_id)
        #print(txt)
          
        # Save the file to local disk
        with open(f"/tmp/{file_name}", 'w') as f:
          f.write(txt)
          
        # upload back to s3
        s3.upload_file(f"/tmp/{file_name}", S3_WEB_BUCKET_NAME, obj["Key"])
        
        # delete local file
        os.remove(f"/tmp/{file_name}")
    
    # Invalidate CloudFront
    cloudfront.create_invalidation(
      DistributionId=CLOUD_FRONT_DISTRIBUTION_ID,
      InvalidationBatch={
              'Paths': {
                  'Quantity': 1,
                  'Items': [
                      '/*',
                  ]
              },
              'CallerReference': 'CDK auto website deployment'
          }
      )
    return True

def on_update(event):
  return

def on_delete(event):
  # Cleanup the S3 bucket: web
  s3_res = boto3.resource('s3')
  web_bucket = s3_res.Bucket(S3_WEB_BUCKET_NAME)
  web_bucket.objects.all().delete()

  return True

def on_complete(event):
  return

def is_complete(event):
  return { 'IsComplete': True }