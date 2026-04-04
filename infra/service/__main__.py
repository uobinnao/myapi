from __future__ import annotations

from pathlib import Path
import tomllib

import pulumi
import pulumi_gcp as gcp
from pulumi import Config, ResourceOptions


def read_app_name_from_pyproject() -> str:
    repo_root = Path(__file__).resolve().parents[2]
    pyproject_path = repo_root / "pyproject.toml"

    with pyproject_path.open("rb") as f:
        data = tomllib.load(f)

    return data["project"]["name"]


app_name = read_app_name_from_pyproject()

cfg = Config()
gcp_cfg = Config("gcp")

project_id = gcp_cfg.require("project")
region = gcp_cfg.require("region")

service_name = f"{app_name}-staging" or cfg.get("serviceName")
artifact_repo_id = app_name or cfg.get("artifactRegistryRepoId")
image_by_digest = cfg.require(
    "imageByDigest"
)  # LOCATION-docker.pkg.dev/.../{repo}@sha256:...
runtime_sa_id = f"{app_name}-staging-runtime" or cfg.get("runtimeServiceAccountId")
deployer_principal = cfg.require(
    "deployerPrincipal"
)  # serviceAccount:github-myapi-staging@...
usda_secret_name = cfg.get("usdaSecretName") or "USDA_API_KEY_STAGING"
app_env = "staging" or cfg.get("appEnv")
allow_unauthenticated = cfg.get_bool("allowUnauthenticated") or False
staging_invoker_member = cfg.get(
    "stagingInvokerMember"
)  # optional: user:..., group:..., serviceAccount:...

provider = gcp.Provider(
    "gcp-provider",
    project=project_id,
    region=region,
)

required_services = [
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "iam.googleapis.com",
]

service_apis: list[pulumi.Resource] = []
for svc in required_services:
    service_apis.append(
        gcp.projects.Service(
            svc.replace(".", "-"),
            project=project_id,
            service=svc,
            disable_on_destroy=False,
            opts=ResourceOptions(provider=provider),
        )
    )

base_opts = ResourceOptions(provider=provider, depends_on=service_apis)

runtime_sa = gcp.serviceaccount.Account(
    "runtime-sa",
    project=project_id,
    account_id=runtime_sa_id,
    display_name=f"{app_name} staging runtime",
    opts=base_opts,
)

usda_secret = gcp.secretmanager.Secret(
    "usda-secret",
    project=project_id,
    secret_id=usda_secret_name,
    replication={"auto": {}},
    opts=base_opts,
)

runtime_secret_access = gcp.secretmanager.SecretIamMember(
    "runtime-secret-access",
    project=project_id,
    secret_id=usda_secret.secret_id,
    role="roles/secretmanager.secretAccessor",
    member=runtime_sa.email.apply(lambda email: f"serviceAccount:{email}"),
    opts=ResourceOptions(provider=provider),
)

deployer_run_developer = gcp.projects.IAMMember(
    "deployer-run-developer",
    project=project_id,
    role="roles/run.developer",
    member=deployer_principal,
    opts=ResourceOptions(provider=provider),
)

deployer_runtime_sa_user = gcp.serviceaccount.IAMMember(
    "deployer-runtime-sa-user",
    service_account_id=runtime_sa.name,
    role="roles/iam.serviceAccountUser",
    member=deployer_principal,
    opts=ResourceOptions(provider=provider),
)

deployer_repo_reader = gcp.artifactregistry.RepositoryIamMember(
    "deployer-repo-reader",
    project=project_id,
    location=region,
    repository=artifact_repo_id,
    role="roles/artifactregistry.reader",
    member=deployer_principal,
    opts=ResourceOptions(provider=provider),
)

service_template = gcp.cloudrunv2.ServiceTemplateArgs(
    service_account=runtime_sa.email,
    containers=[
        gcp.cloudrunv2.ServiceTemplateContainerArgs(
            image=image_by_digest,
            ports=gcp.cloudrunv2.ServiceTemplateContainerPortsArgs(
                container_port=8080,
            ),
            envs=[
                gcp.cloudrunv2.ServiceTemplateContainerEnvArgs(
                    name="APP_ENV",
                    value=app_env,
                ),
                gcp.cloudrunv2.ServiceTemplateContainerEnvArgs(
                    name="USDA_API_KEY",
                    value_source=gcp.cloudrunv2.ServiceTemplateContainerEnvValueSourceArgs(
                        secret_key_ref=gcp.cloudrunv2.ServiceTemplateContainerEnvValueSourceSecretKeyRefArgs(
                            secret=usda_secret.secret_id,
                            version="latest",
                        )
                    ),
                ),
            ],
            resources=gcp.cloudrunv2.ServiceTemplateContainerResourcesArgs(
                limits={
                    "cpu": "1",
                    "memory": "512Mi",
                },
            ),
        )
    ],
    scaling=gcp.cloudrunv2.ServiceTemplateScalingArgs(
        min_instance_count=0,
        max_instance_count=1,
    ),
)

service = gcp.cloudrunv2.Service(
    "service",
    project=project_id,
    location=region,
    name=service_name,
    deletion_protection=False,
    ingress="INGRESS_TRAFFIC_ALL",
    invoker_iam_disabled=allow_unauthenticated,
    template=service_template,
    opts=ResourceOptions(
        provider=provider,
        depends_on=[
            runtime_secret_access,
            deployer_run_developer,
            deployer_runtime_sa_user,
            deployer_repo_reader,
        ],
    ),
)

if staging_invoker_member and not allow_unauthenticated:
    gcp.cloudrunv2.ServiceIamMember(
        "staging-invoker",
        project=project_id,
        location=region,
        name=service.name,
        role="roles/run.invoker",
        member=staging_invoker_member,
        opts=ResourceOptions(provider=provider),
    )

pulumi.export("appName", app_name)
pulumi.export("serviceName", service.name)
pulumi.export("serviceUrl", service.uri)
pulumi.export("runtimeServiceAccountEmail", runtime_sa.email)
pulumi.export("secretName", usda_secret.secret_id)
pulumi.export("deployedImage", image_by_digest)
