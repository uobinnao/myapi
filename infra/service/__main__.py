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


app_name = read_app_name_from_pyproject()
app_slug = slugify(app_name)
stack = pulumi.get_stack()

cfg = Config()
gcp_cfg = Config("gcp")

project_id = gcp_cfg.require("project")
region = gcp_cfg.require("region")

default_secret_name = "USDA_API_KEY_PROD" if stack == "prod" else "USDA_API_KEY_STAGING"
default_min_instances = 0
default_max_instances = 1
default_deletion_protection = stack == "prod"
default_timeout = "60s"

service_name = f"{app_slug}-{stack}"
runtime_sa_id = f"{app_slug}-{stack}-runtime"
default_runtime_sa_email = f"{runtime_sa_id}@{project_id}.iam.gserviceaccount.com"

image_by_digest = cfg.require("imageByDigest")
usda_secret_name = cfg.get("usdaSecretName") or default_secret_name
usda_secret_version = cfg.get("usdaSecretVersion") or "latest"
runtime_service_account_email = (
    cfg.get("runtimeServiceAccountEmail") or default_runtime_sa_email
)

allow_unauthenticated = cfg_bool(cfg, "allowUnauthenticated", False)

# Supports both the new generic key and your old stack-specific key.
invoker_member = cfg.get(f"{stack}InvokerMember")

container_port = cfg_int(cfg, "containerPort", 8080)
min_instance_count = cfg_int(cfg, "minInstanceCount", default_min_instances)
max_instance_count = cfg_int(cfg, "maxInstanceCount", default_max_instances)

cpu_limit = cfg.get("cpu") or "1"
memory_limit = cfg.get("memory") or "512Mi"
timeout = cfg.get("timeout") or default_timeout
ingress = cfg.get("ingress") or "INGRESS_TRAFFIC_ALL"
app_env = cfg.get("appEnv") or stack
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
    invoker_iam_disabled=allow_unauthenticated,
    template=service_template,
    opts=ResourceOptions(provider=provider),
)

if invoker_member and not allow_unauthenticated:
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
pulumi.export("minInstanceCount", min_instance_count)
pulumi.export("maxInstanceCount", max_instance_count)
pulumi.export("timeout", timeout)
pulumi.export("cpuIdle", cpu_idle)
pulumi.export("startupCpuBoost", startup_cpu_boost)

#################################################a#

# from __future__ import annotations

# from pathlib import Path
# import re
# import tomllib

# import pulumi
# import pulumi_gcp as gcp
# from pulumi import Config, InvokeOptions, ResourceOptions


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


# def cfg_float(cfg: Config, key: str) -> float | None:
#     value = cfg.get(key)
#     return None if value is None else float(value)


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
# default_logging_retention_days = 30

# service_name = f"{app_slug}-{stack}"
# runtime_sa_id = f"{app_slug}-{stack}-runtime"

# image_by_digest = cfg.require("imageByDigest")
# usda_secret_name = cfg.get("usdaSecretName") or default_secret_name
# usda_secret_version = cfg.get("usdaSecretVersion") or "latest"

# allow_unauthenticated = cfg_bool(cfg, "allowUnauthenticated", False)

# # Supports both the new generic key and your old staging-specific key.
# invoker_member = cfg.get(f"{stack}InvokerMember")

# # Optional: GitHub deployer/service account allowed to attach this runtime SA.
# deployer_member = cfg.get("deployerMember")

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
# logging_retention_days = cfg_int(
#     cfg,
#     "loggingRetentionDays",
#     default_logging_retention_days,
# )

# monthly_budget_usd = cfg_float(cfg, "monthlyBudgetUsd")
# billing_account_id = cfg.get("billingAccountId")
# budget_alert_email = cfg.get("budgetAlertEmail")

# provider = gcp.Provider(
#     "gcp-provider",
#     project=project_id,
#     region=region,
# )

