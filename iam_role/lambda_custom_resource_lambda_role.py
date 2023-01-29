from aws_cdk import (
    Stack,
    aws_iam as _iam,
)
from constructs import Construct
from iam_role import policy

def create_role(self, bucket_name, region, account_id):
    # Trust
    new_role = _iam.Role(self, "lambda-custom-res-lambda-role",
        assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
    )
    # Log groups
    new_role.add_to_policy(
        policy.create_policy_lambda_log(self, bucket_name, region, account_id)
    )
    
    # Lambda Invoke
    new_role.add_to_policy(
        _iam.PolicyStatement(
            actions=["lambda:InvokeFunction"],
            resources=["*"]
        )
    )
    return new_role