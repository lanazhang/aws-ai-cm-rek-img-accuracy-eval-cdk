#!/usr/bin/env python3
import os
import uuid
import json
import aws_cdk as cdk

from accuracy_eval.backend_provision import BackendProvision
from accuracy_eval.a2i_provision import A2iProvision
from accuracy_eval.frontend_provision import FrontendProvision

instance_hash = str(uuid.uuid4())[0:5]

app = cdk.App()

a2i_stack = A2iProvision(app, "A2iProvisionStack",
    env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION')),
    instance_hash_code=instance_hash
)

backend_stack = BackendProvision(app, "BackendProvisionStack",
    env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION')),
    instance_hash_code=instance_hash,
    cognito_user_pool_id = a2i_stack.ouput_cognito_user_pool_id
)

frontend_stack = FrontendProvision(app, "FrontProvisionStack",
    env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION')),
    instance_hash_code=instance_hash,
    api_gw_base_url = backend_stack.api_gw_base_url,
)

app.synth()
