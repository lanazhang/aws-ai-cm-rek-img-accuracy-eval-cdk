DYNAMOBD_TASK_TABLE_PREFIX = "cm-accuracy-eval-task"
DYNAMOBD_DETAIL_TABLE_PREFIX = "cm-accuracy-result"
DYNAMOBD_DETAIL_TABLE_LABELED_INDEX_NAME = "issue_flag-index"

COGNITO_NAME_PREFIX = 'cm-accuracy-eval-user-pool'
COGNITO_USER_POOL_NAME = 'cm-accuracy-eval-user-pool'
COGNITO_CLIENT_NAME = 'web-client'
COGNITO_GROUP_NAME = 'admin'
COGNITO_USER_POOL_DOMAIN = 'accuracy-eval'

S3_BUCKET_NAME_PREFIX = "cm-accuracy-eval"
S3_A2I_PREFIX = "a2i/"
S3_BUCKET_TEMP_FILE_KEY = ".cfn_temp/a2i.json"
S3_INPUT_PREFIX = "input/"
S3_REPORT_PREFIX = "report/"
S3_PRE_SIGNED_URL_EXPIRATION_IN_S = "300"
S3_WEB_BUCKET_NAME_PREFIX = "cm-accuracy-eval-website-console"

A2I_WORKFLOW_NAME_PREFIX = "cm-accuracy-result"
A2I_UI_TEMPLATE_NAME = "cm-accuracy-eval-image-review-ui-template"
A2I_WORK_FORCE_NAME = 'cm-accuracy-eval-workforce'
A2I_WORK_TEAM_NAME = 'cm-accuracy-eval-workteam'

API_NAME_PREFIX = "cm-accuracy-eval-srv"
STEP_FUNCTION_STATE_MACHINE_NAME_PREFIX = "cm-accuracy-eval-image-sm"