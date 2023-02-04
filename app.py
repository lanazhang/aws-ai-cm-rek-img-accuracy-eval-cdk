#!/usr/bin/env python3
import aws_cdk as cdk
from aws_cdk import CfnParameter as _cfnParameter
from aws_cdk import Stack,CfnOutput
import uuid
from accuracy_eval.backend_provision import BackendProvision
from accuracy_eval.frontend_provision import FrontendProvision
from accuracy_eval.a2i_provision import A2iProvision


#env = cdk.Environment(account="TARGET_ACCOUNT_ID", region="TARGET_REGION")

class RootProvision(Stack):
    instance_hash = None
    def __init__(self, scope):
        super().__init__(scope, "cm-accuracy-eval-RootStack", description="AWS Content Moderation accuracy evaluation provision stack. Beta",
        )
    
        self.instance_hash = str(uuid.uuid4())[0:5]

        user_emails = _cfnParameter(self, "userEmails", type="String",
                                description="The emails for users to log in to the website and A2I. Split by a comma if multiple. You can always add new users after the system is deployed.")
    
    
        a2i_stack = A2iProvision(self, "A2iProvisionStack", description="AWS Content Moderation accuracy evaluation - A2I deployment statck.",
            instance_hash_code=self.instance_hash,
            user_emails=user_emails
        )
        
        backend_stack = BackendProvision(self, "BackendProvisionStack", description="AWS Content Moderation accuracy evaluation - Backend deployment statck.",
            instance_hash_code=self.instance_hash,
            cognito_user_pool_id = a2i_stack.ouput_cognito_user_pool_id
        )
    
        frontend_stack = FrontendProvision(self, "FrontProvisionStack", description="AWS Content Moderation accuracy evaluation - Frontend deployment statck.",
            instance_hash_code=self.instance_hash,
            api_gw_base_url = backend_stack.api_gw_base_url,
        )

        CfnOutput(self, "Website URL",
            value=f"https://{frontend_stack.output_url}"
        )
        
app = cdk.App()

root_stack = RootProvision(app)

app.synth()


