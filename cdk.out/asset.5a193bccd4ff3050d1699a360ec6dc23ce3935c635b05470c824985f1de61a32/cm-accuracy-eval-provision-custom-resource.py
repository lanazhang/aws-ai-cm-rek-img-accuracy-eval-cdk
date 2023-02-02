'''
Function for CloudFormation custom resource to setup A2I relates services
on_create:
1. Check if workteam exists - create Cognito user pool, domain, client if not
2. Add users to the Cognito user pool
3. Create workforce if doesn't exist
4. Create workteam if doesn't exist
5. Crate A2I human ui template

on_delete:
1. Delete A2I human ui template
Leave the workforce, workteam and cognito user pool
'''
import json
import boto3
import os, time

HUMAN_TASK_UI_NAME = os.environ["HUMAN_TASK_UI_NAME"]
WORKFORCE_NAME = os.environ["WORKFORCE_NAME"]
WORKTEAM_NAME = os.environ["WORKTEAM_NAME"]

COGNITO_USER_POOL_NAME = os.environ["COGNITO_USER_POOL_NAME"]
COGNITO_CLIENT_NAME = os.environ["COGNITO_CLIENT_NAME"]
COGNITO_GROUP_NAME = os.environ["COGNITO_GROUP_NAME"]
COGNITO_USER_POOL_DOMAIN = os.environ["COGNITO_USER_POOL_DOMAIN"]
COGNITO_USER_EMAILS = os.environ["COGNITO_USER_EMAILS"].split(',')

S3_BUCKET_NAME = os.environ["S3_BUCKET_NAME"]
S3_BUCKET_TEMP_FILE_KEY = os.environ["S3_BUCKET_TEMP_FILE_KEY"]

s3 = boto3.client('s3')
sagemaker = boto3.client('sagemaker')
lambda_client = boto3.client('lambda')
cognito = boto3.client('cognito-idp')

def on_event(event, context):
  print(event)
  request_type = event['RequestType']
  if request_type == 'Create': return on_create(event)
  if request_type == 'Update': return on_update(event)
  if request_type == 'Delete': return on_delete(event)
  raise Exception("Invalid request type: %s" % request_type)