# runtime_sa = gcp.serviceaccount.Account(
#     "runtime-sa",
#     project=project_id,
#     account_id=runtime_sa_id,
#     display_name=f"{service_name} runtime",
#     opts=ResourceOptions(provider=provider),
# )

# secret_accessor = gcp.secretmanager.SecretIamMember(
#     "runtime-secret-accessor",
#     project=project_id,
#     secret_id=usda_secret_name,
#     role="roles/secretmanager.secretAccessor",
#     member=runtime_sa.email.apply(lambda email: f"serviceAccount:{email}"),
#     opts=ResourceOptions(provider=provider),
# )

# depends_on: list[pulumi.Resource] = [runtime_sa, secret_accessor]

# if deployer_member:
#     deployer_runtime_sa_user = gcp.serviceaccount.IAMMember(
#         "deployer-runtime-sa-user",
#         service_account_id=runtime_sa.name,
#         role="roles/iam.serviceAccountUser",
#         member=deployer_member,
#         opts=ResourceOptions(provider=provider),
#     )
#     depends_on.append(deployer_runtime_sa_user)

# service_template = gcp.cloudrunv2.ServiceTemplateArgs(
#     service_account=runtime_sa.email,
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
#     invoker_iam_disabled=allow_unauthenticated,
#     template=service_template,
#     opts=ResourceOptions(
#         provider=provider,
#         depends_on=depends_on,
#     ),
# )

# if invoker_member and not allow_unauthenticated:
#     gcp.cloudrunv2.ServiceIamMember(
#         f"{stack}-invoker",
#         project=project_id,
#         location=region,
#         name=service.name,
#         role="roles/run.invoker",
#         member=invoker_member,
#         opts=ResourceOptions(provider=provider),
#     )

# # Keep the default logging bucket from retaining logs longer than intended.
# default_log_bucket = gcp.logging.ProjectBucketConfig(
#     "default-log-bucket",
#     project=project_id,
#     location="global",
#     bucket_id="_Default",
#     retention_days=logging_retention_days,
#     opts=ResourceOptions(provider=provider),
# )

# budget_email_channel: gcp.monitoring.NotificationChannel | None = None
# monthly_budget: gcp.billing.Budget | None = None

# if monthly_budget_usd is not None:
#     if not billing_account_id:
#         raise ValueError("billingAccountId is required when monthlyBudgetUsd is set")

#     billing_account = gcp.organizations.get_billing_account(
#         billing_account=billing_account_id,
#         opts=InvokeOptions(provider=provider),
#     )
#     project = gcp.organizations.get_project(
#         project_id=project_id,
#         opts=InvokeOptions(provider=provider),
#     )

#     notification_channels: list[pulumi.Input[str]] = []

#     if budget_alert_email:
#         budget_email_channel = gcp.monitoring.NotificationChannel(
#             "budget-email-channel",
#             project=project_id,
#             display_name=f"{service_name} budget email",
#             type="email",
#             labels={
#                 "email_address": budget_alert_email,
#             },
#             opts=ResourceOptions(provider=provider),
#         )
#         notification_channels = [budget_email_channel.id]

#     monthly_budget = gcp.billing.Budget(
#         "monthly-budget",
#         billing_account=billing_account.id,
#         display_name=f"{service_name} monthly budget",
#         budget_filter={
#             "projects": [f"projects/{project.number}"],
#         },
#         amount={
#             "specified_amount": {
#                 "currency_code": "USD",
#                 "units": str(int(monthly_budget_usd)),
#                 "nanos": int(round((monthly_budget_usd % 1) * 1_000_000_000)),
#             },
#         },
#         threshold_rules=[
#             {"threshold_percent": 0.5},
#             {"threshold_percent": 0.9},
#             {"threshold_percent": 1.0},
#             {"threshold_percent": 1.0, "spend_basis": "FORECASTED_SPEND"},
#         ],
#         all_updates_rule=(
#             {
#                 "monitoring_notification_channels": notification_channels,
#                 "disable_default_iam_recipients": True,
#             }
#             if notification_channels
#             else {
#                 "monitoring_notification_channels": [],
#                 "enable_project_level_recipients": True,
#             }
#         ),
#         opts=ResourceOptions(provider=provider),
#     )

