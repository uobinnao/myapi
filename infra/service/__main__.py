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


def cfg_bool(cfg: Config, key: str, default: bool) -> bool:
    value = cfg.get_bool(key)
    return default if value is None else value


def cfg_int(cfg: Config, key: str, default: int) -> int:
    value = cfg.get_int(key)
    return default if value is None else value


def is_preview_stack(stack_name: str) -> bool:
    return stack_name == "preview" or stack_name.startswith("preview-")


def default_service_name_for_stack(app_slug: str, stack_name: str) -> str:
    if stack_name.startswith("preview-pr-"):
        # preview-pr-17 -> myapi-pr-17
        suffix = stack_name.removeprefix("preview-")
        return f"{app_slug}-{suffix}"
    return f"{app_slug}-{stack_name}"


def default_runtime_sa_email_for_stack(
    app_slug: str,
    stack_name: str,
    project_id: str,
) -> str:
    if is_preview_stack(stack_name):
        runtime_sa_id = f"{app_slug}-preview-runtime"
    else:
        runtime_sa_id = f"{app_slug}-{stack_name}-runtime"
    return f"{runtime_sa_id}@{project_id}.iam.gserviceaccount.com"


def default_secret_name_for_stack(stack_name: str) -> str:
    if stack_name == "prod":
        return "USDA_API_KEY_PROD"
    if is_preview_stack(stack_name):
        return "USDA_API_KEY_PREVIEW"
    return "USDA_API_KEY_STAGING"


def default_public_access_for_stack(stack_name: str) -> bool:
    return stack_name == "prod" or is_preview_stack(stack_name)


def default_app_env_for_stack(stack_name: str) -> str:
    if stack_name == "prod":
        return "prod"
    if is_preview_stack(stack_name):
        return "preview"
    return stack_name


app_name = read_app_name_from_pyproject()
app_slug = slugify(app_name)
stack = pulumi.get_stack()

cfg = Config()
gcp_cfg = Config("gcp")

project_id = gcp_cfg.require("project")
region = gcp_cfg.require("region")

default_secret_name = default_secret_name_for_stack(stack)
default_min_instances = 0
default_max_instances = 1
default_deletion_protection = stack == "prod"
default_timeout = "60s"
default_public_access = default_public_access_for_stack(stack)
default_service_name = default_service_name_for_stack(app_slug, stack)
default_runtime_sa_email = default_runtime_sa_email_for_stack(
    app_slug,
    stack,
    project_id,
)
default_app_env = default_app_env_for_stack(stack)

service_name = cfg.get("serviceName") or default_service_name
image_by_digest = cfg.require("imageByDigest")
usda_secret_name = cfg.get("usdaSecretName") or default_secret_name
usda_secret_version = cfg.get("usdaSecretVersion") or "latest"
runtime_service_account_email = (
    cfg.get("runtimeServiceAccountEmail") or default_runtime_sa_email
)

public_access = cfg_bool(cfg, "publicAccess", default_public_access)

# Only private stacks should use a specific invoker member.
invoker_member: str | None = None
if not public_access:
    invoker_member = cfg.get("invokerMember") or cfg.get(f"{stack}InvokerMember")

container_port = cfg_int(cfg, "containerPort", 8080)
min_instance_count = cfg_int(cfg, "minInstanceCount", default_min_instances)
max_instance_count = cfg_int(cfg, "maxInstanceCount", default_max_instances)

cpu_limit = cfg.get("cpu") or "1"
memory_limit = cfg.get("memory") or "512Mi"
timeout = cfg.get("timeout") or default_timeout
ingress = cfg.get("ingress") or "INGRESS_TRAFFIC_ALL"
app_env = cfg.get("appEnv") or default_app_env
cpu_idle = cfg_bool(cfg, "cpuIdle", True)
startup_cpu_boost = cfg_bool(cfg, "startupCpuBoost", False)

provider = gcp.Provider(
    "gcp-provider",
    project=project_id,
    region=region,
)

