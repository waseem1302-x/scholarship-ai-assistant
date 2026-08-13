targetScope = 'resourceGroup'

@description('Azure region. Confirm service availability and data-residency requirements before deployment.')
param location string = resourceGroup().location

@description('Lowercase 3-24 character prefix used in globally unique resource names.')
@minLength(3)
@maxLength(19)
param resourcePrefix string

@allowed([
  'staging'
  'beta'
])
param environment string

@description('PostgreSQL administrator used only to bootstrap limited database roles. Keep only in deployment secret handling.')
@secure()
param postgresAdministratorPassword string

@description('PostgreSQL availability mode. Start ZoneRedundant only after confirming the selected region supports it and the budget is approved.')
@allowed([
  'Disabled'
  'ZoneRedundant'
])
param postgresHighAvailability string = 'Disabled'

@description('Tags applied to every resource for cost and ownership reporting.')
param tags object = {
  application: 'scholarship-ai-assistant'
  environment: environment
  managedBy: 'bicep'
}

var vnetName = '${resourcePrefix}-network'
var logWorkspaceName = '${resourcePrefix}-logs'
var keyVaultName = '${resourcePrefix}-kv'
var registryName = replace('${resourcePrefix}acr', '-', '')
var storageAccountName = toLower(replace('${resourcePrefix}files', '-', ''))
var postgresName = '${resourcePrefix}-postgres'
var containerEnvironmentName = '${resourcePrefix}-apps'
var databaseName = 'scholarship'

resource network 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: vnetName
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        '10.70.0.0/16'
      ]
    }
    subnets: [
      {
        name: 'container-apps'
        properties: {
          // A /24 leaves headroom for revisions and future workloads. It is
          // dedicated to the Container Apps environment as Azure requires.
          addressPrefix: '10.70.0.0/24'
          delegations: [
            {
              name: 'container-apps-delegation'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
      {
        name: 'postgres'
        properties: {
          addressPrefix: '10.70.1.0/24'
          delegations: [
            {
              name: 'postgres-delegation'
              properties: {
                serviceName: 'Microsoft.DBforPostgreSQL/flexibleServers'
              }
            }
          ]
        }
      }
      {
        name: 'private-endpoints'
        properties: {
          addressPrefix: '10.70.2.0/24'
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
    ]
  }
}

resource appSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' existing = {
  parent: network
  name: 'container-apps'
}

resource postgresSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' existing = {
  parent: network
  name: 'postgres'
}

resource postgresPrivateDns 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: '${resourcePrefix}.postgres.database.azure.com'
  location: 'global'
  tags: tags
}

resource postgresPrivateDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: postgresPrivateDns
  name: '${resourcePrefix}-postgres-link'
  location: 'global'
  properties: {
    virtualNetwork: {
      id: network.id
    }
    registrationEnabled: false
  }
}

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: postgresName
  location: location
  tags: tags
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    version: '16'
    administratorLogin: 'platformadmin'
    administratorLoginPassword: postgresAdministratorPassword
    availabilityZone: '1'
    highAvailability: {
      mode: postgresHighAvailability
      standbyAvailabilityZone: '2'
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    maintenanceWindow: {
      customWindow: 'Enabled'
      dayOfWeek: 0
      startHour: 2
      startMinute: 0
    }
    storage: {
      storageSizeGB: 32
      autoGrow: 'Enabled'
      type: 'Premium_LRS'
    }
    network: {
      delegatedSubnetResourceId: postgresSubnet.id
      privateDnsZoneArmResourceId: postgresPrivateDns.id
      publicNetworkAccess: 'Disabled'
    }
    authConfig: {
      activeDirectoryAuth: 'Disabled'
      passwordAuth: 'Enabled'
    }
  }
  dependsOn: [
    postgresPrivateDnsLink
  ]
}

resource scholarshipDatabase 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgres
  name: databaseName
  properties: {}
}

resource workspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logWorkspaceName
  location: location
  tags: tags
  sku: {
    name: 'PerGB2018'
  }
  properties: {
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
    retentionInDays: 30
    workspaceCapping: {
      dailyQuotaGb: 1
    }
  }
}

resource containerEnvironment 'Microsoft.App/managedEnvironments@2025-01-01' = {
  name: containerEnvironmentName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: workspace.properties.customerId
        sharedKey: workspace.listKeys().primarySharedKey
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: appSubnet.id
    }
  }
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: registryName
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
    networkRuleBypassOptions: 'AzureServices'
  }
}

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    enablePurgeProtection: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    publicNetworkAccess: 'Enabled'
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  tags: tags
  sku: {
    name: 'Standard_RAGRS'
  }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    publicNetworkAccess: 'Disabled'
    encryption: {
      keySource: 'Microsoft.Storage'
      services: {
        blob: {
          enabled: true
        }
      }
    }
  }
}

output containerAppsEnvironmentId string = containerEnvironment.id
output containerRegistryLoginServer string = registry.properties.loginServer
output keyVaultUri string = vault.properties.vaultUri
output postgresServerName string = postgres.name
output postgresDatabaseName string = scholarshipDatabase.name
output storageAccountId string = storage.id
