from aws_cdk import (
    Stack,
    aws_iam as _iam,
)
from constructs import Construct
from iam_role import policy


def create_role(self, bucket_name, region, account_id):
    # IAM role
    s3_trigger_role = _iam.Role(self, "lambda-s3-trigger-role",
        assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
    )
    s3_trigger_role.add_to_policy(
        # S3 read access
        policy.create_policy_s3(self, bucket_name, region, account_id)
    )
    s3_trigger_role.add_to_policy(
        # DynamoDB access
        policy.create_policy_dynamodb(self, bucket_name, region, account_id)
    )
    s3_trigger_role.add_to_policy(
        # CloudWatch log
        policy.create_policy_lambda_log(self, bucket_name, region, account_id)
    )
    return s3_trigger_role