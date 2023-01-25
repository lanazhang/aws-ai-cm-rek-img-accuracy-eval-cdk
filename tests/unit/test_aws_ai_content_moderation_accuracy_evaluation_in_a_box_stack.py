import aws_cdk as core
import aws_cdk.assertions as assertions

from aws_ai_content_moderation_accuracy_evaluation_in_a_box.aws_ai_content_moderation_accuracy_evaluation_in_a_box_stack import AwsAiContentModerationAccuracyEvaluationInABoxStack

# example tests. To run these tests, uncomment this file along with the example
# resource in aws_ai_content_moderation_accuracy_evaluation_in_a_box/aws_ai_content_moderation_accuracy_evaluation_in_a_box_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = AwsAiContentModerationAccuracyEvaluationInABoxStack(app, "aws-ai-content-moderation-accuracy-evaluation-in-a-box")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