service_template = gcp.cloudrunv2.ServiceTemplateArgs(
    service_account=runtime_service_account_email,
    timeout=timeout,
    containers=[
        gcp.cloudrunv2.ServiceTemplateContainerArgs(
            image=image_by_digest,
            ports=gcp.cloudrunv2.ServiceTemplateContainerPortsArgs(
                container_port=container_port,
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
                            secret=usda_secret_name,
                            version=usda_secret_version,
                        ),
                    ),
                ),
            ],
            resources=gcp.cloudrunv2.ServiceTemplateContainerResourcesArgs(
                cpu_idle=cpu_idle,
                startup_cpu_boost=startup_cpu_boost,
                limits={
                    "cpu": cpu_limit,
                    "memory": memory_limit,
                },
            ),
        ),
    ],
    scaling=gcp.cloudrunv2.ServiceTemplateScalingArgs(
        min_instance_count=min_instance_count,
        max_instance_count=max_instance_count,
    ),
)

service = gcp.cloudrunv2.Service(
    "service",
    project=project_id,
    location=region,
    name=service_name,
    deletion_protection=default_deletion_protection,
    ingress=ingress,
    invoker_iam_disabled=public_access,
    template=service_template,
    opts=ResourceOptions(provider=provider),
)

if invoker_member:
    gcp.cloudrunv2.ServiceIamMember(
        f"{stack}-invoker",
        project=project_id,
        location=region,
        name=service.name,
        role="roles/run.invoker",
        member=invoker_member,
        opts=ResourceOptions(provider=provider),
    )

pulumi.export("stack", stack)
pulumi.export("appName", app_name)
pulumi.export("serviceName", service.name)
pulumi.export("serviceUrl", service.uri)
pulumi.export("runtimeServiceAccountEmail", runtime_service_account_email)
pulumi.export("secretName", usda_secret_name)
pulumi.export("deployedImage", image_by_digest)
pulumi.export("publicAccess", public_access)
pulumi.export("minInstanceCount", min_instance_count)
pulumi.export("maxInstanceCount", max_instance_count)
pulumi.export("timeout", timeout)
pulumi.export("cpuIdle", cpu_idle)
pulumi.export("startupCpuBoost", startup_cpu_boost)


# from __future__ import annotations

# from pathlib import Path
# import re
# import tomllib

# import pulumi
# import pulumi_gcp as gcp
# from pulumi import Config, ResourceOptions


# def read_app_name_from_pyproject() -> str:
#     repo_root = Path(__file__).resolve().parents[2]
#     pyproject_path = repo_root / "pyproject.toml"

#     with pyproject_path.open("rb") as f:
#         data = tomllib.load(f)

#     return data["project"]["name"]


# def slugify(value: str) -> str:
#     value = value.lower()
#     value = re.sub(r"[._]+", "-", value)
#     value = re.sub(r"[^a-z0-9-]+", "-", value)
#     value = re.sub(r"^-+|-+$", "", value)
#     value = re.sub(r"-{2,}", "-", value)
#     return value


# def cfg_bool(cfg: Config, key: str, default: bool) -> bool:
#     value = cfg.get_bool(key)
#     return default if value is None else value


# def cfg_int(cfg: Config, key: str, default: int) -> int:
#     value = cfg.get_int(key)
#     return default if value is None else value


# app_name = read_app_name_from_pyproject()
# app_slug = slugify(app_name)
# stack = pulumi.get_stack()

# cfg = Config()
# gcp_cfg = Config("gcp")

# project_id = gcp_cfg.require("project")
# region = gcp_cfg.require("region")

# default_secret_name = "USDA_API_KEY_PROD" if stack == "prod" else "USDA_API_KEY_STAGING"
# default_min_instances = 0
# default_max_instances = 1
# default_deletion_protection = stack == "prod"
# default_timeout = "60s"
# default_public_access = stack == "prod"

# service_name = f"{app_slug}-{stack}"
# runtime_sa_id = f"{app_slug}-{stack}-runtime"
# default_runtime_sa_email = f"{runtime_sa_id}@{project_id}.iam.gserviceaccount.com"

# image_by_digest = cfg.require("imageByDigest")
# usda_secret_name = cfg.get("usdaSecretName") or default_secret_name
# usda_secret_version = cfg.get("usdaSecretVersion") or "latest"
# runtime_service_account_email = (
#     cfg.get("runtimeServiceAccountEmail") or default_runtime_sa_email
# )

