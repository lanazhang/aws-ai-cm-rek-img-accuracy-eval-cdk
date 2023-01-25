import json
import boto3
import uuid
from datetime import datetime
import os

S3_BUCKET = os.environ["S3_BUCKET"]
S3_KEY_PREFIX = os.environ["S3_KEY_PREFIX"]
DYNAMO_TASK_TABLE = os.environ["DYNAMODB_TASK_TABLE"]
DYNAMO_RESULT_TABLE_PREFIX = os.environ["DYNAMODB_RESULT_TABLE_PREFIX"]

JOB_STATUS = "CREATED"

s3 = boto3.client("s3")
sfn = boto3.client("stepfunctions")
dynamodb = boto3.client('dynamodb')

def lambda_handler(event, context):
    name = event.get("task_name")
    description = event.get("task_description")
    created_by = event.get("created_by")
    
    result = {}
    
    if name is None or created_by is None:
        return {
            'statusCode': 400,
            'body': 'Missing paramters. Require taks_name and created_by.'
        }        
        
    id = str(uuid.uuid4())
    task = {
        "id": id,
        "name": name,
        "description": description,
        "s3_bucket":S3_BUCKET,
        "s3_key_prefix": f'{S3_KEY_PREFIX}{id}/',
        "created_by": created_by,
        "created_ts": datetime.now().strftime('%Y/%m/%d %H:%M:%S UTC'),
        "status": JOB_STATUS,
        "moderation_result_table": None,
        "a2i_workflow_arn": None,
        "last_update_ts": datetime.now().strftime('%Y/%m/%d %H:%M:%S UTC'),
        "total_files": None,
    }
    
    # Create S3 folder with empty file
    s3_response = s3.put_object(
        Bucket= S3_BUCKET,
        Key= S3_KEY_PREFIX + id + "/.temp",
        Body=b'',
    )
    
    # Create DB table for moderation result
    task["moderation_result_table"] = f"{DYNAMO_RESULT_TABLE_PREFIX}{id}"
    try:
        dyn_resource = boto3.resource('dynamodb')
        table = dyn_resource.create_table(
            TableName=task["moderation_result_table"],
            KeySchema=[
                {
                    'AttributeName': 'file_path',
                    'KeyType': 'HASH'  #Partition key
                }
            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'file_path',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'issue_flag',
                    'AttributeType': 'N'
                }
            ],
            GlobalSecondaryIndexes=[
                {
                    'IndexName': 'issue_flag-index',
                    'KeySchema': [
                        {
                            'AttributeName': 'issue_flag',
                            'KeyType': 'HASH'  #Partition key
                        }
                    ],
                    'Projection': {
                        'ProjectionType': 'ALL'
                    }
                }
            ],
            BillingMode= "PAY_PER_REQUEST",
        )

        print("Created moderation table: ", task["moderation_result_table"])
    except Exception as ex:
        print("Failed to create moderation table: ", ex)

    # Create task in DB table
    d_response = dynamodb.put_item(
        TableName=DYNAMO_TASK_TABLE,
        Item=constructDynamoItem(task),
    )

    # Get item from DB table
    if d_response["ResponseMetadata"]["HTTPStatusCode"] == 200:
        d_response = dynamodb.get_item(
            TableName=DYNAMO_TASK_TABLE,
            Key={"id" : { "S": id}}
        )    
        result = unmarshalJson(d_response["Item"])

    return {
        'statusCode': 200,
        'body': json.dumps(result)
    }

def constructDynamoItem(item):
    d_item = {}
    for key, value in item.items():
        if value is None:
            d_item[key] = {'NULL': True}
        elif type(key) == str:
            d_item[key] = {'S': value}
        elif type(key) == datetime:
            d_item[key] = {'S': value.strftime('%Y/%m/%d %H:%M:%s UTC')}
        elif type(key) == bool:
            d_item[key] = {'BOOL': value}
        elif type(key) == int or type(key) == float:
            d_item[key] = {'N': str(value)}

    return d_item

def unmarshalJson(node):
    data = {}
    data["M"] = node
    return unmarshalValue(data, True)


def unmarshalValue(node, mapAsObject):
    for key, value in node.items():
        if(key == "S" or key == "N"):
            return value
        if(key == "M" or key == "L"):
            if(key == "M"):
                if(mapAsObject):
                    data = {}
                    for key1, value1 in value.items():
                        data[key1] = unmarshalValue(value1, mapAsObject)
                    return data
            data = []
            for item in value:
                data.append(unmarshalValue(item, mapAsObject))
            return data