def on_create(event):
    cognito_user_pool_id, cognito_user_pool_arn, cognito_client_id = None, None, None
    work_force_arn, work_team_arn = None, None
    user_errors = []
    # Check if workteam exists:
    ts = sagemaker.list_workteams()
    if ts is not None and "Workteams" in ts and len(ts["Workteams"]) > 0:
      cognito_user_pool_id = ts["Workteams"][0]["MemberDefinitions"][0]["CognitoMemberDefinition"]["UserPool"]
      cognito_user_pool_arn = cognito.describe_user_pool(UserPoolId=cognito_user_pool_id)["UserPool"]["Arn"]
      #cognito_client_id = ts["Workteams"][0]["MemberDefinitions"][0]["CognitoMemberDefinition"]["ClientId"]
      work_force_arn = sagemaker.list_workforces()["Workforces"][0]["WorkforceArn"]
      work_team_arn = ts["Workteams"][0]["WorkteamArn"]
      print("1. workteam exists:", cognito_user_pool_id, cognito_client_id, work_force_arn, work_team_arn)
    else:
      # Create Cognito User Pool, domain, client
      cognito_user_pool_id, cognito_user_pool_arn = create_cognito()
      print("1. workteam doesn't exist. Created Cognito user pool:", cognito_user_pool_id, cognito_user_pool_arn, cognito_client_id)
    
    # Create a new Cognito User Pool Client
    cog_client = cognito.create_user_pool_client(
      UserPoolId=cognito_user_pool_id,
      ClientName=COGNITO_CLIENT_NAME,
      GenerateSecret=False
    )
    cognito_client_id = cog_client["UserPoolClient"]["ClientId"]
    print("1.1 User pool client created:", cognito_client_id)

    # Add user
    if COGNITO_USER_EMAILS is not None and len(COGNITO_USER_EMAILS) > 0:
      for user in COGNITO_USER_EMAILS:
        try:
          cognito.admin_create_user(
              UserPoolId=cognito_user_pool_id,
              Username=user,
              UserAttributes=[
                  {
                      'Name': 'email',
                      'Value': user
                  },
              ],
              DesiredDeliveryMediums=['EMAIL']
          )
          print("2. User created:", user)
        except Exception as ex:
          print("2. Failed to add user.", ex)
          user_errors.append("Username exists:" + user)
          
    if work_force_arn is None:
      # Create Workforce if doesn't exist
      wfs = sagemaker.list_workforces()
      if wfs is None or "Workforces" not in wfs or len(wfs["Workforces"]) == 0:
        # Create workforce
        wf = sagemaker.create_workforce(
          CognitoConfig={
            "UserPool": cognito_user_pool_id,
            "ClientId": cognito_client_id,
          },
          WorkforceName=WORKFORCE_NAME
        )
        work_force_arn = wf["WorkforceArn"]
        print("3. Workforce created:", work_force_arn)
    else:
        print("3. Workforce exists:", work_force_arn)
    
    
    if work_team_arn is None:  
      # Wait until workforce stablized
      time.sleep(5)
      
      # Create workteam
      wt = sagemaker.create_workteam(
          WorkteamName=WORKTEAM_NAME,
          #WorkforceName=WORKFORCE_NAME,
          Description="Content Moderation accuracy evaluation workteam",
          MemberDefinitions=[
            {
              'CognitoMemberDefinition': {
                  'UserPool': cognito_user_pool_id,
                  'UserGroup': COGNITO_GROUP_NAME,
                  'ClientId': cognito_client_id
              }
          }]
        )
      work_team_arn = wt["WorkteamArn"]
      print("4. Workteam created:", work_force_arn)
    else:
      print("4. Workteam exists:", work_force_arn)
    
    ui_template = """
      <script src="https://assets.crowd.aws/crowd-html-elements.js"></script>
      {% capture s3_uri %}s3://{{ task.input.aiServiceRequest.image.s3Object.bucket }}/{{ task.input.aiServiceRequest.image.s3Object.name }}{% endcapture %}
      
      <crowd-form>
        <crowd-rekognition-detect-moderation-labels categories="[
            {% for label in task.input.selectedAiServiceResponse.moderationLabels %}
              {
                name: &quot;{{ label.name }}&quot;,
                parentName: &quot;{{ label.parentName }}&quot;,
              },
            {% endfor %}
          ]" src="{{ s3_uri | grant_read_access }}" header="Review the image and choose all applicable categories.">
          <short-instructions header="Instructions"><p>Review the image and choose all applicable categories.</p><p>If no categories apply, choose None.</p><p><br></p><p><strong>Nudity</strong></p><p>Visuals depicting nude male or female person or persons</p><p><br></p><p><strong>Graphic Male Nudity</strong></p><p>Visuals depicting full frontal male nudity, often close ups</p><p><br></p><p><strong>Graphic Female Nudity</strong></p><p>Visuals depicting full frontal female nudity, often close ups</p><p><br></p><p><strong>Sexual Activity</strong></p><p>Visuals depicting various types of explicit sexual activities and pornography</p><p><br></p><p><strong>Illustrated Explicit Nudity</strong></p><p>Visuals depicting animated or drawn sexual activity, nudity or pornography</p><p><br></p><p><strong>Adult Toys</strong></p><p>Visuals depicting adult toys, often in a marketing context</p><p><br></p><p><strong>Female Swimwear or Underwear</strong></p><p>Visuals depicting female person wearing only swimwear or underwear</p><p><br></p><p><strong>Male Swimwear Or Underwear</strong></p><p>Visuals depicting male person wearing only swimwear or underwear</p><p><br></p><p><strong>Barechested Male</strong></p><p>Visuals depicting topless males</p><p><br></p><p><strong>Partial Nudity</strong></p><p>Visuals depicting covered up nudity, for example using hands or pose</p><p><br></p><p><strong>Sexual Situations</strong></p><p>Visuals depicting passionate kissing and embracing of a sexual nature</p><p><br></p><p><strong>Revealing Clothes</strong></p><p>Visuals depicting revealing clothes and poses, such as deep cut dresses</p><p><br></p><p><strong>Graphic Violence or Gore</strong></p><p>Visuals depicting prominent blood or bloody injuries</p><p><br></p><p><strong>Physical Violence</strong></p><p>Visuals depicting violent physical assault, such as kicking or punching</p><p><br></p><p><strong>Weapon Violence</strong></p><p>Visuals depicting violence using weapons like firearms or blades, such as shooting</p><p><br></p><p><strong>Weapons</strong></p><p>Visuals depicting weapons like firearms and blades</p><p><br></p><p><strong>Self Injury</strong></p><p>Visuals depicting self-inflicted cutting on the body, typically in distinctive patterns using sharp objects</p><p><br></p><p><strong>Emaciated Bodies</strong></p><p>Visuals depicting extremely malnourished human bodies</p><p><br></p><p><strong>Corpses</strong></p><p>Visuals depicting human dead bodies</p><p><br></p><p><strong>Hanging</strong></p><p>Visuals depicting death by hanging</p><p><strong>Air Crash</strong> Visuals depicting air crashes <strong>Explosions and Blasts</strong> Visuals depicting blasts and explosions <strong>Middle Finger</strong> Visuals depicting a person showing the middle finger as a rude gesture <strong>Drug Products</strong> Visuals depicting drug products like joints or marijuana <strong>Drug Use</strong> Visuals depicting drug use, for example, snorting drug powders <strong>Pills</strong> Visuals depicting pills of any kind <strong>Drug Paraphernalia</strong> Visuals depicting drug paraphernalia like bongs and vaporizers <strong>Tobacco Products</strong> Visuals depicting tobacco products like cigarettes and e-cigarette devices <strong>Smoking</strong> Visuals depicting a person or persons smoking <strong>Drinking</strong> Visuals depicting a person or persons drinking alcoholic beverages <strong>Alcoholic Beverages</strong> Visuals depicting bottles or containers of alcoholic beverages <strong>Gambling</strong> Visuals depicting gambling, such as slot machines or casinos <strong>Nazi Party</strong> Visuals depicting Nazi party symbols, such as the Nazi Swastika <strong>White Supremacy</strong> Visuals depicting white supremacy symbols, such as the Confederate flag <strong>Extremist</strong> Visuals depicting flags and emblems of extremist organizations</p></short-instructions>
      
          <full-instructions header="Instructions"></full-instructions>
        </crowd-rekognition-detect-moderation-labels>
      </crowd-form>
    """
    
    # Create A2I UI tempalte
    hui = sagemaker.create_human_task_ui(
        HumanTaskUiName=HUMAN_TASK_UI_NAME,
        UiTemplate={
          'Content': ui_template
        }
      )
    ui_template_arn = hui["HumanTaskUiArn"]
    print("5. Human UI template created:", ui_template_arn)
    
    result = {
      "WorkForceArn": work_force_arn,
      "WorkTeamArn": work_team_arn,
      "UiTemplateArn": ui_template_arn,
      "CognitoUserPoolArn": cognito_user_pool_arn,
      "CognitoUserPoolId": cognito_user_pool_id,
      "CognitoClientId": cognito_client_id,
      "UserErrors": user_errors
    }
    
    # save result to s3 temp file for downstream to access
    s3.put_object(
      Body=json.dumps(result),
      Bucket=S3_BUCKET_NAME,
      Key=S3_BUCKET_TEMP_FILE_KEY
    )
    
    return result["CognitoUserPoolId"]

