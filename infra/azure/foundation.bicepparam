using './foundation.bicep'

// Copy this file privately for each environment before deployment. Do not add
// passwords or a real production resource prefix to the repository.
param location = 'southeastasia'
param resourcePrefix = 'replace-me'
param environment = 'staging'
// Provide securely at deployment time. Do not write a real password in this file.
param postgresAdministratorPassword = ''
param postgresHighAvailability = 'Disabled'
// Confirm regional availability and the cost guardrail before retaining this default.
param redisSkuName = 'Balanced_B0'
