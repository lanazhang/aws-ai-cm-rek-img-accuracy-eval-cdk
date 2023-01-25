import json
import boto3
import subprocess
from ast import literal_eval
from boto3.dynamodb.conditions import Key, Attr
import os

DYNAMO_TASK_TABLE = os.environ["DYNAMODB_TASK_TABLE"]
SUPPORTED_FILE_TYPES = os.environ["SUPPORTED_FILE_TYPES"].split(',')
DYNAMO_INDEX_NAME = os.environ["DYNAMODB_INDEX_NAME"]

dynamodb = boto3.client('dynamodb')
s3 = boto3.client('s3')
sagemaker = boto3.client('sagemaker')

def lambda_handler(event, context):
    id = event.get("id")
    if id is None:
        return {
            'statusCode': 400,
            'body': 'Missing paramters. Require id.'
        }   
        
    result ={}
    
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
            'body': "Task id doesn't exist"
        }   

    # Get S3 file count if status is "CREATED"
    if item["status"]["S"] == "CREATED":
        total = 0
        try:
            # Delete the temp file if exisis
            s3.delete_object(Bucket=item["s3_bucket"]["S"], Key=item["s3_key_prefix"]["S"] + ".temp")

            # Get S3 object count using AWS CLI (in base layer)
            cli = f'/opt/aws s3api list-objects --bucket {item["s3_bucket"]["S"]} --prefix {item["s3_key_prefix"]["S"]} --output json --query "[length(Contents[])]"'
            result = subprocess.Popen(cli,shell=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            output = result.communicate()[0].decode('UTF-8')
            total = literal_eval(output)[0]
            item["total_files"] = {"N": str(total)}
            print("2. Get S3 object count: ", total)
            
            # Update DB
            d_response = dynamodb.put_item(
                TableName=DYNAMO_TASK_TABLE,
                Item=item,
            )
            print("3. Update DB: ", item)
        except Exception as ex:
            print("Failed to get S3 object count", ex)        

    item = unmarshalJson(item)
    
    # Get A2I login URL
    a2i_url = None
    try:
        work_team_arn = sagemaker.list_workteams()["Workteams"][0]["WorkteamArn"]
        workteamName = work_team_arn[work_team_arn.rfind('/') + 1:]
        item["a2i_url"] = 'https://' + sagemaker.describe_workteam(WorkteamName=workteamName)['Workteam']['SubDomain']
        item["a2i_job_title"] = item["a2i_workflow_arn"].split("/")[-1]
        print("4. Get A2I URL: ", item["a2i_url"], item["a2i_job_title"])
    except Exception as ex:
        print("Failed to get A2I portal URL: ", ex)
        
    
    # Get moderation/review metrics
    processed, labeled, reviewed, tp, tn, fp, fn = 0, 0, 0, 0, 0, 0, 0
    if item["status"] != "CREATED":
        processed, labeled, reviewed, tp, tn, fp, fn = get_metrics(item["moderation_result_table"])
    item["processed"] = processed
    item["labeled"] = labeled
    item["reviewed"] = reviewed
    item["true_positive"] = tp
    item["true_negative"] = tn
    item["false_positive"] = fp
    item["false_negative"] = fn
        
    return {
        'statusCode': 200,
        'body': json.dumps(item)
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

def get_metrics(result_table):
    # Scan result table with pagination: Total
    processed = 0
    d_response = dynamodb.scan(
        Select="COUNT",
        TableName=result_table,
    )
    processed = d_response["Count"]
    last_key = d_response.get("LastEvaluatedKey")
    if last_key is not None:
        while last_key is not None:
            d_response = dynamodb.scan(
                Select="COUNT",
                TableName=result_table,
                ExclusiveStartKey=last_key
            )
            last_key = d_response.get("LastEvaluatedKey")
            processed += d_response["Count"]
    #print("////", processed)

    # Scan result table: issued images
    labeled, reviewed, fp, fn, tp, tn = 0, 0, 0, 0, 0, 0
    d_response = dynamodb.query(
        TableName=result_table,
        IndexName=DYNAMO_INDEX_NAME,
        KeyConditionExpression='issue_flag = :i',
        ExpressionAttributeValues={
            ':i': {'N': '1'}
        }
    )
    labeled, reviewed, tp, tn, fp, fn = count_flags(d_response["Items"], labeled, reviewed, tp, tn, fp, fn)
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
            labeled, reviewed, tp, tn, fp, fn = count_flags(d_response["Items"], labeled, reviewed, tp, tn, fp, fn)
    #print("////", labeled, reviewed, tp, tn, fp, fn)

    return processed, labeled, reviewed, tp, tn, fp, fn

def count_flags(items, labeled, reviewed, tp, tn, fp, fn):
    labeled += len(items)
    for i in items:
        if i["reviewed_flag"]["N"] == "1":
            reviewed += 1
        if i["fp_flag"]["N"] == "1":
            fp += 1
        if i["fn_flag"]["N"] == "1":
            fn += 1
        if i["tp_flag"]["N"] == "1":
            tp += 1
        if i["tn_flag"]["N"] == "1":
            tn += 1    
    return labeled, reviewed, tp, tn, fp, fn