import json
import boto3
import uuid
from datetime import datetime
import time

MIN_CONFIDENCE = 50.0

rekognition = boto3.client('rekognition')
dynamodb = boto3.client('dynamodb')

def lambda_handler(event, context):
    if event is None:
        return {
        'statusCode': 400,
        'body': 'Missing parameters'
    }
    
    bucket_name = event["S3Bucket"]
    s3_key = event["S3Key"]

    dyanmodb_table = event["DynamoDBTable"]
    a2i_workflow_arn = event["A2IWorkFlowArn"]
    

    # Call Rekognition image moderation
    human_loop_name = f"rek-default-loop-{str(uuid.uuid4())}"
    
    start_ts = datetime.now()
    img_start_ts = time.time()

    try:
     rek_response = rekognition.detect_moderation_labels(
         Image={
            'S3Object': {
                'Bucket': bucket_name,
                'Name': s3_key,
            }
         },
         HumanLoopConfig={
            "FlowDefinitionArn":a2i_workflow_arn,
            "HumanLoopName": human_loop_name,
            "DataAttributes":{"ContentClassifiers":["FreeOfPersonallyIdentifiableInformation"]}
         },
         MinConfidence = MIN_CONFIDENCE
     )
    except Exception as ex:
      return {
         'statusCode': 500,
         'body': 'Moderation failed ' + s3_key
     }    
     
    # Construct result
    db_item = {
     "file_path": {
      "S": f"s3://{bucket_name}/{s3_key}"
     },
     "issue_flag": {
      "N": "0"
     },
     "reviewed_flag": {
      "N": "0"
     },
     "tp_flag": {
      "N": "0"
     },
     "fp_flag": {
      "N": "0"
     },
     "tn_flag": {
      "N": "0"
     },
     "fn_flag": {
      "N": "0"
     },     
     "moderation_duration_ms": {
      "N": str(time.time() - img_start_ts)
     },
     "moderation_min_confidence": {
      "N": str(MIN_CONFIDENCE)
     },
     "moderation_start_ts": {
      "S": start_ts.strftime('%Y/%m/%d %H:%M:%S UTC')
     },
     "rek_moderation_model_version": {
      "S": rek_response["ModerationModelVersion"]
     }
    }
    
    db_item["issue_flag"]["N"] = "1" if len(rek_response["ModerationLabels"]) > 0 else "0"
    if len(rek_response["ModerationLabels"]) > 0:
     db_item["rek_results"] = {"L":[]}
     for l in rek_response["ModerationLabels"]:
         db_item["rek_results"]["L"].append(
                    {
                         "M": {
                           "category": {
                            "S": l["Name"]
                           },
                           "confidence": {
                            "N": str(l["Confidence"])
                           },
                           "parent_category": {
                            "S": l["ParentName"]
                           },
                           "review_result": {
                            "NULL": True
                           }
                         }
                     }
             )
    print(dyanmodb_table, db_item)

    # Save result to DynamoDB
    db_response = dynamodb.put_item(
        TableName = dyanmodb_table,
        Item = db_item
    )
    
    msg = 'No invalid information detected.'
    if len(rek_response["ModerationLabels"]) > 0:
     msg = f'{len(rek_response["ModerationLabels"])} labels detected.'
    
    return msg