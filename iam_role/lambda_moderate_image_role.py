from aws_cdk import (
    Stack,
    aws_iam as _iam,
)
from constructs import Construct
from iam_role import policy

def create_role(self, bucket_name, region, account_id):
    # Trust
    new_role = _iam.Role(self, "lambda-moderate-image-role",
        assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
    )
    # S3
    new_role.add_to_policy(
        policy.create_policy_s3(self, bucket_name, region, account_id)
    )
    # Pass role: sagemaker
    new_role.add_to_policy(
        policy.create_policy_passrole_sagemaker(self, bucket_name, region, account_id)
    )
    # Pass role: rekognition
    new_role.add_to_policy(
        policy.create_policy_passrole_rekognition(self, bucket_name, region, account_id)
    )
    # Rekognition
    new_role.add_to_policy(
        policy.create_policy_rekognition(self, bucket_name, region, account_id)
    )
    # SageMaker - A2I
    new_role.add_to_policy(
        policy.create_policy_a2i(self, bucket_name, region, account_id)
    )
    # DynamoDB
    new_role.add_to_policy(
        policy.create_policy_dynamodb(self, bucket_name, region, account_id)
    )
    # Log groups
    new_role.add_to_policy(
        policy.create_policy_lambda_log(self, bucket_name, region, account_id)
    )
    return new_role