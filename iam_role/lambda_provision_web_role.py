from aws_cdk import (
    Stack,
    aws_iam as _iam,
)
from constructs import Construct
from iam_role import policy

def create_role(self, bucket_name, region, account_id):
    # Trust
    new_role = _iam.Role(self, "lambda-provision-web-role",
        assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
    )
    # Log groups
    new_role.add_to_policy(
        policy.create_policy_lambda_log(self, bucket_name, region, account_id)
    )
    
    # Log groups
    new_role.add_to_policy(
        policy.create_policy_s3(self, bucket_name, region, account_id)
    )
    # Cognito
    new_role.add_to_policy(
        _iam.PolicyStatement(
            actions=["cloudfront:CreateInvalidation"],
            resources=["*"]
        )
    )
    # Lambda Invoke
    new_role.add_to_policy(
        _iam.PolicyStatement(
            actions=["lambda:InvokeFunction"],
            resources=["*"]
        )
    )
    return new_role