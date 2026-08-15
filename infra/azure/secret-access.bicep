targetScope = 'resourceGroup'

@description('Existing Key Vault name from the foundation deployment.')
param keyVaultName string

@description('Existing runtime user-assigned managed identity name from the foundation deployment.')
param runtimeIdentityName string

@description('Existing migration user-assigned managed identity name from the foundation deployment.')
param migrationIdentityName string

// Secret values are never parameters to this template. The named secrets must
// be created through the approved private-network bootstrap procedure before
// this template is deployed.
var keyVaultSecretsUserRoleDefinitionId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '4633458b-17de-408a-b874-0445c86b69e6'
)

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource runtimeIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: runtimeIdentityName
}

resource migrationIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: migrationIdentityName
}

resource appDatabaseUrlSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' existing = {
  parent: vault
  name: 'app-database-url'
}

resource jwtSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' existing = {
  parent: vault
  name: 'app-jwt-secret'
}

resource redisUrlSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' existing = {
  parent: vault
  name: 'app-rate-limit-redis-url'
}

resource smtpUsernameSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' existing = {
  parent: vault
  name: 'app-smtp-username'
}

resource smtpPasswordSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' existing = {
  parent: vault
  name: 'app-smtp-password'
}

resource operationsHealthTokenSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' existing = {
  parent: vault
  name: 'app-operations-health-token'
}

resource migrationDatabaseUrlSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' existing = {
  parent: vault
  name: 'app-migration-database-url'
}

resource runtimeDatabaseSecretAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(appDatabaseUrlSecret.id, runtimeIdentity.id, keyVaultSecretsUserRoleDefinitionId)
  scope: appDatabaseUrlSecret
  properties: {
    roleDefinitionId: keyVaultSecretsUserRoleDefinitionId
    principalId: runtimeIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource runtimeJwtSecretAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(jwtSecret.id, runtimeIdentity.id, keyVaultSecretsUserRoleDefinitionId)
  scope: jwtSecret
  properties: {
    roleDefinitionId: keyVaultSecretsUserRoleDefinitionId
    principalId: runtimeIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource runtimeRedisSecretAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(redisUrlSecret.id, runtimeIdentity.id, keyVaultSecretsUserRoleDefinitionId)
  scope: redisUrlSecret
  properties: {
    roleDefinitionId: keyVaultSecretsUserRoleDefinitionId
    principalId: runtimeIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource runtimeSmtpUsernameSecretAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(smtpUsernameSecret.id, runtimeIdentity.id, keyVaultSecretsUserRoleDefinitionId)
  scope: smtpUsernameSecret
  properties: {
    roleDefinitionId: keyVaultSecretsUserRoleDefinitionId
    principalId: runtimeIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource runtimeSmtpPasswordSecretAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(smtpPasswordSecret.id, runtimeIdentity.id, keyVaultSecretsUserRoleDefinitionId)
  scope: smtpPasswordSecret
  properties: {
    roleDefinitionId: keyVaultSecretsUserRoleDefinitionId
    principalId: runtimeIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource runtimeOperationsHealthTokenAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(
    operationsHealthTokenSecret.id,
    runtimeIdentity.id,
    keyVaultSecretsUserRoleDefinitionId
  )
  scope: operationsHealthTokenSecret
  properties: {
    roleDefinitionId: keyVaultSecretsUserRoleDefinitionId
    principalId: runtimeIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource migrationDatabaseSecretAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(migrationDatabaseUrlSecret.id, migrationIdentity.id, keyVaultSecretsUserRoleDefinitionId)
  scope: migrationDatabaseUrlSecret
  properties: {
    roleDefinitionId: keyVaultSecretsUserRoleDefinitionId
    principalId: migrationIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}