# pulumi.export("stack", stack)
# pulumi.export("appName", app_name)
# pulumi.export("serviceName", service.name)
# pulumi.export("serviceUrl", service.uri)
# pulumi.export("runtimeServiceAccountEmail", runtime_sa.email)
# pulumi.export("secretName", usda_secret_name)
# pulumi.export("deployedImage", image_by_digest)
# pulumi.export("minInstanceCount", min_instance_count)
# pulumi.export("maxInstanceCount", max_instance_count)
# pulumi.export("timeout", timeout)
# pulumi.export("cpuIdle", cpu_idle)
# pulumi.export("startupCpuBoost", startup_cpu_boost)
# pulumi.export("loggingRetentionDays", default_log_bucket.retention_days)
# pulumi.export("budgetAlertEmail", budget_alert_email)
# pulumi.export(
#     "monthlyBudgetDisplayName", monthly_budget.display_name if monthly_budget else None
# )


#########################################

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
# default_min_instances = 1 if stack == "prod" else 0
# default_max_instances = 2 if stack == "prod" else 1
# default_deletion_protection = stack == "prod"

# service_name =f"{app_slug}-{stack}"
# runtime_sa_id = f"{app_slug}-{stack}-runtime"

# image_by_digest = cfg.require("imageByDigest")
# usda_secret_name = cfg.get("usdaSecretName") or default_secret_name
# usda_secret_version = cfg.get("usdaSecretVersion") or "latest"

# allow_unauthenticated = cfg_bool(cfg, "allowUnauthenticated", False)

# # Supports both the new generic key and your old staging-specific key.
# invoker_member = cfg.get(f"{stack}InvokerMember")

# # Optional: GitHub deployer/service account allowed to attach this runtime SA.
# deployer_member = cfg.get("deployerMember")

# container_port = cfg_int(cfg, "containerPort", 8080)
# min_instance_count = cfg_int(cfg, "minInstanceCount", default_min_instances)
# max_instance_count = cfg_int(cfg, "maxInstanceCount", default_max_instances)

# cpu_limit = cfg.get("cpu") or "1"
# memory_limit = cfg.get("memory") or "512Mi"
# timeout = cfg.get("timeout") or "300s"
# ingress = cfg.get("ingress") or "INGRESS_TRAFFIC_ALL"
# app_env = cfg.get("appEnv") or stack

# provider = gcp.Provider(
#     "gcp-provider",
#     project=project_id,
#     region=region,
# )

# runtime_sa = gcp.serviceaccount.Account(
#     "runtime-sa",
#     project=project_id,
#     account_id=runtime_sa_id,
#     display_name=f"{service_name} runtime",
#     opts=ResourceOptions(provider=provider),
# )

# secret_accessor = gcp.secretmanager.SecretIamMember(
#     "runtime-secret-accessor",
#     project=project_id,
#     secret_id=usda_secret_name,
#     role="roles/secretmanager.secretAccessor",
#     member=runtime_sa.email.apply(lambda email: f"serviceAccount:{email}"),
#     opts=ResourceOptions(provider=provider),
# )

# depends_on: list[pulumi.Resource] = [runtime_sa, secret_accessor]

# if deployer_member:
#     deployer_runtime_sa_user = gcp.serviceaccount.IAMMember(
#         "deployer-runtime-sa-user",
#         service_account_id=runtime_sa.name,
#         role="roles/iam.serviceAccountUser",
#         member=deployer_member,
#         opts=ResourceOptions(provider=provider),
#     )
#     depends_on.append(deployer_runtime_sa_user)