def on_update(event):
  return

def on_delete(event):
  # Delete UI Template
  try:
    sagemaker.delete_human_task_ui(HumanTaskUiName=HUMAN_TASK_UI_NAME)
  except Exception as ex:
    print(ex)
  
  # Get Cognitio User Pool Id from workteam
  cognito_user_pool_id = None
  ts = sagemaker.list_workteams()
  if ts is not None and "Workteams" in ts and len(ts["Workteams"]) > 0:
    cognito_user_pool_id = ts["Workteams"][0]["MemberDefinitions"][0]["CognitoMemberDefinition"]["UserPool"]
  
  # Delete Cognito client
  # Get Cognito User Pool client Id
  if cognito_user_pool_id is not None and len(cognito_user_pool_id) > 0:
    clients_response = cognito.list_user_pool_clients(
        UserPoolId=cognito_user_pool_id,
        MaxResults=20
    )
    if clients_response is not None and "UserPoolClients" in clients_response and len(clients_response["UserPoolClients"]) > 0:
      for client in clients_response["UserPoolClients"]:
        if client["ClientName"] == COGNITO_CLIENT_NAME:
          cognito.delete_user_pool_client(
              UserPoolId=cognito_user_pool_id,
              ClientId=client["ClientId"]
          )
          
  # Delete the temp file from S3 bucket
  s3.delete_object(Bucket=S3_BUCKET_NAME, Key=S3_BUCKET_TEMP_FILE_KEY)
  
  return {}

