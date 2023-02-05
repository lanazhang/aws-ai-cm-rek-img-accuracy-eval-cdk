# AWS AI Content Moderation Accuracy Evaluation PoC-in-a-box (beta)
This tool will help you evaluate Amazon Rekognition image moderation's false-positive rate based on your own image dataset. Follow the instructions to deploy the system to your AWS account as a CDK package so that you can run self-serve evaluations without privacy concerns.


![workflow digram](static/flow_diagram.png)

To evaluate Content Moderation accuracy:

* Initiate a new task and upload your dataset to the Amazon provided S3 bucket folder.
* Start the moderation task once all the images are in place. Rekognition will then start to moderate images one by one.
* Rekognition will label some of your images as inappropriate. You then can review these images using A2I to provide human input: if the image truly has inappropriate information (true-positive) or not (false-positive).
* The tool will combine Rekognition moderation results and human inputs to produce an accuracy report.


## Prerequisites
You will need admin access to the AWS account to deploy the CDK package and the underline AWS services.

### Supported AWS regions
The Accuracy Evaluation tool requires AWS services such as Amazon SageMaker GrounTruth/A2I and Amazon Rekognition, which are available in certain regions. Please choose one of the below AWS regions to deploy the CDK package.

| |Regions ||||
| ---------- | ---------- | ---------- | ---------- | ---------- |
| US | us-east-1 | us-east-2 | us-west-2 ||
| Europe | eu-central-1 | eu-west-2 | eu-west-1 ||
| Asia | ap-south-1 | ap-southeast-2 | ap-northeast-2 | ap-northeast-1 |


### Install environment dependencies and set up authentication
> :warning: You can skip this section and proceed to the **Deploy the CDK package** section if using ClouShell in the same AWS account or the other AWS services support bash command (ex. Cloud9)

- [ ] Install Node.js
https://nodejs.org/en/download/

- [ ] Install Python 3.7+
https://www.python.org/downloads/

- [ ] Install Pip
```sh
python -m ensurepip --upgrade
```

- [ ] Install Python Virtual Environment
```sh
pip install virtualenv
```

- [ ] Setup the AWS CLI authentication
```sh
aws configure                                                                     
 ```                      

### Deploy the CDK package
> :warning: **Set up a SageMaker GroundTruth private team via the AWS console**: 
Before starting the CDK deployment, you must manually set up SageMaker GrounTruth private team in the AWS console if the account/region doesn't have it provisioned.
Refer to [**Step 1**](https://catalog.us-east-1.prod.workshops.aws/workshops/1ece9ffd-4c24-4e66-b42a-0c0e13b0f668/en-US/content-moderation/01-image-moderation/02-image-moderation-with-a2i#step-1:-create-a-private-team-in-aws-console-(you-can-skip-this-step-if-you-already-have-a-private-work-team-in-the-region)) 
and [**Step 2**](https://catalog.us-east-1.prod.workshops.aws/workshops/1ece9ffd-4c24-4e66-b42a-0c0e13b0f668/en-US/content-moderation/01-image-moderation/02-image-moderation-with-a2i#step-2:-activate-a2i-user-account) 
in this [instruction](https://catalog.us-east-1.prod.workshops.aws/workshops/1ece9ffd-4c24-4e66-b42a-0c0e13b0f668/en-US/content-moderation/01-image-moderation/02-image-moderation-with-a2i) 
to set up the private team. This step will create the user(s) to access the Accuracy Evaluation web portal and A2I for human review.

Once set up the SageMaker GrounTruth private team, follow the below steps to deploy the CDK package.

1. Clone code
```sh
git clone https://github.com/lanazhang/aws-ai-cm-rek-img-accuracy-eval-cdk.git
```
```sh
cd aws-ai-cm-rek-img-accuracy-eval-cdk/
```

2. Install Node CDK package
```sh
sudo npm install -g aws-cdk
```

3. Create Python Virtual Environment
```sh
python3 -m venv .venv
```

4. Activate virtual environment

  - On MacOS or Linux
  ```sh
  source .venv/bin/activate
  ```
  - On Windows
  ```sh
    .venv\Scripts\activate.bat                                        
```

5. Once the virtualenv is activated, you can install the required dependencies.

```
pip install -r requirements.txt
```

6. Set up environment varaibles - change the values to your target AWS account Id and region.
```
export CDK_DEFAULT_ACCOUNT=YOUR_ACCOUNT_ID
export CDK_DEFAULT_REGION=YOUR_TARGET_REGION
```

7. Bootstrap CDK
```
cdk bootstrap aws://${CDK_DEFAULT_ACCOUNT}/${CDK_DEFAULT_REGION}
```

8. Deploy CDK package
```
cdk deploy --all --requires-approval never
```

You can navigate to the CloudFormation service in the AWS console to monitor the deployment process. The CDK package will launch one CloudFormation stack with three nested stacks to deploy sub-systems. 

Once the deployment completes, you can find the website URL from the CloudFormation stack output. Use the username/password set up earlier in the GroundTruth private team stage to log in to the website.
![CloudFormation stack output](static/cloudformation-stack-output.png)


## Add new users
You can log in to the Accuracy Evaluation web portal using the user created in the step: **Set up a SageMaker GroundTruth private team using the AWS console**. The same username/password will work for both the web portal and the A2I human review console.

To add additional users to the system using the AWS console:
- Navigate to SageMaker
- Select GroundTruth -> Labeling workforces on the left menu
- Choose the "Private" tab
- Click on "Invite new workers" at the bottom "Workers" section and add new users by specifying email addresses. The system will send an invite Email(s) to the users automatically.
- Add the new user(s) to the work team:
  - Click on the team name in the "Private team" section
  - Click on the "Workers" tab to see all the workers in the pool
  - Select the worker and click on the "Add works to team" button

## The Accuracy Evaluation system architecture diagram:
![workflow digram](static/cm-accuray-eval-architecture.png)
