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

from iam_role.lambda_s3_trigger_role import create_role as create_lambda_s3_trigger_role
from iam_role.lambda_moderate_image_role import create_role as create_lambda_moderate_image_role
from iam_role.lambda_update_status_role import create_role as create_lambda_update_status_role
from iam_role.step_functions_sm_role import create_role as create_step_function_role
from iam_role.lambda_get_images_role import create_role as create_lambda_get_images_role
from iam_role.lambda_get_report_role import create_role as create_lambda_get_report_role
from iam_role.lambda_get_tasks_role import create_role as create_lambda_get_tasks_role
from iam_role.lambda_create_task_role import create_role as create_lambda_create_task_role
from iam_role.lambda_delete_task_role import create_role as create_lambda_delete_task_role
from iam_role.lambda_start_moderation_role import create_role as lambda_start_moderation_role
from iam_role.lambda_get_task_with_count_role import create_role as lambda_get_task_with_count_role
from iam_role.lambda_provision_role import create_role as lambda_provision_role

COGNITO_NAME_PREFIX = 'cm-accuracy-eval-user-pool'

DYNAMOBD_TASK_TABLE_PREFIX = "cm-accuracy-eval-task"
DYNAMOBD_DETAIL_TABLE_PREFIX = "cm-accuracy-"
DYNAMOBD_DETAIL_TABLE_LABELED_INDEX_NAME = "issue_flag-index"

S3_BUCKET_NAME_PREFIX = "cm-accuracy-eval"
S3_INPUT_PREFIX = "input/"
S3_A2I_PREFIX = "a2i/"
S3_PRE_SIGNED_URL_EXPIRATION_IN_S = "300"

API_NAME_PREFIX = "cm-accuracy-eval-srv"
STEP_FUNCTION_STATE_MACHINE_NAME_PREFIX = "cm-accuracy-eval-image-sm"
A2I_WORKFLOW_NAME_PREFIX = "cm-accuracy-"
A2I_UI_TEMPLATE_NAME = "cm-accuracy-eval-image-review-ui-template"
A2I_WORK_FORCE_NAME = 'cm-accuracy-eval-workforce'
A2I_WORK_TEAM_NAME = 'cm-accuracy-eval-workteam'

COGNITO_USER_POOL_NAME = 'cm-accuracy-eval-user-pool'
COGNITO_CLIENT_NAME = 'web-client'
COGNITO_GROUP_NAME = 'admin'
COGNITO_USER_POOL_DOMAIN = 'accuracy-eval'