def on_complete(event):
  return

def is_complete(event):
  # Check if human UI created
  ui = sagemaker.describe_human_task_ui(HumanTaskUiName=HUMAN_TASK_UI_NAME)
  if ui is not None and ui.get("HumanTaskUiArn") is not None:
    return { 'IsComplete': True }
  else:
    return { 'IsComplete': False }
  
  
def create_cognito():
    # Create Cognito User Pool
    cog_up = cognito.create_user_pool(
      PoolName=COGNITO_USER_POOL_NAME,
      AutoVerifiedAttributes=['email'],
      VerificationMessageTemplate={
        'DefaultEmailOption': 'CONFIRM_WITH_CODE'
      },
      MfaConfiguration='OFF',
      EmailConfiguration={
        "EmailSendingAccount": "COGNITO_DEFAULT"
      },
      #Domain='PoolName',
      AdminCreateUserConfig={
          'AllowAdminCreateUserOnly': True,
          "UnusedAccountValidityDays": 7,
            "InviteMessageTemplate": {
                "EmailMessage": "\n<html xmlns:o=\"urn:schemas-microsoft-com:office:office\" xmlns:w=\"urn:schema=s-microsoft-com:office:word\" xmlns:m=\"http://schemas.microsoft.com/office/2004/12/omml\" xmlns=\"http://www.w3.org/TR/REC-html40\">\n<head>\n<meta http-equiv=\"Content-Type\" content=\"text/html; charset=utf-8\">\n<meta name=\"Generator\" content=\"Microsoft Word 15 (filtered medium)\">\n<style>\n    @font-face {\n        font-family: \"Cambria Math\";\n        panose-1: 2 4 5 3 5 4 6 3 2 4;\n    }\n\n    @font-face {\n        font-family: DengXian;\n        panose-1: 2 1 6 0 3 1 1 1 1 1;\n    }\n\n    @font-face {\n        font-family: Calibri;\n        panose-1: 2 15 5 2 2 2 4 3 2 4;\n    }\n\n    @font-face {\n        font-family: \"@DengXian\";\n        panose-1: 2 1 6 0 3 1 1 1 1 1;\n    }\n\n    @font-face {\n        font-family: \"Amazon Ember\";\n        panose-1: 2 11 6 3 2 2 4 2 2 4;\n    }\n\n    p.MsoNormal,\n    li.MsoNormal,\n    div.MsoNormal {\n        margin: 0in;\n        margin-bottom: .0001pt;\n        font-size: 12.0pt;\n        font-family: \"Calibri\", sans-serif;\n    }\n\n    h2 {\n        mso-style-priority: 9;\n        mso-style-link: \"Heading 2 Char\";\n        mso-margin-top-alt: auto;\n        margin-right: 0in;\n        mso-margin-bottom-alt: auto;\n        margin-left: 0in;\n        font-size: 18.0pt;\n        font-family: \"Calibri\", sans-serif;\n        font-weight: bold;\n    }\n\n    a,\n    span.MsoHyperlink {\n        mso-style-priority: 99;\n        color: #0563C1;\n    }\n\n    span.EmailStyle17 {\n        mso-style-type: personal-compose;\n        font-family: \"Calibri\", sans-serif;\n        color: windowtext;\n    }\n\n    span.Heading2Char {\n        mso-style-name: \"Heading 2 Char\";\n        mso-style-priority: 9;\n        mso-style-link: \"Heading 2\";\n        font-family: \"Calibri\", sans-serif;\n        font-weight: bold;\n    }\n\n    .MsoChpDefault {\n        mso-style-type: export-only;\n        font-family: \"Calibri\", sans-serif;\n    }\n\n    @page WordSection1 {\n        size: 8.5in 11.0in;\n        margin: 1.0in 1.0in 1.0in 1.0in;\n    }\n\n    div.WordSection1 {\n        page: WordSection1;\n    }\n</style>\n</head>\n<body lang=\"EN-US\" link=\"#0563C1\" vlink=\"#954F72\">\n<div class=\"WordSection1\">\n    <p style=\"font-variant-ligatures: normal;font-variant-caps: normal;orphans:2;text-align:start;widows:2;-webkit-text-stroke-width: 0px;text-decoration-style:initial;text-decoration-color:initial;word-spacing:0px\">\n    <span style=\"font-size:13.5pt;font-family:'Amazon Ember',sans-serif;color:var(--awsui-color-text-interactive-default, #545b64);\">\n        Hi,\n    </span>\n    </p>\n    <h2>\n        <span style=\"font-family:'Amazon Ember',sans-serif;color:var(--awsui-color-text-interactive-default, #545b64);\">You are invited by lanaz@amazon.com from AWS to work on a labeling project\n            <o:p></o:p>\n        </span>\n    </h2>\n    <br/>\n    <p style=\"font-variant-ligatures: normal;font-variant-caps: normal;orphans:2;text-align:start;widows:2;-webkit-text-stroke-width: 0px;text-decoration-style:initial;text-decoration-color:initial;word-spacing:0px\">\n        <span style=\"font-size:13.5pt;font-family:'Amazon Ember',sans-serif;color:var(--awsui-color-text-interactive-default, #545b64);\">Click on the link below to log into your labeling project.\n            <o:p></o:p>\n        </span>\n    </p>\n    <p style=\"font-variant-ligatures: normal;font-variant-caps: normal;orphans:2;text-align:start;widows:2;-webkit-text-stroke-width: 0px;text-decoration-style:initial;text-decoration-color:initial;word-spacing:0px;padding-bottom:30px\">\n        <span style=\"font-size:13.5pt;font-family:'Amazon Ember',sans-serif;\">\n            <a style=\"color:var(--awsui-color-text-link-default, #0073bb);\" href=\"https://6f4q7e2co4.labeling.us-west-2.sagemaker.aws\" target=\"_blank\">https://6f4q7e2co4.labeling.us-west-2.sagemaker.aws</a>\n            \n            <o:p></o:p>\n        </span>\n    </p>\n    <p style=\"font-variant-ligatures: normal;font-variant-caps: normal;orphans:2;text-align:start;widows:2;-webkit-text-stroke-width: 0px;text-decoration-style:initial;text-decoration-color:initial;word-spacing:0px\">\n    <span style=\"font-size:13.5pt;font-family:'Amazon Ember',sans-serif;color:var(--awsui-color-text-interactive-default, #545b64);\">\n        You will need the following username and temporary password provided below to login for the first time.\n    </span>\n    </p>\n    <p style=\"font-variant-ligatures: normal;font-variant-caps: normal;orphans:2;text-align:start;widows:2;-webkit-text-stroke-width: 0px;text-decoration-style:initial;text-decoration-color: initial;word-spacing:0px\">\n        <span style=\"font-size:13.5pt;font-family:'Amazon Ember',sans-serif;color:var(--awsui-color-text-interactive-default, #545b64);\">User name:\n            <b>{username}</b>\n            <o:p></o:p>\n        </span>\n    </p>\n    <p style=\"font-variant-ligatures: normal;font-variant-caps: normal;orphans:2;text-align:start;widows:2;-webkit-text-stroke-width: 0px;text-decoration-style:initial;text-decoration-color:initial;word-spacing:0px\">\n        <span style=\"font-size:13.5pt;font-family:'Amazon Ember',sans-serif;color:var(--awsui-color-text-interactive-default, #545b64);\">Temporary password:\n            <b>{####}</b>\n            <o:p></o:p>\n        </span>\n    </p>\n    <br/>\n    <p style=\"font-variant-ligatures: normal;font-variant-caps: normal;orphans:2;text-align:start;widows:2;-webkit-text-stroke-width: 0px;text-decoration-style:initial;text-decoration-color:initial;word-spacing:0px\">\n    <span style=\"font-size:13.5pt;font-family:'Amazon Ember',sans-serif;color:var(--awsui-color-text-interactive-default, #545b64);\">\n    Once you log in with your temporary password, you will be required to create a new password for your account.\n    </span>\n    </p>\n    <p style=\"font-variant-ligatures: normal;font-variant-caps: normal;orphans:2;text-align:start;widows:2;-webkit-text-stroke-width: 0px;text-decoration-style:initial;text-decoration-color:initial;word-spacing:0px\">\n    <span style=\"font-size:13.5pt;font-family:'Amazon Ember',sans-serif;color:var(--awsui-color-text-interactive-default, #545b64);\">\n    After creating a new password, you can log into your private team to access your labeling project.\n    </span>\n    </p>\n    <br/>\n    <p style=\"font-variant-ligatures: normal;font-variant-caps: normal;orphans:2;text-align:start;widows:2;-webkit-text-stroke-width: 0px;text-decoration-style:initial;text-decoration-color:initial;word-spacing:0px\">\n    <span style=\"font-size:13.5pt;font-family:'Amazon Ember',sans-serif;color:var(--awsui-color-text-interactive-default, #545b64);\">\n    \n    </span>\n    </p>\n    <p style=\"font-variant-ligatures: normal;font-variant-caps: normal;orphans:2;text-align:start;widows:2;-webkit-text-stroke-width: 0px;text-decoration-style:initial;text-decoration-color:initial;word-spacing:0px\">\n    <span style=\"font-size:13.5pt;font-family:'Amazon Ember',sans-serif;color:var(--awsui-color-text-interactive-default, #545b64);\">\n    If you have any questions, please contact us at <a style=\"color:var(--awsui-color-text-link-default, #0073bb);\" href=\"mailto:lanaz@amazon.com\" target=\"_top\">lanaz@amazon.com</a>.\n    </span>\n    </p>\n    <p class=\"MsoNormal\">\n        <span style=\"font-size:11.0pt\">\n            <o:p>&nbsp;</o:p>\n        </span>\n    </p>\n</div>\n</body>\n</html>\n",
                "EmailSubject": f"You are invited by {COGNITO_USER_EMAILS[0]} to work on a content moderation accuracy evaluation project"
        }},
    )
    cognito_user_pool_id = cog_up["UserPool"]["Id"]
    cognito_user_pool_arn = cog_up["UserPool"]["Arn"]
    print("!!! User pool created:", cognito_user_pool_id, cognito_user_pool_arn)
    
    # Create Cognito User Group
    cog_grp = cognito.create_group(
        GroupName=COGNITO_GROUP_NAME,
        UserPoolId=cognito_user_pool_id,
        Description='Admin group',
        #RoleArn='string',
        #Precedence=123
    )
    print("!!! User group created:", cog_grp)


    # Create Cognito User Pool Domain
    cog_d = cognito.create_user_pool_domain(
        Domain=COGNITO_USER_POOL_DOMAIN,
        UserPoolId=cognito_user_pool_id,
    )

    return cognito_user_pool_id, cognito_user_pool_arn