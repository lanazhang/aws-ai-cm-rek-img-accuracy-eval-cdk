from aws_cdk import (
    Stack,
    CfnParameter as _cfnParameter,
    aws_cognito as _cognito,
    aws_s3 as _s3,
    aws_dynamodb as _dynamodb,
    aws_lambda as _lambda,
    aws_apigateway as _apigw,
    aws_iam as _iam,
    Environment,
    Duration,
    aws_s3_notifications,
    aws_stepfunctions as _aws_stepfunctions,
    RemovalPolicy,
    custom_resources as cr,
    CfnOutput,
    CustomResource
)
from aws_cdk.aws_logs import RetentionDays
from constructs import Construct
import os
import uuid
import json

from iam_role.lambda_provision_role import create_role as lambda_provision_role
from iam_role.lambda_custom_resource_lambda_role import create_role as lambda_custom_res_role

COGNITO_NAME_PREFIX = 'cm-accuracy-eval-user-pool'
COGNITO_USER_POOL_NAME = 'cm-accuracy-eval-user-pool'
COGNITO_CLIENT_NAME = 'web-client'
COGNITO_GROUP_NAME = 'admin'
COGNITO_USER_POOL_DOMAIN = 'accuracy-eval'

S3_BUCKET_NAME_PREFIX = "cm-accuracy-eval"

A2I_WORKFLOW_NAME_PREFIX = "cm-accuracy-"
A2I_UI_TEMPLATE_NAME = "cm-accuracy-eval-image-review-ui-template"
A2I_WORK_FORCE_NAME = 'cm-accuracy-eval-workforce'
A2I_WORK_TEAM_NAME = 'cm-accuracy-eval-workteam'

class A2iProvision(Stack):
    instance_hash = None
    region = None
    account_id = None
    ouput_cognito_user_pool_id = None

    def __init__(self, scope: Construct, construct_id: str, instance_hash_code,**kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.instance_hash = instance_hash_code #str(uuid.uuid4())[0:5]
        
        self.account_id = os.getenv('CDK_DEFAULT_ACCOUNT')
        self.region = os.getenv('CDK_DEFAULT_REGION')
        bucket_name = f'{S3_BUCKET_NAME_PREFIX}-{self.account_id}-{self.region}-{self.instance_hash}'
        
        user_emails = _cfnParameter(self, "userEmails", type="String", default="lanaz@amazon.com",
                                    description="The emails for users to log in to the website and A2I. Split by a comma if multiple. You can always add new users after the system is deployed.")
        
        work_team_arn, a2i_ui_template_arn, cognito_user_pool_arn = None, None, None
       
        # Custom Resource Lambda: cm-accuracy-eval-provision-custom-resource
        lambda_provision = _lambda.Function(self, 
            id='provision-custom-resource', 
            function_name=f"cm-accuracy-eval-provision-custom-resource-{self.instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler='cm-accuracy-eval-provision-custom-resource.on_event',
            code=_lambda.Code.from_asset(os.path.join("./", "lambda/provision")),
            timeout=Duration.seconds(60),
            role=lambda_provision_role(self,bucket_name, self.region, self.account_id),
            memory_size=512,
            environment={
             'HUMAN_TASK_UI_NAME': f"{A2I_UI_TEMPLATE_NAME}-{self.instance_hash}",
             'COGNITO_USER_EMAILS':user_emails.value_as_string,
             'WORKFORCE_NAME': f'{A2I_WORK_FORCE_NAME}-{self.instance_hash}',
             'WORKTEAM_NAME': f'{A2I_WORK_TEAM_NAME}-{self.instance_hash}',
             'COGNITO_USER_POOL_NAME':f'{COGNITO_USER_POOL_NAME}-{self.instance_hash}',
             'COGNITO_CLIENT_NAME': f'{COGNITO_CLIENT_NAME}-{self.instance_hash}',
             'COGNITO_GROUP_NAME': f'{COGNITO_GROUP_NAME}-{self.instance_hash}',
             'COGNITO_USER_POOL_DOMAIN': f'{COGNITO_USER_POOL_DOMAIN}-{self.instance_hash}'
            }
        ) 
        c_resource = cr.AwsCustomResource(
            self,
            f"provision-provider-{self.instance_hash}",
            log_retention=RetentionDays.ONE_WEEK,
            on_create=cr.AwsSdkCall(
                service="Lambda",
                action="invoke",
                physical_resource_id=cr.PhysicalResourceId.of("Trigger"),
                parameters={
                    "FunctionName": lambda_provision.function_name,
                    "InvocationType": "RequestResponse",
                    "Payload": "{\"RequestType\": \"Create\"}"
                },
                output_paths=["Payload"]
            ),
            on_delete=cr.AwsSdkCall(
                service="Lambda",
                action="invoke",
                physical_resource_id=cr.PhysicalResourceId.of("Trigger"),
                parameters={
                    "FunctionName": lambda_provision.function_name,
                    "InvocationType": "RequestResponse",
                    "Payload": "{\"RequestType\": \"Delete\"}"
                },
                # output_paths=["info.current"]
            ),
            role=lambda_custom_res_role(self, bucket_name, self.region, self.account_id)
        )       
        
        self.ouput_cognito_user_pool_id = c_resource.get_response_field("Payload")
        CfnOutput(self, id="CognitoUserPoolIds", value=self.ouput_cognito_user_pool_id, export_name="CognitoUserPoolId,CognitoUserPoolClientId")
