targetScope = 'resourceGroup'

@description('Prefix used by the foundation deployment.')
param resourcePrefix string

@description('Immutable OCI image reference in digest form, for example registry.azurecr.io/repository@sha256:... .')
param imageReference string

var containerEnvironmentName = '${resourcePrefix}-apps'
var registryName = replace('${resourcePrefix}acr', '-', '')
var keyVaultName = '${resourcePrefix}-kv'
var migrationIdentityName = '${resourcePrefix}-migration-id'
var jobName = '${resourcePrefix}-migrate'

resource containerEnvironment 'Microsoft.App/managedEnvironments@2025-01-01' existing = {
  name: containerEnvironmentName
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: registryName
}

resource migrationIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: migrationIdentityName
}

resource migrationJob 'Microsoft.App/jobs@2024-03-01' = {
  name: jobName
  location: resourceGroup().location
  tags: {
    application: 'scholarship-ai-assistant'
    workload: 'migration'
    managedBy: 'bicep'
  }
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${migrationIdentity.id}': {}
    }
  }
  properties: {
    environmentId: containerEnvironment.id
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 1800
      replicaRetryLimit: 0
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: [
        {
          server: registry.properties.loginServer
          identity: migrationIdentity.id
        }
      ]
      secrets: [
        {
          name: 'migration-database-url'
          keyVaultUrl: 'https://${keyVaultName}.${az.environment().suffixes.keyvaultDns}/secrets/app-migration-database-url'
          identity: migrationIdentity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'migrate'
          image: imageReference
          command: [
            'alembic'
            'upgrade'
            'head'
          ]
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            {
              name: 'APP_ENV'
              value: 'production'
            }
            {
              name: 'APP_MIGRATION_ONLY'
              value: 'true'
            }
            {
              name: 'APP_MIGRATION_DATABASE_URL'
              secretRef: 'migration-database-url'
            }
          ]
        }
      ]
    }
  }
}

output migrationJobName string = migrationJob.name
