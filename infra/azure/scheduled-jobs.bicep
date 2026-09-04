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

@description('Existing Azure OpenAI account name used only by catalogue extraction.')
param catalogueAiResourceName string = ''

@description('Azure OpenAI endpoint. Leave empty while catalogue AI ingestion is disabled.')
param catalogueAiEndpoint string = ''

@description('Deployment name supporting strict structured outputs. Configuration, not a secret.')
param catalogueAiModel string = 'unconfigured'

@description('Fail-closed catalogue extraction feature gate. Enable only after gold evaluation.')
param catalogueAiIngestionEnabled bool = false

@description('Bounded official-site crawling gate for reviewed acquisition runs.')
param catalogueBoundedCrawlingEnabled bool = true

@description('Maximum accepted official-source artifacts per catalogue candidate.')
@minValue(1)
@maxValue(25)
param catalogueAiMaxPagesPerCandidate int = 10

@description('Reviewed input-token price per million; required to enable catalogue AI.')
param catalogueAiInputCostPerMillion string = '0'

@description('Reviewed output-token price per million; required to enable catalogue AI.')
param catalogueAiOutputCostPerMillion string = '0'

@description('Optional existing private seed Blob storage account for managed-identity reads.')
param catalogueSeedStorageAccountName string = ''

var containerEnvironmentName = '${resourcePrefix}-apps'
var registryName = replace('${resourcePrefix}acr', '-', '')
var keyVaultName = '${resourcePrefix}-kv'
var runtimeIdentityName = '${resourcePrefix}-runtime-id'
var applicationInsightsName = '${resourcePrefix}-insights'
var cognitiveServicesOpenAiUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
var storageBlobDataReaderRoleId = '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
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
  {
    name: 'operations-health-token'
    keyVaultUrl: '${secretBaseUrl}/app-operations-health-token'
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
    name: 'APP_OPERATIONS_HEALTH_TOKEN'
    secretRef: 'operations-health-token'
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
    name: 'APP_METRICS_BACKEND'
    value: 'external'
  }
  {
    name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
    value: applicationInsights.properties.ConnectionString
  }
  {
    name: 'APP_PASSWORD_BREACH_CHECK_ENABLED'
    value: 'true'
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
    name: 'APP_SOURCE_MONITOR_BATCH_LIMIT'
    value: '100'
  }
  {
    name: 'APP_SOURCE_MONITOR_CLAIM_SECONDS'
    value: '900'
  }
  {
    name: 'APP_SOURCE_MONITOR_PER_HOST_INTERVAL_SECONDS'
    value: '1.0'
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

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: applicationInsightsName
}

resource catalogueAiAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = if (!empty(catalogueAiResourceName)) {
  name: catalogueAiResourceName
}

resource catalogueAiUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(catalogueAiResourceName)) {
  name: guid(catalogueAiAccount.id, runtimeIdentity.id, cognitiveServicesOpenAiUserRoleId)
  scope: catalogueAiAccount
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      cognitiveServicesOpenAiUserRoleId
    )
    principalId: runtimeIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource catalogueSeedStorage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = if (!empty(catalogueSeedStorageAccountName)) {
  name: catalogueSeedStorageAccountName
}

resource catalogueSeedBlobReaderRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(catalogueSeedStorageAccountName)) {
  name: guid(catalogueSeedStorage.id, runtimeIdentity.id, storageBlobDataReaderRoleId)
  scope: catalogueSeedStorage
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      storageBlobDataReaderRoleId
    )
    principalId: runtimeIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
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

// Manual-only, bounded bulk work. Deploying this job never starts an import;
// operators supply an explicit seed URI and mode when starting an execution.
resource catalogueIngestionJob 'Microsoft.App/jobs@2024-03-01' = {
  name: '${resourcePrefix}-catalogue-ingestion'
  location: resourceGroup().location
  tags: {
    application: 'scholarship-ai-assistant'
    environment: environment
    workload: 'manual-job'
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
      triggerType: 'Manual'
      replicaTimeout: 7200
      replicaRetryLimit: 0
      manualTriggerConfig: {
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
          command: [
            'python'
            '-m'
            'app.cli.ingest_catalogue_seeds'
            '--help'
          ]
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: concat(commonEnvironment, [
            {
              name: 'AZURE_CLIENT_ID'
              value: runtimeIdentity.properties.clientId
            }
            {
              name: 'APP_CATALOGUE_AI_INGESTION_ENABLED'
              value: string(catalogueAiIngestionEnabled)
            }
            {
              name: 'APP_CATALOGUE_AI_PROVIDER'
              value: catalogueAiIngestionEnabled ? 'azure_openai' : 'unavailable'
            }
            {
              name: 'APP_CATALOGUE_AI_ENDPOINT'
              value: catalogueAiEndpoint
            }
            {
              name: 'APP_CATALOGUE_AI_MODEL'
              value: catalogueAiModel
            }
            {
              name: 'APP_CATALOGUE_WEB_DISCOVERY_ENABLED'
              value: 'false'
            }
            {
              name: 'APP_CATALOGUE_BOUNDED_CRAWLING_ENABLED'
              value: string(catalogueBoundedCrawlingEnabled)
            }
            {
              name: 'APP_CATALOGUE_DOCUMENT_INTELLIGENCE_ENABLED'
              value: 'false'
            }
            {
              name: 'APP_CATALOGUE_AI_MAX_CANDIDATES_PER_RUN'
              value: '500'
            }
            {
              name: 'APP_CATALOGUE_AI_MAX_PAGES_PER_CANDIDATE'
              value: string(catalogueAiMaxPagesPerCandidate)
            }
            {
              name: 'APP_CATALOGUE_AI_MAX_CALLS_PER_RUN'
              value: '100'
            }
            {
              name: 'APP_CATALOGUE_AI_MAX_ESTIMATED_COST_PER_RUN'
              value: '5.00'
            }
            {
              name: 'APP_CATALOGUE_AI_INPUT_COST_PER_MILLION'
              value: catalogueAiInputCostPerMillion
            }
            {
              name: 'APP_CATALOGUE_AI_OUTPUT_COST_PER_MILLION'
              value: catalogueAiOutputCostPerMillion
            }
          ])
        }
      ]
    }
  }
}

output scheduledJobNames array = [for job in scheduledWorkloads: job.name]
output catalogueIngestionJobName string = catalogueIngestionJob.name