# public_access = cfg_bool(cfg, "publicAccess", default_public_access)

# # Only private stacks should use a specific invoker member.
# invoker_member: str | None = None
# if not public_access:
#     invoker_member = cfg.get("invokerMember") or cfg.get(f"{stack}InvokerMember")

# container_port = cfg_int(cfg, "containerPort", 8080)
# min_instance_count = cfg_int(cfg, "minInstanceCount", default_min_instances)
# max_instance_count = cfg_int(cfg, "maxInstanceCount", default_max_instances)

# cpu_limit = cfg.get("cpu") or "1"
# memory_limit = cfg.get("memory") or "512Mi"
# timeout = cfg.get("timeout") or default_timeout
# ingress = cfg.get("ingress") or "INGRESS_TRAFFIC_ALL"
# app_env = cfg.get("appEnv") or stack
# cpu_idle = cfg_bool(cfg, "cpuIdle", True)
# startup_cpu_boost = cfg_bool(cfg, "startupCpuBoost", False)

# provider = gcp.Provider(
#     "gcp-provider",
#     project=project_id,
#     region=region,
# )

# service_template = gcp.cloudrunv2.ServiceTemplateArgs(
#     service_account=runtime_service_account_email,
#     timeout=timeout,
#     containers=[
#         gcp.cloudrunv2.ServiceTemplateContainerArgs(
#             image=image_by_digest,
#             ports=gcp.cloudrunv2.ServiceTemplateContainerPortsArgs(
#                 container_port=container_port,
#             ),
#             envs=[
#                 gcp.cloudrunv2.ServiceTemplateContainerEnvArgs(
#                     name="APP_ENV",
#                     value=app_env,
#                 ),
#                 gcp.cloudrunv2.ServiceTemplateContainerEnvArgs(
#                     name="USDA_API_KEY",
#                     value_source=gcp.cloudrunv2.ServiceTemplateContainerEnvValueSourceArgs(
#                         secret_key_ref=gcp.cloudrunv2.ServiceTemplateContainerEnvValueSourceSecretKeyRefArgs(
#                             secret=usda_secret_name,
#                             version=usda_secret_version,
#                         ),
#                     ),
#                 ),
#             ],
#             resources=gcp.cloudrunv2.ServiceTemplateContainerResourcesArgs(
#                 cpu_idle=cpu_idle,
#                 startup_cpu_boost=startup_cpu_boost,
#                 limits={
#                     "cpu": cpu_limit,
#                     "memory": memory_limit,
#                 },
#             ),
#         ),
#     ],
#     scaling=gcp.cloudrunv2.ServiceTemplateScalingArgs(
#         min_instance_count=min_instance_count,
#         max_instance_count=max_instance_count,
#     ),
# )

# service = gcp.cloudrunv2.Service(
#     "service",
#     project=project_id,
#     location=region,
#     name=service_name,
#     deletion_protection=default_deletion_protection,
#     ingress=ingress,
#     invoker_iam_disabled=public_access,
#     template=service_template,
#     opts=ResourceOptions(provider=provider),
# )

# if invoker_member:
#     gcp.cloudrunv2.ServiceIamMember(
#         f"{stack}-invoker",
#         project=project_id,
#         location=region,
#         name=service.name,
#         role="roles/run.invoker",
#         member=invoker_member,
#         opts=ResourceOptions(provider=provider),
#     )

# pulumi.export("stack", stack)
# pulumi.export("appName", app_name)
# pulumi.export("serviceName", service.name)
# pulumi.export("serviceUrl", service.uri)
# pulumi.export("runtimeServiceAccountEmail", runtime_service_account_email)
# pulumi.export("secretName", usda_secret_name)
# pulumi.export("deployedImage", image_by_digest)
# pulumi.export("publicAccess", public_access)
# pulumi.export("minInstanceCount", min_instance_count)
# pulumi.export("maxInstanceCount", max_instance_count)
# pulumi.export("timeout", timeout)
# pulumi.export("cpuIdle", cpu_idle)
# pulumi.export("startupCpuBoost", startup_cpu_boost)
