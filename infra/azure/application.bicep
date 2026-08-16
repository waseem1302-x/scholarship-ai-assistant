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

@description('Exact HTTPS origin for the free Container Apps domain. bootstrap.invalid is allowed only for the initial, non-beta staging deployment.')
param appOrigin string

@description('WebAuthn relying-party ID matching appOrigin. Required before enabling beta.')
param webauthnRpId string = 'bootstrap.invalid'

@description('Approved transactional sender address. This is non-secret deployment configuration.')
param smtpFrom string

@description('Approved SMTP hostname. Credentials remain in Key Vault.')
param smtpHost string

@description('Named operational owner contacts required when beta is enabled.')
param betaProductOwnerContact string
param betaSupportContact string
param betaModerationContact string
param betaDataQualityContact string
param betaIncidentContact string

@description('Enables invitation-only beta after the staging release gates have passed. Defaults to false.')
param betaEnabled bool = false

@description('Existing stable revision that must retain traffic while the candidate is verified.')
param stableRevisionName string = ''

@description('Deterministic candidate revision suffix derived from the immutable release commit.')
@minLength(6)
@maxLength(20)
param candidateRevisionSuffix string

var containerEnvironmentName = '${resourcePrefix}-apps'
var registryName = replace('${resourcePrefix}acr', '-', '')
var keyVaultName = '${resourcePrefix}-kv'
var runtimeIdentityName = '${resourcePrefix}-runtime-id'
var appName = '${resourcePrefix}-api'
var logWorkspaceName = '${resourcePrefix}-logs'
var applicationInsightsName = '${resourcePrefix}-insights'
var keyVaultSecretBaseUrl = 'https://${keyVaultName}.${az.environment().suffixes.keyvaultDns}/secrets'

resource containerEnvironment 'Microsoft.App/managedEnvironments@2025-01-01' existing = {
  name: containerEnvironmentName
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: registryName
}

resource runtimeIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: runtimeIdentityName
}

resource logWorkspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' existing = {
  name: logWorkspaceName
}

