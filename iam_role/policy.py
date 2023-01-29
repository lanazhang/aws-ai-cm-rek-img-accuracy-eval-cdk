from aws_cdk import (
    Stack,
    aws_iam as _iam,
)
from constructs import Construct

def create_policy_s3(self, bucket_name, region, account_id):
    return  _iam.PolicyStatement(
            actions=["s3:GetObject*","s3:ListObjects", "s3:DeleteObject", "s3:DeleteObjectVersion", "s3:*File"],
            resources=[f"arn:aws:s3:::{bucket_name}"]
        )

def create_policy_passrole_sagemaker(self, bucket_name, region, account_id):
    return  _iam.PolicyStatement(
            actions=["iam:PassRole"],
            resources=["*"],
            conditions={
                "StringEquals": {
                    "iam:PassedToService": "sagemaker.amazonaws.com"
                }
            }
        )

def create_policy_passrole_rekognition(self, bucket_name, region, account_id):
    return  _iam.PolicyStatement(
            actions=["iam:PassRole"],
            resources=["*"],
            conditions={
                "StringEquals": {
                    "iam:PassedToService": "rekognition.amazonaws.com"
                }
            }
        )
        
def create_policy_rekognition(self, bucket_name, region, account_id):
    return  _iam.PolicyStatement(
            actions=["rekognition:DetectModerationLabels"],
            resources=["*"]
        )

def create_policy_a2i(self, bucket_name, region, account_id):
    return  _iam.PolicyStatement(
            actions=[
                "sagemaker:*HumanLoop*",
                "sagemaker:*FlowDefinition",
                "sagemaker:*Workteam*",
                "sagemaker:*Workforce*",
                "sagemaker:*HumanTaskUi*"
            ],
            resources=["*"]
        )

def create_policy_dynamodb(self, bucket_name, region, account_id):
    return  _iam.PolicyStatement(
            actions=["dynamodb:PutItem",
                "dynamodb:GetItem",
                "dynamodb:DescribeTable",
                "dynamodb:DeleteTable"],
            resources=[f"arn:aws:dynamodb:{region}:{account_id}:*"]
        )

def create_policy_lambda_log(self, bucket_name, region, account_id):
    return  _iam.PolicyStatement(
            actions=["logs:CreateLogGroup","logs:CreateLogStream","logs:PutLogEvents"],
            resources=[f"arn:aws:logs:{region}:{account_id}:*"]
        )