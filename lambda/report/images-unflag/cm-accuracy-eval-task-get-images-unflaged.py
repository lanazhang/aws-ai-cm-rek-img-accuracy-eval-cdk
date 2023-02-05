import json
import boto3
import math
import os

DYNAMO_TASK_TABLE = os.environ["DYNAMODB_TASK_TABLE"]
DYNAMO_INDEX_NAME = os.environ["DYNAMODB_INDEX_NAME"]
EXPIRATION_IN_S = os.environ["EXPIRATION_IN_S"] # 5 minutes

region = os.environ['AWS_REGION']

TP_STR = "true-positive"
FP_STR = "false-positive"

dynamodb = boto3.client('dynamodb')
s3 = boto3.client('s3', region_name=region, endpoint_url=f'https://s3.{region}.amazonaws.com')

def lambda_handler(event, context):
    id = event.get("id")
    top_category = event.get("top_category")
    sub_category = event.get("sub_category")
    type = event.get("type")
    confidence_threshold = event.get("confidence_threshold")
    
    if id is None:
        return {
            'statusCode': 400,
            'body': "Task id is required."
        }

    # Get task item from DB table
    d_response = dynamodb.get_item(
        TableName=DYNAMO_TASK_TABLE,
        Key={"id" : { "S": id}}
    )    
    item = d_response.get("Item")
    print("1. Get db item: ", item)
    if item is None:
       return {
            'statusCode': 400,
            'body': "Task id doesn't exist."
        }   
    
    from boto3.dynamodb.conditions import Key
    dynamo_res = boto3.resource('dynamodb')
    table = dynamo_res.Table(item["moderation_result_table"]["S"])
    response = table.query(
        IndexName=DYNAMO_INDEX_NAME,
        KeyConditionExpression=Key('issue_flag').eq(0)
    )
    last_key = response.get("LastEvaluatedKey")

    result = []
    for db_item in response["Items"]:
        file_path = db_item["file_path"]
        bucket = file_path.split("/")[2]
        key = file_path.replace(f's3://{bucket}/', '')
        
        # Generate S3 presigned URL
        s3_response = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket,
                    'Key': key},
            ExpiresIn=EXPIRATION_IN_S)
            
        result.append({
                "file_path": file_path,
                "url": s3_response,
                "top_category": None,
                "sub_category": None,
                "confidence": None,
                "type": None,
                "review_result": None,
            })
    
    return {
            'statusCode': 200,
            'body': json.dumps(result)
        } 