// A single workspace-backed Application Insights resource aggregates custom
// OpenTelemetry metrics across every active Container Apps API replica.
resource applicationInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: applicationInsightsName
  location: resourceGroup().location
  kind: 'web'
  tags: {
    application: 'scholarship-ai-assistant'
    environment: environment
    managedBy: 'bicep'
  }
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logWorkspace.id
    IngestionMode: 'LogAnalytics'
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: resourceGroup().location
  tags: {
    application: 'scholarship-ai-assistant'
    environment: environment
    managedBy: 'bicep'
  }
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${runtimeIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerEnvironment.id
    configuration: {
      activeRevisionsMode: 'Multiple'
      registries: [
        {
          server: registry.properties.loginServer
          identity: runtimeIdentity.id
        }
      ]
      secrets: [
        {
          name: 'database-url'
          keyVaultUrl: '${keyVaultSecretBaseUrl}/app-database-url'
          identity: runtimeIdentity.id
        }
        {
          name: 'jwt-secret'
          keyVaultUrl: '${keyVaultSecretBaseUrl}/app-jwt-secret'
          identity: runtimeIdentity.id
        }
        {
          name: 'redis-url'
          keyVaultUrl: '${keyVaultSecretBaseUrl}/app-rate-limit-redis-url'
          identity: runtimeIdentity.id
        }
        {
          name: 'smtp-username'
          keyVaultUrl: '${keyVaultSecretBaseUrl}/app-smtp-username'
          identity: runtimeIdentity.id
        }
        {
          name: 'smtp-password'
          keyVaultUrl: '${keyVaultSecretBaseUrl}/app-smtp-password'
          identity: runtimeIdentity.id
        }
        {
          name: 'operations-health-token'
          keyVaultUrl: '${keyVaultSecretBaseUrl}/app-operations-health-token'
          identity: runtimeIdentity.id
        }
      ]
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        traffic: empty(stableRevisionName) ? [] : [
          {
            revisionName: stableRevisionName
            weight: 100
          }
        ]
      }
    }
    template: {
      revisionSuffix: candidateRevisionSuffix
      containers: [
        {
          name: 'api'
          image: imageReference
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
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
              name: 'APP_COOKIE_SECURE'
              value: 'true'
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
              name: 'APP_PASSWORD_BREACH_CHECK_ENABLED'
              value: 'true'
            }
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              value: applicationInsights.properties.ConnectionString
            }
            {
              name: 'OTEL_SERVICE_NAME'
              value: 'scholarship-api-${environment}'
            }
            {
              name: 'OTEL_RESOURCE_ATTRIBUTES'
              value: 'deployment.environment.name=${environment}'
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
              value: string(betaEnabled)
            }
            {
              name: 'APP_BETA_REGISTRATION_OPEN'
              value: 'false'
            }
            {
              name: 'APP_BETA_MAX_ACTIVE_STUDENTS'
              value: '25'
            }
            {
              name: 'APP_BETA_PRODUCT_OWNER_CONTACT'
              value: betaProductOwnerContact
            }
            {
              name: 'APP_BETA_SUPPORT_CONTACT'
              value: betaSupportContact
            }
            {
              name: 'APP_BETA_MODERATION_CONTACT'
              value: betaModerationContact
            }
            {
              name: 'APP_BETA_DATA_QUALITY_CONTACT'
              value: betaDataQualityContact
            }
            {
              name: 'APP_BETA_INCIDENT_CONTACT'
              value: betaIncidentContact
            }
            {
              name: 'APP_WEBAUTHN_RP_ID'
              value: webauthnRpId
            }
            {
              name: 'APP_WEBAUTHN_ORIGINS'
              value: appOrigin
            }
            // Scholarship graph rollout is expand-first. The API continues to
            // serve the existing reviewed Opportunity catalogue in PR 0.
            {
              name: 'APP_CATALOGUE_GRAPH_READS_ENABLED'
              value: 'false'
            }
            {
              name: 'APP_CATALOGUE_GRAPH_WRITES_ENABLED'
              value: 'false'
            }
            {
              name: 'APP_CATALOGUE_AUTO_PUBLISH_ENABLED'
              value: 'false'
            }
            // High-risk capabilities stay server-side disabled. The assistant
            // cannot be switched on by a frontend or a public workflow input.
            {
              name: 'APP_ASSISTANT_ENABLED'
              value: 'false'
            }
            {
              name: 'APP_ASSISTANT_PROVIDER'
              value: 'evidence-template'
            }
            {
              name: 'APP_ASSISTANT_DAILY_USER_LIMIT'
              value: '30'
            }
            {
              name: 'APP_ASSISTANT_MONTHLY_USER_LIMIT'
              value: '300'
            }
            {
              name: 'APP_ASSISTANT_RATE_LIMIT_PER_MINUTE'
              value: '12'
            }
            {
              name: 'APP_ASSISTANT_GLOBAL_DAILY_LIMIT'
              value: '1000'
            }
            {
              name: 'APP_DOCUMENT_LAB_ENABLED'
              value: 'false'
            }
            {
              name: 'APP_DOCUMENT_LAB_GLOBAL_DAILY_UPLOAD_LIMIT'
              value: '500'
            }
            {
              name: 'APP_COMMUNITY_ENABLED'
              value: 'false'
            }
            {
              name: 'APP_REMINDER_WORKER_REQUIRED'
              value: 'true'
            }
          ]
          probes: [
            {
              type: 'Startup'
              httpGet: {
                path: '/health/live'
                port: 8000
              }
              initialDelaySeconds: 3
              periodSeconds: 5
              failureThreshold: 24
              timeoutSeconds: 3
            }
            {
              type: 'Liveness'
              httpGet: {
                path: '/health/live'
                port: 8000
              }
              initialDelaySeconds: 10
              periodSeconds: 10
              failureThreshold: 3
              timeoutSeconds: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health/ready'
                port: 8000
              }
              initialDelaySeconds: 10
              periodSeconds: 10
              failureThreshold: 6
              timeoutSeconds: 5
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 2
        rules: [
          {
            name: 'http-concurrency'
            http: {
              metadata: {
                concurrentRequests: '20'
              }
            }
          }
        ]
      }
    }
  }
}

output appName string = app.name
output appFqdn string = app.properties.configuration.ingress.fqdn
output applicationInsightsName string = applicationInsights.name