class AccuracyEval(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        REGION = Stack.of(self).region
        ACCOUNT_ID = Stack.of(self).account

        user_emails = _cfnParameter(self, "userEmails", type="String", default="lanaz@amazon.com",
                                    description="The emails for users to log in to the tool and A2I. Split by a comma if multiple. You can always add new users after the system is deployed.")
        
        instance_hash = str(uuid.uuid4())[0:5]
        work_team_arn, a2i_ui_template_arn, cognito_user_pool_arn = None, None, None
        
        # Create S3 bucket
        bucket_name = f'{S3_BUCKET_NAME_PREFIX}-{ACCOUNT_ID}-{REGION}-{instance_hash}'
        s3_bucket = _s3.Bucket(self, 
            id='cm-eval-bucket', 
            bucket_name=bucket_name, 
            removal_policy=RemovalPolicy.DESTROY,
            cors=[_s3.CorsRule(
                allowed_headers=["*"],
                allowed_methods=[_s3.HttpMethods.GET],
                allowed_origins=["*"])
            ])
       
        # Custom Resource Lambda: cm-accuracy-eval-provision-custom-resource
        provision_role = lambda_provision_role(self,bucket_name, REGION, ACCOUNT_ID)
        lambda_provision = _lambda.Function(self, 
            id='provision-custom-resource', 
            function_name=f"cm-accuracy-eval-provision-custom-resource-{instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler='cm-accuracy-eval-provision-custom-resource.on_event',
            code=_lambda.Code.from_asset(os.path.join("./", "lambda/provision")),
            timeout=Duration.seconds(60),
            role=provision_role,
            memory_size=512,
            environment={
             'HUMAN_TASK_UI_NAME': f"{A2I_UI_TEMPLATE_NAME}-{instance_hash}",
             'COGNITO_USER_EMAILS':user_emails.value_as_string,
             'WORKFORCE_NAME': f'{A2I_WORK_FORCE_NAME}-{instance_hash}',
             'WORKTEAM_NAME': f'{A2I_WORK_TEAM_NAME}-{instance_hash}',
             'COGNITO_USER_POOL_NAME':f'{COGNITO_USER_POOL_NAME}-{instance_hash}',
             'COGNITO_CLIENT_NAME': f'{COGNITO_CLIENT_NAME}-{instance_hash}',
             'COGNITO_GROUP_NAME': f'{COGNITO_GROUP_NAME}-{instance_hash}',
             'COGNITO_USER_POOL_DOMAIN': f'{COGNITO_USER_POOL_DOMAIN}-{instance_hash}'
            }
        ) 
        c_resource = cr.AwsCustomResource(
            self,
            f"provision-provider-{instance_hash}",
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
                # output_paths=["info.current"]
            ),
            role=provision_role
        )       
        
        CfnOutput(self, id="InfoCurrent", value=c_resource.get_response_field("Payload"), export_name="CustomResourceOutput")

        cognito_user_pool_arn = c_resource.get_response_field("Payload.CognitoUserPoolArn")
        if cognito_user_pool_arn is None or not cognito_user_pool_arn.startswith('arn:'):
            cognito_user_pool_arn = 'arn:aws:cognito-idp:us-east-1:122702569249:userpool/us-east-1_8fo02lIv0'

        
        # Create Cognitio User pool and authorizer
        user_pool = _cognito.UserPool.from_user_pool_arn(self, f"{COGNITO_NAME_PREFIX}-{instance_hash}", cognito_user_pool_arn)
        '''
        user_pool = _cognito.UserPool(self, f"{COGNITO_NAME_PREFIX}-{instance_hash}")
        user_pool.add_client("app-client", 
            auth_flows=_cognito.AuthFlow(
                user_password=True
            ),
            supported_identity_providers=[_cognito.UserPoolClientIdentityProvider.COGNITO],
        )
        '''
        auth = _apigw.CognitoUserPoolsAuthorizer(self, f"WebAuthorizer-{instance_hash}", cognito_user_pools=[user_pool])
                                                      
        # Create DynamoDB                                 
        task_table = _dynamodb.Table(self, 
            id='task-table', 
            table_name=f'{DYNAMOBD_TASK_TABLE_PREFIX}-{instance_hash}', 
            partition_key=_dynamodb.Attribute(name='id', type=_dynamodb.AttributeType.STRING),
            removal_policy=RemovalPolicy.DESTROY
        ) 
        
        # Create Lambdas

        # IAM role
        s3_trigger_role = create_lambda_s3_trigger_role(self,bucket_name, REGION, ACCOUNT_ID)
        
        # Lambda: cm-accuracy-eval-task-s3-a2i-etl
        lambda_s3_trigger = _lambda.Function(self, 
            id='s3-trigger', 
            function_name=f"cm-accuracy-eval-task-s3-a2i-etl-{instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler='cm-accuracy-eval-task-s3-a2i-etl.lambda_handler',
            code=_lambda.Code.from_asset(os.path.join("./", "lambda/task/s3-trigger")),
            timeout=Duration.seconds(30),
            role=s3_trigger_role,
            memory_size=5120,
            environment={
             'DYNAMODB_TABLE_PREFIX': DYNAMOBD_DETAIL_TABLE_PREFIX,
             'DYNAMO_TASK_TABLE': DYNAMOBD_TASK_TABLE_PREFIX,
             'DYNAMO_INDEX_NAME': DYNAMOBD_DETAIL_TABLE_LABELED_INDEX_NAME,
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
        
        # Step Function - start
        # Lambda: cm-accuracy-eval-task-moderate-image 
        moderate_image_role = create_lambda_moderate_image_role(self,bucket_name, REGION, ACCOUNT_ID)
        lambda_moderate_image = _lambda.Function(self, 
            id='moderate-image', 
            function_name=f"cm-accuracy-eval-task-moderate-image-{instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler='cm-accuracy-eval-task-moderate-image.lambda_handler',
            code=_lambda.Code.from_asset(os.path.join("./", "lambda/task/moderate-image")),
            timeout=Duration.seconds(30),
            role=moderate_image_role,
        )
        # Lambda: cm-accuracy-eval-task-update-status 
        update_status_role = create_lambda_update_status_role(self,bucket_name, REGION, ACCOUNT_ID)
        lambda_update_status = _lambda.Function(self, 
            id='update-status', 
            function_name=f"cm-accuracy-eval-task-update-status-{instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler='cm-accuracy-eval-task-update-status.lambda_handler',
            code=_lambda.Code.from_asset(os.path.join("./", "lambda/task/update-status")),
            role=update_status_role,
        )      
        # StepFunctions StateMachine
        step_function_role = create_step_function_role(self, bucket_name, REGION, ACCOUNT_ID)
        sm_json = None
        with open('./stepfunctions/cm-accuracy-eval-image-bulk.json', "r") as f:
            sm_json = str(f.read())

        if sm_json is not None:
            sm_json = sm_json.replace("##LAMBDA_MODERATE_IMAGE##", f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:cm-accuracy-eval-task-moderate-image-{instance_hash}")
            sm_json = sm_json.replace("##LAMBDA_UPDATE_STATUS##", f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:cm-accuracy-eval-task-update-status-{instance_hash}")
            
        cfn_state_machine = _aws_stepfunctions.CfnStateMachine(self, f'{STEP_FUNCTION_STATE_MACHINE_NAME_PREFIX}-{instance_hash}',
            state_machine_name=f'{STEP_FUNCTION_STATE_MACHINE_NAME_PREFIX}-{instance_hash}', 
            role_arn=step_function_role.role_arn,
            definition_string=sm_json)
        
        # Step Function - end
        
        
        api = _apigw.RestApi(self, f"{API_NAME_PREFIX}-{instance_hash}",
                                  rest_api_name=f"{API_NAME_PREFIX}-{instance_hash}")
        v1 = api.root.add_resource("v1")
        task = v1.add_resource("task")
        report = v1.add_resource("report")
        
        # create Lambda layer
        layer = _lambda.LayerVersion(self, 'aws_cli_layer',
                                     code=_lambda.Code.from_asset(os.path.join("./", "lambda/layer")),
                                     description='Base layer with AWS CLI',
                                     compatible_runtimes=[_lambda.Runtime.PYTHON_3_9],
                                     removal_policy=RemovalPolicy.DESTROY
                                     )
                                     
        # POST /v1/report/images
        # Lambda: cm-accuracy-eval-report-get-images 
        get_images_role = create_lambda_get_images_role(self,bucket_name, REGION, ACCOUNT_ID)
        self.create_api_endpoint('get-images', report, "report", "images", "POST", auth, get_images_role, "cm-accuracy-eval-report-get-images", instance_hash, 10240, 30, 
            evns={
             'DYNAMO_INDEX_NAME': DYNAMOBD_DETAIL_TABLE_LABELED_INDEX_NAME,
             'DYNAMO_TASK_TABLE': DYNAMOBD_TASK_TABLE_PREFIX,
             'EXPIRATION_IN_S': S3_PRE_SIGNED_URL_EXPIRATION_IN_S,
            })
 
        # POST /v1/report/images-unflag
        # Lambda: cm-accuracy-eval-task-get-images-unflaged 
        self.create_api_endpoint('get-images-unflag', report, "report", "images-unflag", "POST", auth, get_images_role, "cm-accuracy-eval-task-get-images-unflaged", instance_hash, 10240, 30, 
            evns={
             'DYNAMO_INDEX_NAME': DYNAMOBD_DETAIL_TABLE_LABELED_INDEX_NAME,
             'DYNAMO_TASK_TABLE': DYNAMOBD_TASK_TABLE_PREFIX,
             'EXPIRATION_IN_S': S3_PRE_SIGNED_URL_EXPIRATION_IN_S,
            })        
 
        # POST /v1/report/report
        # Lambda: cm-accuracy-eval-report-get-report 
        get_report_role = create_lambda_get_report_role(self,bucket_name, REGION, ACCOUNT_ID)
        self.create_api_endpoint('get-report', report, "report", "report", "POST", auth, get_report_role, "cm-accuracy-eval-report-get-report", instance_hash, 1280, 30, 
            evns={
             'DYNAMO_INDEX_NAME': DYNAMOBD_DETAIL_TABLE_LABELED_INDEX_NAME,
             'DYNAMO_TASK_TABLE': DYNAMOBD_TASK_TABLE_PREFIX,
            })
            
        # POST /v1/task/tasks
        # Lambda: cm-accuracy-eval-task-get-tasks
        get_tasks_role = create_lambda_get_tasks_role(self,bucket_name, REGION, ACCOUNT_ID)
        self.create_api_endpoint('get-tasks', task, "task", "tasks", "POST", auth, get_tasks_role, "cm-accuracy-eval-task-get-tasks", instance_hash, 128, 3, 
            evns={
             'DYNAMO_TASK_TABLE': DYNAMOBD_TASK_TABLE_PREFIX,
            })

        # POST /v1/task/create-task
        # Lamabd: cm-accuracy-eval-task-create-task
        create_task_role = create_lambda_create_task_role(self,bucket_name, REGION, ACCOUNT_ID)
        self.create_api_endpoint('create-task', task, "task", "create-task", "POST", auth, create_task_role, "cm-accuracy-eval-task-create-task", instance_hash, 128, 30, 
            evns={
             'DYNAMODB_RESULT_TABLE_PREFIX': DYNAMOBD_DETAIL_TABLE_PREFIX,
             'DYNAMODB_TASK_TABLE': DYNAMOBD_TASK_TABLE_PREFIX,
             'S3_BUCKET': bucket_name,
             'S3_KEY_PREFIX': S3_INPUT_PREFIX,
            })
        
        # POST /v1/task/task-with-count
        # Lamabd: cm-accuracy-eval-job-get-job-with-s3-object-count
        get_task_with_count_role = lambda_get_task_with_count_role(self, bucket_name, REGION, ACCOUNT_ID)
        self.create_api_endpoint('get-task-with-count', task, "task", "task-with-count", "POST", auth, get_task_with_count_role, "cm-accuracy-eval-job-get-job-with-s3-object-count", instance_hash, 2560, 30, 
            evns={
             'DYNAMODB_INDEX_NAME': DYNAMOBD_DETAIL_TABLE_LABELED_INDEX_NAME,
             'DYNAMODB_TASK_TABLE': DYNAMOBD_TASK_TABLE_PREFIX,
             'SUPPORTED_FILE_TYPES': '.jpg,.png,.jpeg',
            }, layer=layer)
        
        # POST /v1/task/delete-task
        # Lambda: cm-accuracy-eval-task-delete-task
        delete_task_with_count_role = create_lambda_delete_task_role(self,bucket_name, REGION, ACCOUNT_ID)
        self.create_api_endpoint('delete-task', task, "task", "delete-task", "POST", auth, delete_task_with_count_role, "cm-accuracy-eval-task-delete-task", instance_hash, 2560, 30, 
            evns={
             'DYNAMODB_TASK_TABLE': DYNAMOBD_TASK_TABLE_PREFIX,
            }, layer=layer)
        
        # POST /v1/task/start-moderation
        # Lambda: cm-accuracy-eval-task-start-moderation   
        start_moderation_role = lambda_start_moderation_role(self,bucket_name, REGION, ACCOUNT_ID)
        self.create_api_endpoint('start-moderation', task, "task", "start-moderation", "POST", auth, start_moderation_role, "cm-accuracy-eval-task-start-moderation", instance_hash, 128, 30, 
            evns={
                "DYNAMODB_TASK_TABLE":DYNAMOBD_TASK_TABLE_PREFIX,
                "DYNAMODB_RESULT_TABLE_PREFIX": DYNAMOBD_DETAIL_TABLE_PREFIX,
                "WORK_FLOW_NAME_PREFIX": A2I_WORKFLOW_NAME_PREFIX,
                "HUMAN_TASK_UI_NAME": f'arn:aws:sagemaker:{REGION}:{ACCOUNT_ID}:human-task-ui/{A2I_UI_TEMPLATE_NAME}-{instance_hash}',
                "STEP_FUNCTION_STATE_MACHINE_ARN": f"arn:aws:states:{REGION}:{ACCOUNT_ID}:stateMachine:{STEP_FUNCTION_STATE_MACHINE_NAME_PREFIX}-{instance_hash}"
            })
            
            
    def create_api_endpoint(self, id, root, path1, path2, method, auth, role, lambda_file_name, instance_hash, memory_m, timeout_s, evns, layer=None):
    # POST /v1/task/tasks
        # Lambda: cm-accuracy-eval-task-get-tasks
        layers = []
        if layer is not None:
            layers = [layer]
        lambda_funcation = _lambda.Function(self, 
            id=id, 
            function_name=f"{lambda_file_name}-{instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler=f'{lambda_file_name}.lambda_handler',
            code=_lambda.Code.from_asset(os.path.join("./", f"lambda/{path1}/{path2}")),
            timeout=Duration.seconds(timeout_s),
            role=role,
            memory_size=memory_m,
            environment=evns,
            layers=layers
        )   
        
        resource = root.add_resource(
                path2, 
                default_cors_preflight_options=_apigw.CorsOptions(
                allow_methods=['POST', 'OPTIONS'],
                allow_origins=_apigw.Cors.ALL_ORIGINS)
        )
        method = resource.add_method(
            method, 
            _apigw.LambdaIntegration(
                lambda_funcation,
                proxy=False,
                integration_responses=[
                    _apigw.IntegrationResponse(
                        status_code="200",
                        response_parameters={
                            'method.response.header.Access-Control-Allow-Origin': "'*'"
                        }
                    )
                ]
            ),
            method_responses=[
                _apigw.MethodResponse(
                    status_code="200",
                    response_parameters={
                        'method.response.header.Access-Control-Allow-Origin': True
                    }
                )
            ],
            authorizer=auth,
            authorization_type=_apigw.AuthorizationType.COGNITO
        )