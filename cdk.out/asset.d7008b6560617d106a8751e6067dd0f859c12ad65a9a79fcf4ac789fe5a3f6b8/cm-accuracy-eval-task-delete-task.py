import json
import boto3
import subprocess
import os

DYNAMO_TASK_TABLE = os.environ["DYNAMODB_TASK_TABLE"] 

s3 = boto3.client("s3")
dynamodb = boto3.client('dynamodb')
sagemaker = boto3.client('sagemaker')

def lambda_handler(event, context):
    id = event.get("id")
    if id is None:
        return {
            'statusCode': 400,
            'body': 'Missing paramters. Require id.'
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
            'body': "Task id doesn't exist"
        }   
    
    
    # Delete S3 folder: all the uploaded files
    cli = f'/opt/aws s3 rm --recursive s3://{item["s3_bucket"]["S"]}/{item["s3_key_prefix"]["S"]}'
    result = subprocess.Popen(cli,shell=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    output = result.communicate()[0].decode('UTF-8')

    # Delete A2I Workflow and the output S3 folder
    if "a2i_workflow_arn" in item and "S" in item["a2i_workflow_arn"] and len(item["a2i_workflow_arn"]["S"]) > 0:
        arr = item["a2i_workflow_arn"]["S"].split('/')
        fd_name = arr[len(arr)-1]
        sm_response = sagemaker.delete_flow_definition(
            FlowDefinitionName=fd_name
            )

        # Delete S3 folder: A2I output
        cli = f'/opt/aws s3 rm --recursive s3://{item["s3_bucket"]["S"]}/a2i/{fd_name}/'
        result = subprocess.Popen(cli,shell=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        output = result.communicate()[0].decode('UTF-8')
        print(f"3. Delete A2I workflow definition and the S3 fol: {sm_response}")
    else:
        print(f"3. No A2I workflow definition provisioned.")
    
    # Delete item from DB table
    d_response = dynamodb.delete_item(
        TableName=DYNAMO_TASK_TABLE,
        Key={
            'id': {
                'S': id,
            }
    })
    print("4. Delete task item in DB:", d_response)
    
    # Delete moderation table
    try:
        if "moderation_result_table" in item and "S" in item["moderation_result_table"] and len(item["moderation_result_table"]["S"]) > 0:
            d_response = dynamodb.delete_table(
                TableName=item["moderation_result_table"]["S"]
                )
            print("5. Delete moderation result table in DB: ", d_response)
        else:
            print("5. No moderation result table provisioned.")
    except Exception as ex:
        print("5. Failed to delete result table:", ex)
    
    
    return {
        'statusCode': 200,
        'body': f'Task {id} deleted'
    }
