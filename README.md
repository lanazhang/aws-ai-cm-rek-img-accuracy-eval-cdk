# AWS AI Content Moderation Accuracy Evaluation CDK Python package

![workflow digram](static/flow_diagram.png)

The AWS Content Moderation Accuracy Evaluation tool helps you evaluate Amazon Rekognition image moderation's false-positive rate based on your own dataset. For best results, we recommend you use a dataset with 5,000+ images, as fewer images may lead to a skewed result and a biased conclusion.

To evaluate Content Moderation accuracy:

* Initiate a new task and upload your dataset to the Amazon provided S3 bucket folder.
* Start the moderation task once all the images are in place. Rekognition will then start to moderate images one by one.
* Rekognition will label some of your images as inappropriate. You then can review these images using A2I to provide human input: if the image truly has inappropriate information (true-positive) or not (false-positive).
* The tool will combine Rekognition moderation results and human inputs to produce an accuracy report.

This CDK package will help you deploy the AWS Content Moderation accuracy evaluation PoC-in-a-box with Python.

## Prerequisites

```sh
# Setup the AWS CLI
aws configure                                                                     
 ```                                                                                  

1. Locally install AWS CDK as the [official documentation](https://docs.aws.amazon.com/cdk/latest/guide/getting_started.html) describes.
2. [Bootstrap CDK for AWS Account](https://github.com/aws/aws-cdk/blob/master/design/cdk-bootstrap.md) 
3. Create a Python virtual environment
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

Once the virtualenv is activated, you can install the required dependencies.

```
$ pip install -r requirements.txt
```

Deploy the system to your AWS account.
```
$ cdk deploy
```

To add additional dependencies, for example other CDK libraries, just add
them to your `setup.py` file and rerun the `pip install -r requirements.txt`
command.

## Useful commands

 * `cdk ls`          list all stacks in the app
 * `cdk synth`       emits the synthesized CloudFormation template
 * `cdk deploy`      deploy this stack to your default AWS account/region
 * `cdk diff`        compare deployed stack with current state
 * `cdk docs`        open CDK documentation

Enjoy!

System architecture:
![workflow digram](static/cm-accuray-eval-architecture.png)
