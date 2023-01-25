from aws_cdk import (
    Stack,
    aws_iam as _iam,
)
from constructs import Construct
from iam_role import policy

def create_role(self, bucket_name, region, account_id):
    # Trust
    new_role = _iam.Role(self, "lambda-update-status-role",
        assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
    )
    # DynamoDB
    new_role.add_to_policy(
        # DynamoDB access
        policy.create_policy_dynamodb(self, bucket_name, region, account_id)
    )
    # Log groups
    new_role.add_to_policy(
        # CloudWatch log
        policy.create_policy_lambda_log(self, bucket_name, region, account_id)
    )
    return new_role