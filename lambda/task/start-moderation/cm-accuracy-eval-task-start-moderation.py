'''
1. Read task item from DynamoDB
2. Check task status - exit flow if status is not 'CREATED'
3. Count nummbers of files in the S3 bucket path - exit flow if no file uploaded (a temp file in the folder so the number should be greater than 1)
4. Create dynamodb table keeps moderation result for the task - ignore if exists
5. Create A2I workflow definition
6. Start the Step Function execution - bulk moderation images in the S3 bucket
7. Update the DB item
'''
import json
import boto3
import uuid
from datetime import datetime
import os

TASK_STATUS = "MODERATING"
DYNAMO_TASK_TABLE = os.environ["DYNAMODB_TASK_TABLE"]
DYNAMO_RESULT_TABLE_PREFIX = os.environ["DYNAMODB_RESULT_TABLE_PREFIX"]
WORK_FLOW_NAME_PREFIX = os.environ["WORK_FLOW_NAME_PREFIX"]
HUMAN_TASK_UI_NAME = os.environ["HUMAN_TASK_UI_NAME"].split('/')[-1]
STEP_FUNCTION_STATE_MACHINE_ARN = os.environ["STEP_FUNCTION_STATE_MACHINE_ARN"]

s3 = boto3.client("s3")
sfn = boto3.client("stepfunctions")
dynamodb = boto3.client('dynamodb')
sagemaker = boto3.client('sagemaker')
lambda_client = boto3.client('lambda')

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
    print("1. Get db item: ", d_response)

    item = unmarshalJson(d_response["Item"])
    print("2. Convert db item to normal json: ", item)
    if item["status"] != "CREATED":
        return {
            'statusCode': 400,
            'body': f'The accuracy evaluation task has already started the moderation. Task status: {item["status"]}'
        }

    # Get numbers of images in the s3 path
    object_keys = get_all_object_keys(item["s3_bucket"], item["s3_key_prefix"])
    item["total_files"] = str(len(object_keys))
    print(f'3. Count numbers of files in the s3 path: s3://{item["s3_bucket"]}/{item["s3_key_prefix"]}. Total:', item["total_files"])
    if item["total_files"] == "0":
        return {
            'statusCode': 400,
            'body': f'No image found in the S3 bucket. S3 URI: s3://{item["s3_bucket"]}/{item["s3_key_prefix"]}'
        }        
    

    # Create A2I workflow
    a2i_workflow_arn = createA2iWorkflow(item["id"], item["s3_bucket"], WORK_FLOW_NAME_PREFIX + '-' + item["id"])
    print("5. Create A2I workflow: ", a2i_workflow_arn )
    item["a2i_workflow_arn"] = a2i_workflow_arn


    # Trigger Step function moderation flow
    params = {
          "TaskId": item["id"],
          "S3Bucket": item["s3_bucket"],
          "S3Prefix": item["s3_key_prefix"],
          "DynamoDBTable": item["moderation_result_table"],
          "A2IWorkFlowArn": item["a2i_workflow_arn"]
        }
    sfn_response = sfn.start_execution(
            stateMachineArn = STEP_FUNCTION_STATE_MACHINE_ARN,
            name = WORK_FLOW_NAME_PREFIX+"-" + item["id"] + f"-{str(uuid.uuid4())[0:5]}",
            input = json.dumps(params),
        )
    item["step_function_execution_arn"] = sfn_response["executionArn"]
    item["moderation_started_ts"] = datetime.now().strftime('%Y/%m/%d %H:%M:%S UTC')
    print("6. Start step function execution: ", item["step_function_execution_arn"])
    
    # Update DB item
    item["status"] = TASK_STATUS
    d_response = dynamodb.put_item(
        TableName=DYNAMO_TASK_TABLE,
        Item=constructDynamoItem(item),
    )
    print("7. Updated task db: ", item)
    
    return {
        'statusCode': 200,
        'body': json.dumps(item)
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
            d_item[key] = {'N': value}

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
            
def createA2iWorkflow(task_id, s3_bucket, workflow_name):
    #workflow_name = workflow_name.lower().replace(' ','-')
    print(">>>>> Workflow_name", workflow_name)
    
    # Check if already exists
    try:
      describe_flow_response = sagemaker.describe_flow_definition(FlowDefinitionName=WORK_FLOW_NAME_PREFIX + task_id)
      if "FlowDefinitionArn" in describe_flow_response:
        event['A2IWorkFlowArn'] = describe_flow_response["FlowDefinitionArn"]
        return event
    except:
      print("Flow definition doesn't exsit.")

    # Get WorkTeam Arn
    work_team_arn = sagemaker.list_workteams()["Workteams"][0]["WorkteamArn"]
    
    # Get UI Template ARN
    ui_template_arn = sagemaker.describe_human_task_ui(HumanTaskUiName=HUMAN_TASK_UI_NAME)["HumanTaskUiArn"]
    
    # Get current Lambda execution role arn
    role_response = (lambda_client.get_function_configuration(
        FunctionName = os.environ['AWS_LAMBDA_FUNCTION_NAME'])
    )
    role_arn = role_response['Role']

    activation_condition = json.dumps(
        {
          "Conditions": [
            {
              "And": [
                {
                  "ConditionType": "ModerationLabelConfidenceCheck",
                  "ConditionParameters": {
                    "ModerationLabelName": "*",
                    "ConfidenceLessThan": 100
                  }
                },
                {
                  "ConditionType": "ModerationLabelConfidenceCheck",
                  "ConditionParameters": {
                    "ModerationLabelName": "*",
                    "ConfidenceGreaterThan": 50
                  }
                }
              ]
            }
          ]
        }
    )

    flow_response = sagemaker.create_flow_definition(
            FlowDefinitionName= WORK_FLOW_NAME_PREFIX + task_id,
            RoleArn= role_arn,
            HumanLoopConfig= {
                "WorkteamArn": work_team_arn,
                "HumanTaskUiArn": ui_template_arn,
                "TaskCount": 1,
                "TaskDescription": workflow_name,
                "TaskTitle": workflow_name
            },
            HumanLoopRequestSource={
                "AwsManagedHumanLoopRequestSource": "AWS/Rekognition/DetectModerationLabels/Image/V3"
            },
            HumanLoopActivationConfig={
                "HumanLoopActivationConditionsConfig": {
                    "HumanLoopActivationConditions": activation_condition
                }
            },
            OutputConfig={
                "S3OutputPath" : f's3://{s3_bucket}/a2i/'
            }
        )
    
    return flow_response['FlowDefinitionArn']

def get_all_object_keys(bucket, prefix, start_after = '', keys = []):
    response = s3.list_objects_v2(
        Bucket     = bucket,
        Prefix     = prefix,
        StartAfter = start_after
    )

    if 'Contents' not in response:
        return keys

    key_list = response['Contents']
    last_key = key_list[-1]['Key']

    keys.extend(key_list)

    return get_all_object_keys(bucket, prefix, last_key, keys)