# service_template = gcp.cloudrunv2.ServiceTemplateArgs(
#     service_account=runtime_sa.email,
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
#     invoker_iam_disabled=allow_unauthenticated,
#     template=service_template,
#     opts=ResourceOptions(
#         provider=provider,
#         depends_on=depends_on,
#     ),
# )

# if invoker_member and not allow_unauthenticated:
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
# pulumi.export("runtimeServiceAccountEmail", runtime_sa.email)
# pulumi.export("secretName", usda_secret_name)
# pulumi.export("deployedImage", image_by_digest)


################################################

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


# app_name = read_app_name_from_pyproject()
# app_slug = slugify(app_name)

# cfg = Config()
# gcp_cfg = Config("gcp")

# project_id = gcp_cfg.require("project")
# region = gcp_cfg.require("region")

# service_name = f"{app_slug}-staging"
# runtime_sa_id = f"{app_slug}-staging-runtime"
# runtime_sa_email = f"{runtime_sa_id}@{project_id}.iam.gserviceaccount.com"

# image_by_digest = cfg.require("imageByDigest")
# usda_secret_name = cfg.get("usdaSecretName") or "USDA_API_KEY_STAGING"
# allow_unauthenticated = cfg.get_bool("allowUnauthenticated") or False
# staging_invoker_member = cfg.get("stagingInvokerMember")

# provider = gcp.Provider(
#     "gcp-provider",
#     project=project_id,
#     region=region,
# )

# service_template = gcp.cloudrunv2.ServiceTemplateArgs(
#     service_account=runtime_sa_email,
#     containers=[
#         gcp.cloudrunv2.ServiceTemplateContainerArgs(
#             image=image_by_digest,
#             ports=gcp.cloudrunv2.ServiceTemplateContainerPortsArgs(
#                 container_port=8080,
#             ),
#             envs=[
#                 gcp.cloudrunv2.ServiceTemplateContainerEnvArgs(
#                     name="APP_ENV",
#                     value="staging",
#                 ),
#                 gcp.cloudrunv2.ServiceTemplateContainerEnvArgs(
#                     name="USDA_API_KEY",
#                     value_source=gcp.cloudrunv2.ServiceTemplateContainerEnvValueSourceArgs(
#                         secret_key_ref=gcp.cloudrunv2.ServiceTemplateContainerEnvValueSourceSecretKeyRefArgs(
#                             secret=usda_secret_name,
#                             version="latest",
#                         )
#                     ),
#                 ),
#             ],
#             resources=gcp.cloudrunv2.ServiceTemplateContainerResourcesArgs(
#                 limits={
#                     "cpu": "1",
#                     "memory": "512Mi",
#                 },
#             ),
#         )
#     ],
#     scaling=gcp.cloudrunv2.ServiceTemplateScalingArgs(
#         min_instance_count=0,
#         max_instance_count=1,
#     ),
# )

# service = gcp.cloudrunv2.Service(
#     "service",
#     project=project_id,
#     location=region,
#     name=service_name,
#     deletion_protection=False,
#     ingress="INGRESS_TRAFFIC_ALL",
#     invoker_iam_disabled=allow_unauthenticated,
#     template=service_template,
#     opts=ResourceOptions(provider=provider),
# )

# if staging_invoker_member and not allow_unauthenticated:
#     gcp.cloudrunv2.ServiceIamMember(
#         "staging-invoker",
#         project=project_id,
#         location=region,
#         name=service.name,
#         role="roles/run.invoker",
#         member=staging_invoker_member,
#         opts=ResourceOptions(provider=provider),
#     )

# pulumi.export("appName", app_name)
# pulumi.export("serviceName", service.name)
# pulumi.export("serviceUrl", service.uri)
# pulumi.export("runtimeServiceAccountEmail", runtime_sa_email)
# pulumi.export("secretName", usda_secret_name)
# pulumi.export("deployedImage", image_by_digest)
