from __future__ import annotations

from pathlib import Path
import re
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


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[._]+", "-", value)
    value = re.sub(r"[^a-z0-9-]+", "-", value)
    value = re.sub(r"^-+|-+$", "", value)
    value = re.sub(r"-{2,}", "-", value)
    return value


app_name = read_app_name_from_pyproject()
app_slug = slugify(app_name)

cfg = Config()
gcp_cfg = Config("gcp")

project_id = gcp_cfg.require("project")
region = gcp_cfg.require("region")

service_name = f"{app_slug}-staging"
runtime_sa_id = f"{app_slug}-staging-runtime"
runtime_sa_email = f"{runtime_sa_id}@{project_id}.iam.gserviceaccount.com"

image_by_digest = cfg.require("imageByDigest")
usda_secret_name = cfg.get("usdaSecretName") or "USDA_API_KEY_STAGING"
allow_unauthenticated = cfg.get_bool("allowUnauthenticated") or False
staging_invoker_member = cfg.get("stagingInvokerMember")

provider = gcp.Provider(
    "gcp-provider",
    project=project_id,
    region=region,
)

service_template = gcp.cloudrunv2.ServiceTemplateArgs(
    service_account=runtime_sa_email,
    containers=[
        gcp.cloudrunv2.ServiceTemplateContainerArgs(
            image=image_by_digest,
            ports=gcp.cloudrunv2.ServiceTemplateContainerPortsArgs(
                container_port=8080,
            ),
            envs=[
                gcp.cloudrunv2.ServiceTemplateContainerEnvArgs(
                    name="APP_ENV",
                    value="staging",
                ),
                gcp.cloudrunv2.ServiceTemplateContainerEnvArgs(
                    name="USDA_API_KEY",
                    value_source=gcp.cloudrunv2.ServiceTemplateContainerEnvValueSourceArgs(
                        secret_key_ref=gcp.cloudrunv2.ServiceTemplateContainerEnvValueSourceSecretKeyRefArgs(
                            secret=usda_secret_name,
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
    opts=ResourceOptions(provider=provider),
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
pulumi.export("runtimeServiceAccountEmail", runtime_sa_email)
pulumi.export("secretName", usda_secret_name)
pulumi.export("deployedImage", image_by_digest)
