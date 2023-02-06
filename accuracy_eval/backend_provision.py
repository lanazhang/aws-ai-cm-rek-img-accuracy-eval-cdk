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
    Fn
)
from aws_cdk.aws_logs import RetentionDays
from aws_cdk.aws_apigateway import IdentitySource
from constructs import Construct
import os
import uuid
import json
from accuracy_eval.constant import *

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
from iam_role.lambda_export_csv_role import create_role as create_lambda_export_csv_role


class BackendProvision(NestedStack):
    account_id = None
    region = None
    instance_hash = None
    api_gw_base_url = None
    
    def __init__(self, scope: Construct, construct_id: str, instance_hash_code, cognito_user_pool_id, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.account_id=os.environ.get("CDK_DEPLOY_ACCOUNT", os.environ["CDK_DEFAULT_ACCOUNT"])
        self.region=os.environ.get("CDK_DEPLOY_REGION", os.environ["CDK_DEFAULT_REGION"])
        
        self.instance_hash = instance_hash_code #str(uuid.uuid4())[0:5]
        bucket_name = f'{S3_BUCKET_NAME_PREFIX}-{self.account_id}-{self.region}-{self.instance_hash}'
        
        work_team_arn, a2i_ui_template_arn = None, None
        
        # Create Cognitio User pool and authorizer
        pool_arn = f"arn:aws:cognito-idp:{self.region}:{self.account_id}:userpool/{cognito_user_pool_id}"
        user_pool = _cognito.UserPool.from_user_pool_arn(self, "cm-accuracy-eval-cognito", pool_arn)
        '''
        user_pool = _cognito.UserPool(self, f"{COGNITO_NAME_PREFIX}-{self.instance_hash}")
        user_pool.add_client("app-client", 
            auth_flows=_cognito.AuthFlow(
                user_password=True
            ),
            supported_identity_providers=[_cognito.UserPoolClientIdentityProvider.COGNITO],
        )
        '''
        auth = _apigw.CognitoUserPoolsAuthorizer(self, f"WebAuth-{self.instance_hash}", 
            cognito_user_pools=[user_pool],
            identity_source=IdentitySource.header('Authorization')
        )
                                                      
        # Create DynamoDB                                 
        task_table = _dynamodb.Table(self, 
            id='task-table', 
            table_name=f'{DYNAMOBD_TASK_TABLE_PREFIX}-{self.instance_hash}', 
            partition_key=_dynamodb.Attribute(name='id', type=_dynamodb.AttributeType.STRING),
            removal_policy=RemovalPolicy.DESTROY
        ) 
        
        # Step Function - start
        # Lambda: cm-accuracy-eval-task-moderate-image 
        lambda_moderate_image = _lambda.Function(self, 
            id='moderate-image', 
            function_name=f"cm-accuracy-eval-task-moderate-image-{self.instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler='cm-accuracy-eval-task-moderate-image.lambda_handler',
            code=_lambda.Code.from_asset(os.path.join("./", "lambda/task/moderate-image")),
            timeout=Duration.seconds(30),
            role=create_lambda_moderate_image_role(self,bucket_name, self.region, self.account_id),
        )
        # Lambda: cm-accuracy-eval-task-update-status 
        lambda_update_status = _lambda.Function(self, 
            id='update-status', 
            function_name=f"cm-accuracy-eval-task-update-status-{self.instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler='cm-accuracy-eval-task-update-status.lambda_handler',
            code=_lambda.Code.from_asset(os.path.join("./", "lambda/task/update-status")),
            role=create_lambda_update_status_role(self,bucket_name, self.region, self.account_id),
            environment={
             'DYNAMODB_TASK_TABLE': DYNAMOBD_TASK_TABLE_PREFIX + f"-{self.instance_hash}",
            }
        )
        # StepFunctions StateMachine
        sm_json = None
        with open('./stepfunctions/cm-accuracy-eval-image-bulk.json', "r") as f:
            sm_json = str(f.read())

        if sm_json is not None:
            sm_json = sm_json.replace("##LAMBDA_MODERATE_IMAGE##", f"arn:aws:lambda:{self.region}:{self.account_id}:function:cm-accuracy-eval-task-moderate-image-{self.instance_hash}")
            sm_json = sm_json.replace("##LAMBDA_UPDATE_STATUS##", f"arn:aws:lambda:{self.region}:{self.account_id}:function:cm-accuracy-eval-task-update-status-{self.instance_hash}")
            
        cfn_state_machine = _aws_stepfunctions.CfnStateMachine(self, f'{STEP_FUNCTION_STATE_MACHINE_NAME_PREFIX}-{self.instance_hash}',
            state_machine_name=f'{STEP_FUNCTION_STATE_MACHINE_NAME_PREFIX}-{self.instance_hash}', 
            role_arn=create_step_function_role(self, bucket_name, self.region, self.account_id).role_arn,
            definition_string=sm_json)
        
        # Step Function - end
        
        
        api = _apigw.RestApi(self, f"{API_NAME_PREFIX}-{self.instance_hash}",
                                  rest_api_name=f"{API_NAME_PREFIX}-{self.instance_hash}")
        v1 = api.root.add_resource("v1")
        task = v1.add_resource("task")
        report = v1.add_resource("report")
        
        self.api_gw_base_url = api.url
        CfnOutput(self, id="ApiGwBaseUrl", value=api.url, export_name="ApiGwBaseUrl")
        
        # create Lambda layer
        layer = _lambda.LayerVersion(self, 'aws_cli_layer',
                                     code=_lambda.Code.from_asset(os.path.join("./", "lambda/layer")),
                                     description='Base layer with AWS CLI',
                                     compatible_runtimes=[_lambda.Runtime.PYTHON_3_9],
                                     removal_policy=RemovalPolicy.DESTROY
                                     )
                                     
        # POST /v1/report/images
        # Lambda: cm-accuracy-eval-report-get-images 
        get_images_role = create_lambda_get_images_role(self,bucket_name, self.region, self.account_id)
        self.create_api_endpoint('get-images', report, "report", "images", "POST", auth, get_images_role, "cm-accuracy-eval-report-get-images", self.instance_hash, 10240, 30, 
            evns={
             'DYNAMODB_INDEX_NAME': DYNAMOBD_DETAIL_TABLE_LABELED_INDEX_NAME,
             'DYNAMODB_TASK_TABLE': DYNAMOBD_TASK_TABLE_PREFIX + f"-{self.instance_hash}",
             'EXPIRATION_IN_S': S3_PRE_SIGNED_URL_EXPIRATION_IN_S,
            })
 
        # POST /v1/report/images-unflag
        # Lambda: cm-accuracy-eval-task-get-images-unflaged 
        self.create_api_endpoint('get-images-unflag', report, "report", "images-unflag", "POST", auth, get_images_role, "cm-accuracy-eval-task-get-images-unflaged", self.instance_hash, 10240, 30, 
            evns={
             'DYNAMODB_INDEX_NAME': DYNAMOBD_DETAIL_TABLE_LABELED_INDEX_NAME,
             'DYNAMODB_TASK_TABLE': DYNAMOBD_TASK_TABLE_PREFIX + f"-{self.instance_hash}",
             'EXPIRATION_IN_S': S3_PRE_SIGNED_URL_EXPIRATION_IN_S,
            })        
 
        # POST /v1/report/export
        # Lambda: cm-accuracy-eval-report-export-flagged
        export_csv_role = create_lambda_export_csv_role(self,bucket_name, self.region, self.account_id)
        self.create_api_endpoint('export-csv', report, "report", "export", "POST", auth, export_csv_role, "cm-accuracy-eval-report-export-flagged", self.instance_hash, 10240, 30, 
            evns={
             'DYNAMODB_INDEX_NAME': DYNAMOBD_DETAIL_TABLE_LABELED_INDEX_NAME,
             'DYNAMODB_TASK_TABLE': DYNAMOBD_TASK_TABLE_PREFIX + f"-{self.instance_hash}",                
             'S3_BUCKET_NAME': bucket_name,
             'S3_REPORT_PREFIX': S3_REPORT_PREFIX,
             'EXPIRATION_IN_S': S3_PRE_SIGNED_URL_EXPIRATION_IN_S,
            })      
            
        # POST /v1/report/report
        # Lambda: cm-accuracy-eval-report-get-report 
        get_report_role = create_lambda_get_report_role(self,bucket_name, self.region, self.account_id)
        self.create_api_endpoint('get-report', report, "report", "report", "POST", auth, get_report_role, "cm-accuracy-eval-report-get-report", self.instance_hash, 1280, 30, 
            evns={
             'DYNAMODB_INDEX_NAME': DYNAMOBD_DETAIL_TABLE_LABELED_INDEX_NAME,
             'DYNAMODB_TASK_TABLE': DYNAMOBD_TASK_TABLE_PREFIX + f"-{self.instance_hash}",
            })
            
        # POST /v1/task/tasks
        # Lambda: cm-accuracy-eval-task-get-tasks
        get_tasks_role = create_lambda_get_tasks_role(self,bucket_name, self.region, self.account_id)
        self.create_api_endpoint('get-tasks', task, "task", "tasks", "GET", auth, get_tasks_role, "cm-accuracy-eval-task-get-tasks", self.instance_hash, 128, 3, 
            evns={
             'DYNAMODB_TASK_TABLE': DYNAMOBD_TASK_TABLE_PREFIX + f"-{self.instance_hash}",
            })

        # POST /v1/task/create-task
        # Lamabd: cm-accuracy-eval-task-create-task
        create_task_role = create_lambda_create_task_role(self,bucket_name, self.region, self.account_id)
        self.create_api_endpoint('create-task', task, "task", "create-task", "POST", auth, create_task_role, "cm-accuracy-eval-task-create-task", self.instance_hash, 128, 30, 
            evns={
             'DYNAMODB_INDEX_NAME': DYNAMOBD_DETAIL_TABLE_LABELED_INDEX_NAME,
             'DYNAMODB_TASK_TABLE': DYNAMOBD_TASK_TABLE_PREFIX + f"-{self.instance_hash}",
             "DYNAMODB_RESULT_TABLE_PREFIX": f'{DYNAMOBD_DETAIL_TABLE_PREFIX}-{self.instance_hash}',
             'S3_BUCKET': bucket_name,
             'S3_KEY_PREFIX': S3_INPUT_PREFIX,
             'EXPIRATION_IN_S': S3_PRE_SIGNED_URL_EXPIRATION_IN_S
            })
        
        # POST /v1/task/task-with-count
        # Lamabd: cm-accuracy-eval-task-get-task-with-s3-object-count
        get_task_with_count_role = lambda_get_task_with_count_role(self, bucket_name, self.region, self.account_id)
        self.create_api_endpoint('get-task-with-count', task, "task", "task-with-count", "POST", auth, get_task_with_count_role, "cm-accuracy-eval-task-get-task-with-s3-object-count", self.instance_hash, 2560, 30, 
            evns={
             'DYNAMODB_INDEX_NAME': DYNAMOBD_DETAIL_TABLE_LABELED_INDEX_NAME,
             'DYNAMODB_TASK_TABLE': DYNAMOBD_TASK_TABLE_PREFIX + f"-{self.instance_hash}",
             'SUPPORTED_FILE_TYPES': '.jpg,.png,.jpeg',
            }, layer=layer)
        
        # POST /v1/task/delete-task
        # Lambda: cm-accuracy-eval-task-delete-task
        delete_task_with_count_role = create_lambda_delete_task_role(self,bucket_name, self.region, self.account_id)
        self.create_api_endpoint('delete-task', task, "task", "delete-task", "POST", auth, delete_task_with_count_role, "cm-accuracy-eval-task-delete-task", self.instance_hash, 2560, 30, 
            evns={
             'DYNAMODB_TASK_TABLE': DYNAMOBD_TASK_TABLE_PREFIX + f"-{self.instance_hash}",
            }, layer=layer)
        
        # POST /v1/task/start-moderation
        # Lambda: cm-accuracy-eval-task-start-moderation   
        start_moderation_role = lambda_start_moderation_role(self,bucket_name, self.region, self.account_id)
        self.create_api_endpoint('start-moderation', task, "task", "start-moderation", "POST", auth, start_moderation_role, "cm-accuracy-eval-task-start-moderation", self.instance_hash, 128, 30, 
            evns={
                "DYNAMODB_TASK_TABLE":DYNAMOBD_TASK_TABLE_PREFIX + f"-{self.instance_hash}",
                "DYNAMODB_RESULT_TABLE_PREFIX": f'{DYNAMOBD_DETAIL_TABLE_PREFIX}-{self.instance_hash}',
                "WORK_FLOW_NAME_PREFIX": A2I_WORKFLOW_NAME_PREFIX + f"-{self.instance_hash}",
                "HUMAN_TASK_UI_NAME": f'arn:aws:sagemaker:{self.region}:{self.account_id}:human-task-ui/{A2I_UI_TEMPLATE_NAME}-{self.instance_hash}',
                "STEP_FUNCTION_STATE_MACHINE_ARN": f"arn:aws:states:{self.region}:{self.account_id}:stateMachine:{STEP_FUNCTION_STATE_MACHINE_NAME_PREFIX}-{self.instance_hash}"
            })
            
            
    def create_api_endpoint(self, id, root, path1, path2, method, auth, role, lambda_file_name, instance_hash, memory_m, timeout_s, evns, layer=None):
    # POST /v1/task/tasks
        # Lambda: cm-accuracy-eval-task-get-tasks
        layers = []
        if layer is not None:
            layers = [layer]
        lambda_funcation = _lambda.Function(self, 
            id=id, 
            function_name=f"{lambda_file_name}-{self.instance_hash}", 
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