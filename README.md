# AWS AI Content Moderation Accuracy Evaluation PoC-in-a-box

![workflow digram](static/flow_diagram.png)

The AWS Content Moderation Accuracy Evaluation tool helps you evaluate Amazon Rekognition image moderation's false-positive rate based on your own dataset. 

To evaluate Content Moderation accuracy:

* Initiate a new task and upload your dataset to the Amazon provided S3 bucket folder.
* Start the moderation task once all the images are in place. Rekognition will then start to moderate images one by one.
* Rekognition will label some of your images as inappropriate. You then can review these images using A2I to provide human input: if the image truly has inappropriate information (true-positive) or not (false-positive).
* The tool will combine Rekognition moderation results and human inputs to produce an accuracy report.

This CDK package will help you deploy the AWS Content Moderation accuracy evaluation PoC-in-a-box with Python.

## Prerequisites

Install Node.js
https://nodejs.org/en/download/

Install Python 3.7+
https://www.python.org/downloads/

Install Pip
```sh
python -m ensurepip --upgrade
```

Install Python Virtual Environment
```sh
pip install virtualenv
```

Setup the AWS CLI
```sh
aws configure                                                                     
 ```                      

Before starting the CDK deployment, you must manually set up SageMaker GrounTruth Workforce in the AWS console.
Refer to **Step** 1 and **Step 2** in this [instruction](https://catalog.us-east-1.prod.workshops.aws/workshops/1ece9ffd-4c24-4e66-b42a-0c0e13b0f668/en-US/content-moderation/01-image-moderation/02-image-moderation-with-a2i) to set up the Workforce team. The Accuracy Evaluation tool will use to launch human review tasks using Amazon A2I.


1. Clone code
```sh
git clone https://github.com/lanazhang/aws-ai-cm-rek-img-accuracy-eval-cdk.git
```
```sh
cd aws-ai-cm-rek-img-accuracy-eval-cdk/
```

2. Install Node CDK package
```sh
npm install -g aws-cdk
```

3. Create Python Virtual Environment
```sh
python3 -m venv .venv
```

4. Activate virtual environment

  On MacOS or Linux
  ```sh
  source .venv/bin/activate                                       
  ```
  On Windows
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

8. Deploy CDK package - change the userEmails to your email address (split by comma if multiple). Ex: user1@sample.com,user2@sample.com
```
cdk deploy --all --requires-approval never --parameters userEmails=YOUR_EMAIL_ADDRESS_SPLIT_BY_COMMA
```


## Useful commands

 * `cdk ls`          list all stacks in the app
 * `cdk synth`       emits the synthesized CloudFormation template
 * `cdk deploy`      deploy this stack to your default AWS account/region
 * `cdk diff`        compare deployed stack with current state
 * `cdk docs`        open CDK documentation

![workflow digram](static/cm-accuray-eval-architecture.png)
