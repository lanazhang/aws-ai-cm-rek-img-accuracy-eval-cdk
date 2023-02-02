import json
import boto3
from datetime import datetime
import os

VALID_STATUS = ["CREATED", "MODERATING", "MODERATION_COMPLETED", "HUMAN_REVIEWING", "COMPLETED", "FAILED"]
DYNAMO_TASK_TABLE = os.environ["DYNAMODB_TASK_TABLE"]

dynamodb = boto3.client('dynamodb')

def lambda_handler(event, context):
    id = event.get("id")
    if id is None:
        id = event.get("TaskId")
    status = event.get("status")
    if id is None or status is None:
        return {
            'statusCode': 400,
            'body': "Missing parameters. Require id and status."
        }
    
    status = status.upper()
    if not status in VALID_STATUS:
        return {
            'statusCode': 400,
            'body': f'Invalid status: {status}. Supported status: {", ".join(VALID_STATUS)}'
        }
        
    # Get task item from DB table
    d_response = dynamodb.get_item(
        TableName=DYNAMO_TASK_TABLE,
        Key={"id" : { "S": id}}
    )        
    item = d_response["Item"]
    
    # Update DB item
    item["status"]["S"] = status
    d_response = dynamodb.put_item(
        TableName=DYNAMO_TASK_TABLE,
        Item=item,
    )
    
    # TODO implement
    return {
        'statusCode': 200,
        'body': json.dumps(item)
    }