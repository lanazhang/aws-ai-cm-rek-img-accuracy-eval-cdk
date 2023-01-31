from aws_cdk import (
    Stack,
    aws_iam as _iam,
)
from constructs import Construct
from iam_role import policy
def create_role(self, bucket_name, region, account_id):
    # Trust
    new_role = _iam.Role(self, "step-function-role",
        assumed_by=_iam.ServicePrincipal("states.amazonaws.com"),
    )
    # S3
    new_role.add_to_policy(
        # S3 read access
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
    # Lambda invoke
    new_role.add_to_policy(
        _iam.PolicyStatement(
            actions=["lambda:InvokeFunction"],
            resources=[f"arn:aws:lambda:{region}:{account_id}:*"]
        )
    )   
    # StepFunctions
    # Lambda invoke
    new_role.add_to_policy(
        _iam.PolicyStatement(
            actions=["states:*"],
            resources=["*"]
        )
    )   
    # X-ray
    new_role.add_to_policy(
        # DynamoDB access
        _iam.PolicyStatement(
            actions=["xray:PutTelemetryRecords", 
            "xray:GetSamplingTargets",
            "xray:PutTraceSegments",
            "xray:GetSamplingRules"],
            resources=["*"]
        )
    )  
    # Log groups
    new_role.add_to_policy(
        policy.create_policy_lambda_log(self, bucket_name, region, account_id)
    )
    return new_role