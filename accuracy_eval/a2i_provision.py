import aws_cdk as cdk
from aws_cdk import (
    Stack,
    NestedStack,
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
    CustomResource,
    Token,
    Duration,
    Fn
)
from aws_cdk.aws_logs import RetentionDays
from constructs import Construct
import os
import uuid
import json
from accuracy_eval.constant import *

from iam_role.lambda_provision_role import create_role as lambda_provision_role
from iam_role.lambda_custom_resource_lambda_role import create_role as lambda_custom_res_role
from iam_role.lambda_s3_trigger_role import create_role as create_lambda_s3_trigger_role

class A2iProvision(NestedStack):
    instance_hash = None
    region = None
    account_id = None
    ouput_cognito_user_pool_id = None
    user_emails = None

    def __init__(self, scope: Construct, construct_id: str, instance_hash_code, user_emails, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.instance_hash = instance_hash_code #str(uuid.uuid4())[0:5]
        self.user_emails = user_emails
        
        self.account_id=os.environ.get("CDK_DEPLOY_ACCOUNT", os.environ["CDK_DEFAULT_ACCOUNT"])
        self.region=os.environ.get("CDK_DEPLOY_REGION", os.environ["CDK_DEFAULT_REGION"])

        bucket_name = f'{S3_BUCKET_NAME_PREFIX}-{self.account_id}-{self.region}-{self.instance_hash}'
        
        work_team_arn, a2i_ui_template_arn, cognito_user_pool_arn = None, None, None
       
        # Create S3 bucket
        bucket_name = f'{S3_BUCKET_NAME_PREFIX}-{self.account_id}-{self.region}-{self.instance_hash}'
        s3_bucket = _s3.Bucket(self, 
            id='cm-eval-bucket', 
            bucket_name=bucket_name, 
            removal_policy=RemovalPolicy.DESTROY,
            cors=[_s3.CorsRule(
                allowed_headers=["*"],
                allowed_methods=[_s3.HttpMethods.GET],
                allowed_origins=["*"])
            ])
            
        # Create Lambdas
        # Lambda: cm-accuracy-eval-task-s3-a2i-etl
        lambda_s3_trigger = _lambda.Function(self, 
            id='s3-trigger', 
            function_name=f"cm-accuracy-eval-task-s3-a2i-etl-{self.instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler='cm-accuracy-eval-task-s3-a2i-etl.lambda_handler',
            code=_lambda.Code.from_asset(os.path.join("./", "lambda/task/s3-trigger")),
            timeout=Duration.seconds(30),
            role=create_lambda_s3_trigger_role(self,bucket_name, self.region, self.account_id),
            memory_size=5120,
            environment={
             'DYNAMODB_TABLE_PREFIX': f'{DYNAMOBD_DETAIL_TABLE_PREFIX}-{self.instance_hash}',
             'DYNAMODB_TASK_TABLE': DYNAMOBD_TASK_TABLE_PREFIX + f"-{self.instance_hash}",
             'DYNAMODB_INDEX_NAME': DYNAMOBD_DETAIL_TABLE_LABELED_INDEX_NAME,
            }
        )
        # create s3 notification for lambda function
        s3_bucket.add_event_notification(
                _s3.EventType.OBJECT_CREATED, 
                aws_s3_notifications.LambdaDestination(lambda_s3_trigger), 
                _s3.NotificationKeyFilter(
                    prefix=S3_A2I_PREFIX,
                    suffix=".json",
                ))
            
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
             'COGNITO_GT_GROUP_NAME': f'{COGNITO_GT_GROUP_NAME}',
             'COGNITO_USER_POOL_DOMAIN': f'{COGNITO_USER_POOL_DOMAIN}-{self.instance_hash}',
             'S3_BUCKET_NAME': s3_bucket.bucket_name,
             'S3_BUCKET_TEMP_FILE_KEY': S3_BUCKET_TEMP_FILE_KEY
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
            ),
            role=lambda_custom_res_role(self, bucket_name, self.region, self.account_id)
        )
        
        self.ouput_cognito_user_pool_id = Fn.join('',Fn.split('"',c_resource.get_response_field("Payload")))
        CfnOutput(self, id="CognitoUserPoolId", value=self.ouput_cognito_user_pool_id, export_name="CognitoUserPoolId")
