using './foundation.bicep'

// Copy this file privately for each environment before deployment. Do not add
// passwords or a real production resource prefix to the repository.
param location = 'southeastasia'
param resourcePrefix = 'replace-me'
param environment = 'staging'
param postgresAdministratorPassword = ''
param postgresHighAvailability = 'Disabled'
