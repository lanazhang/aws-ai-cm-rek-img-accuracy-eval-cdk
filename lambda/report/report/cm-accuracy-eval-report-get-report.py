import json
import boto3
import math
import os

DYNAMO_TASK_TABLE = os.environ["DYNAMODB_TASK_TABLE"]
DYNAMO_INDEX_NAME = os.environ["DYNAMODB_INDEX_NAME"]

TP_STR = "true-positive"
FP_STR = "false-positive"

dynamodb = boto3.client('dynamodb')

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
    
    result = {
        "processed": 0,
        "labeled": 0,
        "reviewed": 0,
        "tp": 0,
        "fp": 0,
        "by_top_category": {},
        "by_sub_category": {},
        "by_type": {},
        "by_confidence": {},
        "by_top_category_type": {},
        "by_sub_category_type": {},
        "by_confidence_type": {},
    }
    # Get total processed images
    result["processed"] = get_total_processed(item["moderation_result_table"]["S"])
    
    # Get flatten items
    flat_items = get_flat_items(item["moderation_result_table"]["S"], top_category, sub_category, type, confidence_threshold)

    # Aggregate metrics
    by_top_category, by_sub_category, by_type, by_confidence, labeled, reviewed, fp, tp, by_top_category_type, by_sub_category_type, by_confidence_type \
        = aggregate_chart_data(flat_items)
    result["by_top_category"] = construct_list_with_count(by_top_category)
    result["by_sub_category"] = construct_list_with_count(by_sub_category)
    result["by_type"] = construct_list_with_count(by_type)
    result["by_confidence"] = construct_list_with_count(by_confidence, sort_key="title")
    result["labeled"] = len(labeled)
    result["reviewed"] = len(reviewed)
    result["fp"] = len(fp)
    result["tp"] = len(tp)
    
    result["by_top_category_type"][FP_STR] = construct_list_with_count(by_top_category_type[FP_STR])
    result["by_top_category_type"][TP_STR] = construct_list_with_count(by_top_category_type[TP_STR])
    result["by_sub_category_type"][FP_STR] = construct_list_with_count(by_sub_category_type[FP_STR])
    result["by_sub_category_type"][TP_STR] = construct_list_with_count(by_sub_category_type[TP_STR])
    result["by_confidence_type"][FP_STR] = construct_list_with_count(by_confidence_type[FP_STR], sort_key="title")
    result["by_confidence_type"][TP_STR] = construct_list_with_count(by_confidence_type[TP_STR], sort_key="title")
    
    
    return {
        'statusCode': 200,
        'body': json.dumps(result)
    }

def construct_list_with_count(dict, sort_key="value", reverse=True):
    result = []
    if dict is not None:
        for key, value in dict.items():
            result.append(
                {
                    "title": key,
                    "value": len(value) if value is not None else None
                }
            )

    return sorted(result, key=lambda d: d[sort_key], reverse=reverse)

# Get total images, processed, labeled
def get_total_processed(result_table):
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
    return processed

def aggregate_chart_data(flat_items):
    by_top_category, by_sub_category, by_type, by_confidence = {}, {}, {}, {}
    
    by_top_category_type, by_sub_category_type, by_confidence_type = {FP_STR: {}, TP_STR: {}}, {FP_STR: {}, TP_STR: {}}, {FP_STR: {}, TP_STR: {}}
    labeled, reviewed, tp, fp = [], [], [], []
    '''
    {
        "Suggestive": {
            "true-positive": 
        }
        FP_STR: {
            "Suggestive": 10,
            "Nudity": 3
        }
    }
    '''
    
    for item in flat_items:
        by_top_category = format_helper(item, "top_category", by_top_category)
        by_sub_category = format_helper(item, "sub_category", by_sub_category)
        by_type = format_helper(item, "type", by_type)
        
        # Round confidence score to a bucket: 10,20,30,40...100
        confidence_bucket = str(int((math.floor(item["confidence"] / 5))*5))
        by_confidence = format_helper(item, "confidence", by_confidence, key_name=confidence_bucket)
        
        # by type collections
        by_top_category_type = by_type_helper(item, "top_category", by_top_category_type)
        by_sub_category_type = by_type_helper(item, "sub_category", by_sub_category_type)
        by_confidence_type = by_type_helper(item, "confidence", by_confidence_type, key_name=confidence_bucket)

        # metrics
        if item["file_path"] not in labeled:
            labeled.append(item["file_path"])
        if item["type"] is not None and len(item["type"]) > 0 and item["file_path"] not in reviewed:
            reviewed.append(item["file_path"])
        if item["type"] == FP_STR and item["file_path"] not in fp:
            fp.append(item["file_path"])
        elif item["type"] == TP_STR and item["file_path"] not in tp:
            tp.append(item["file_path"])
    
    #print("!!!", by_top_category, by_sub_category, by_type, by_confidence)
    return by_top_category, by_sub_category, by_type, by_confidence, labeled, reviewed, fp, tp, by_top_category_type, by_sub_category_type, by_confidence_type

def by_type_helper(item, key, by_type_dict, key_name=None):
    if key_name is None:
        key_name = item.get(key)
    if key_name is None or len(key_name) == 0: 
        return by_type_dict
        
    file_path = item["file_path"]
    if item["type"] == FP_STR:
        if key_name not in by_type_dict[FP_STR].keys():
            by_type_dict[FP_STR][key_name] = [file_path]
        elif file_path not in by_type_dict[FP_STR][key_name]:
            by_type_dict[FP_STR][key_name].append(file_path)
    if item["type"] == TP_STR:
        if key_name not in by_type_dict[TP_STR].keys():
            by_type_dict[TP_STR][key_name] = [file_path]
        elif file_path not in by_type_dict[TP_STR][key_name]:
            by_type_dict[TP_STR][key_name].append(file_path)
    
    return by_type_dict

def format_helper(item, key, by_dict, key_name=None):
    if key_name is None:
        key_name = item.get(key)
    if key_name is None or len(key_name) == 0: 
        return by_dict
        
    if key_name not in by_dict.keys():
        by_dict[key_name] = [item["file_path"]]
    elif item["file_path"] not in by_dict[key_name]:
        by_dict[key_name].append(item["file_path"])
    return by_dict

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
                flat_items.append({
                    "file_path": db_item["file_path"]["S"],
                    "top_category": db_top_category,
                    "sub_category": db_sub_category,
                    "confidence": db_confidence,
                    "type": i["M"]["review_result"]["S"]
                })

    return flat_items
        