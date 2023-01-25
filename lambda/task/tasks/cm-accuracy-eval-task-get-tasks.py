'''
Get all jobs from the DB table
'''
import json
import boto3
from datetime import datetime
import os

DYNAMO_TASK_TABLE = os.environ["DYNAMODB_TASK_TABLE"]

dynamodb = boto3.client('dynamodb')

def lambda_handler(event, context):

    table = boto3.resource('dynamodb').Table(DYNAMO_TASK_TABLE)
    d_response = dynamodb.scan(TableName=DYNAMO_TASK_TABLE)

    result = []
    for i in d_response["Items"]:
        result.append(unmarshalJson(i))
    
    return {
        'statusCode': 200,
        'body': json.dumps(result)
    }

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