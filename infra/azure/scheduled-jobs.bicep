targetScope = 'resourceGroup'

@description('Prefix used by the foundation deployment.')
param resourcePrefix string

@allowed([
  'staging'
  'beta'
])
param environment string

@description('Immutable OCI image reference in digest form, for example registry.azurecr.io/repository@sha256:... .')
param imageReference string

@description('Exact HTTPS origin for the running app.')
param appOrigin string

@description('WebAuthn relying-party ID matching appOrigin.')
param webauthnRpId string

@description('Approved transactional sender address. This is non-secret deployment configuration.')
param smtpFrom string

@description('Approved SMTP hostname. Credentials remain in Key Vault.')
param smtpHost string

var containerEnvironmentName = '${resourcePrefix}-apps'
var registryName = replace('${resourcePrefix}acr', '-', '')
var keyVaultName = '${resourcePrefix}-kv'
var runtimeIdentityName = '${resourcePrefix}-runtime-id'
var secretBaseUrl = 'https://${keyVaultName}.${az.environment().suffixes.keyvaultDns}/secrets'
var scheduledWorkloads = [
  {
    name: '${resourcePrefix}-source-monitor'
    command: [
      'python'
      '-m'
      'app.cli.monitor_sources'
    ]
    cron: '0 2 * * *'
    timeout: 1800
  }
  {
    name: '${resourcePrefix}-reminder-dispatch'
    command: [
      'python'
      '-m'
      'app.cli.dispatch_reminders'
    ]
    cron: '*/5 * * * *'
    timeout: 600
  }
  {
    name: '${resourcePrefix}-retention'
    command: [
      'python'
      '-m'
      'app.cli.run_retention'
    ]
    cron: '15 3 * * *'
    timeout: 1800
  }
]
var sharedSecrets = [
  {
    name: 'database-url'
    keyVaultUrl: '${secretBaseUrl}/app-database-url'
    identity: runtimeIdentity.id
  }
  {
    name: 'jwt-secret'
    keyVaultUrl: '${secretBaseUrl}/app-jwt-secret'
    identity: runtimeIdentity.id
  }
  {
    name: 'redis-url'
    keyVaultUrl: '${secretBaseUrl}/app-rate-limit-redis-url'
    identity: runtimeIdentity.id
  }
  {
    name: 'smtp-username'
    keyVaultUrl: '${secretBaseUrl}/app-smtp-username'
    identity: runtimeIdentity.id
  }
  {
    name: 'smtp-password'
    keyVaultUrl: '${secretBaseUrl}/app-smtp-password'
    identity: runtimeIdentity.id
  }
]
var commonEnvironment = [
  {
    name: 'APP_ENV'
    value: 'production'
  }
  {
    name: 'APP_RELEASE_VERSION'
    value: imageReference
  }
  {
    name: 'APP_DATABASE_URL'
    secretRef: 'database-url'
  }
  {
    name: 'APP_JWT_SECRET'
    secretRef: 'jwt-secret'
  }
  {
    name: 'APP_RATE_LIMIT_REDIS_URL'
    secretRef: 'redis-url'
  }
  {
    name: 'APP_EMAIL_SMTP_USERNAME'
    secretRef: 'smtp-username'
  }
  {
    name: 'APP_EMAIL_SMTP_PASSWORD'
    secretRef: 'smtp-password'
  }
  {
    name: 'APP_CORS_ORIGINS'
    value: appOrigin
  }
  {
    name: 'APP_TRUSTED_PROXY_MODE'
    value: 'azure-container-apps'
  }
  {
    name: 'APP_RATE_LIMIT_BACKEND'
    value: 'redis'
  }
  {
    name: 'APP_EMAIL_PROVIDER'
    value: 'smtp'
  }
  {
    name: 'APP_EMAIL_FROM'
    value: smtpFrom
  }
  {
    name: 'APP_EMAIL_SMTP_HOST'
    value: smtpHost
  }
  {
    name: 'APP_BETA_ENABLED'
    value: 'false'
  }
  {
    name: 'APP_ASSISTANT_ENABLED'
    value: 'false'
  }
  {
    name: 'APP_ASSISTANT_PROVIDER'
    value: 'evidence-template'
  }
  {
    name: 'APP_DOCUMENT_LAB_ENABLED'
    value: 'false'
  }
  {
    name: 'APP_COMMUNITY_ENABLED'
    value: 'false'
  }
  {
    name: 'APP_WEBAUTHN_RP_ID'
    value: webauthnRpId
  }
  {
    name: 'APP_WEBAUTHN_ORIGINS'
    value: appOrigin
  }
]

resource containerEnvironment 'Microsoft.App/managedEnvironments@2025-01-01' existing = {
  name: containerEnvironmentName
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: registryName
}

resource runtimeIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: runtimeIdentityName
}

resource scheduledJobs 'Microsoft.App/jobs@2024-03-01' = [
  for job in scheduledWorkloads: {
    name: job.name
    location: resourceGroup().location
    tags: {
      application: 'scholarship-ai-assistant'
      environment: environment
      workload: 'scheduled-job'
      managedBy: 'bicep'
    }
    identity: {
      type: 'UserAssigned'
      userAssignedIdentities: {
        '${runtimeIdentity.id}': {}
      }
    }
    properties: {
      environmentId: containerEnvironment.id
      configuration: {
        triggerType: 'Schedule'
        replicaTimeout: job.timeout
        replicaRetryLimit: 1
        scheduleTriggerConfig: {
          cronExpression: job.cron
          parallelism: 1
          replicaCompletionCount: 1
        }
        registries: [
          {
            server: registry.properties.loginServer
            identity: runtimeIdentity.id
          }
        ]
        secrets: sharedSecrets
      }
      template: {
        containers: [
          {
            name: 'job'
            image: imageReference
            command: job.command
            resources: {
              cpu: json('0.25')
              memory: '0.5Gi'
            }
            env: commonEnvironment
          }
        ]
      }
    }
  }
]

output scheduledJobNames array = [for job in scheduledWorkloads: job.name]
