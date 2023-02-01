import json
import boto3
import math
import os
from datetime import datetime

DYNAMO_TASK_TABLE = os.environ["DYNAMODB_TASK_TABLE"]
DYNAMO_INDEX_NAME = os.environ["DYNAMODB_INDEX_NAME"]
EXPIRATION_IN_S = os.environ["EXPIRATION_IN_S"] # 5 minutes

S3_BUCKET_NAME = os.environ["S3_BUCKET_NAME"]
S3_REPORT_PREFIX = os.environ["S3_REPORT_PREFIX"]

dynamodb = boto3.client('dynamodb')
s3 = boto3.client('s3')

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
    top_category = None if top_category is None or len(top_category) == 0 else top_category
    sub_category = None if sub_category is None or len(sub_category) == 0 else sub_category
    type = None if type is None or len(type) == 0 else type
    confidence_threshold = None if confidence_threshold is None or confidence_threshold < 50 else confidence_threshold

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
    
    # Get flatten items
    flat_items = get_flat_items(item["moderation_result_table"]["S"], top_category, sub_category, type, confidence_threshold)
  
    # store result to a csv file in s3
    local_file_name = f'{id}_{datetime.now().strftime("%Y%m%d%H%M%S")}.csv'
    with open("/tmp/" + local_file_name, 'w') as f:
        f.write('file_path,top_category,sub_category,confidence,reivew_result')
        for i in flat_items:
            f.write(f'\n{i["file_path"]},{i["top_category"]},{i["sub_category"]},{i["confidence"]},{i["type"]}')
    s3.upload_file("/tmp/" + local_file_name, S3_BUCKET_NAME, f'{S3_REPORT_PREFIX}{local_file_name}')

    # Generate S3 presigned URL
    response = s3.generate_presigned_url('get_object',
                        Params={'Bucket': S3_BUCKET_NAME,
                                'Key': f'{S3_REPORT_PREFIX}{local_file_name}'},
                        ExpiresIn=EXPIRATION_IN_S)

    return {
        'statusCode': 200,
        'body': response
    }

def get_flat_items(result_table, top_category, sub_category, type, confidence_threshold):
    flat_items = []
    # Scan result table: issued images
    d_response = dynamodb.query(
        TableName=result_table,
        IndexName=DYNAMO_INDEX_NAME,
        KeyConditionExpression='issue_flag = :i',
        ExpressionAttributeValues={
            ':i': {'N': '1'}
        }
    )
    
    for item in d_response["Items"]:
        flat_items = flatten_labels(item, flat_items, top_category, sub_category, type, confidence_threshold)

    last_key = d_response.get("LastEvaluatedKey")
    if last_key is not None:
        while last_key is not None:
            d_response = dynamodb.query(
                TableName=result_table,
                IndexName=DYNAMO_INDEX_NAME,
                KeyConditionExpression='issue_flag = :i',
                ExpressionAttributeValues={
                    ':i': {'N': '1'}
                },
                ExclusiveStartKey=last_key
            )
            last_key = d_response.get("LastEvaluatedKey")
            for item in d_response["Items"]:
                flat_items = flatten_labels(item, flat_items, top_category, sub_category, type, confidence_threshold)
    #print("////", flat_items)

    return flat_items

def flatten_labels(db_item, flat_items, top_category=None, sub_category=None, type=None, confidence_threshold=None):
    if db_item is None or "rek_results" not in db_item or len(db_item["rek_results"]["L"]) == 0:
        return flat_items
    
    if flat_items is None:
        flat_items = []
        
    for i in db_item["rek_results"]["L"]:
        if "M" not in i or i["M"] is None:
            continue
        
        # masage data to fix the data schema mis alignment.
        # For top category, Rek return parent_category="" and put the top category name into "category" field
        db_top_category = i["M"]["parent_category"]["S"]
        db_sub_category = i["M"]["category"]["S"]
        db_confidence = 0
        db_type = None
        if (db_top_category is None or len(db_top_category) == 0) and (db_sub_category is not None and len(db_sub_category) > 0):
            db_top_category = db_sub_category
            db_sub_category = ""
        if ("confidence" in i["M"] and i["M"]["confidence"]["N"] is not None):
            db_confidence = float(i["M"]["confidence"]["N"])
        if ("review_result" in i["M"] and "S" in i["M"]["review_result"] and len(i["M"]["review_result"]["S"]) > 0):
            db_type = i["M"]["review_result"]["S"]
        
        if ((top_category is None or db_top_category == top_category) \
            and (sub_category is None or db_sub_category == sub_category) \
            and (type is None or db_type == type) \
            and (confidence_threshold is None or db_confidence >= confidence_threshold)):
                fi = {
                    "file_path": db_item["file_path"]["S"],
                    "top_category": db_top_category,
                    "sub_category": db_sub_category,
                    "confidence": db_confidence,
                    "type": None
                }
                if i["M"]["review_result"] != {"NULL": True}:
                    fi["type"] = i["M"]["review_result"]["S"]
                flat_items.append(fi)
        
    return flat_items
        