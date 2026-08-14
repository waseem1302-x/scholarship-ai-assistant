targetScope = 'subscription'

@description('Billing-currency monthly limit. Set to 500 only after confirming this subscription bills in MYR.')
param monthlyBudgetAmount int = 500

@description('Explicit operator confirmation after the Azure billing-currency preflight.')
@allowed([
  'MYR'
])
param confirmedBillingCurrency string

@description('Approved cost-alert recipients. This is not a secret.')
@minLength(1)
param alertEmailAddresses array

@description('Start date at the first day of the current or future billing month, in UTC.')
param budgetStartDate string

@description('Optional tag value used to scope this guardrail to this application across staging and beta.')
param applicationTagValue string = 'scholarship-ai-assistant'

// A subscription-scoped budget sees both isolated environment resource groups.
// Thresholds are 20%, 60%, and 100% of MYR 500: MYR 100, 300, and 500.
resource betaBudget 'Microsoft.Consumption/budgets@2024-08-01' = {
  name: 'scholarship-ai-assistant-monthly'
  properties: {
    amount: monthlyBudgetAmount
    category: 'Cost'
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: budgetStartDate
    }
    filter: {
      tags: {
        name: 'application'
        operator: 'In'
        values: [
          applicationTagValue
        ]
      }
    }
    notifications: {
      warningAt100Myr: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 20
        thresholdType: 'Actual'
        contactEmails: alertEmailAddresses
        contactRoles: []
        contactGroups: []
        locale: 'en-us'
      }
      reviewAt300Myr: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 60
        thresholdType: 'Actual'
        contactEmails: alertEmailAddresses
        contactRoles: []
        contactGroups: []
        locale: 'en-us'
      }
      urgentAt500Myr: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        thresholdType: 'Actual'
        contactEmails: alertEmailAddresses
        contactRoles: []
        contactGroups: []
        locale: 'en-us'
      }
      forecastAt500Myr: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        thresholdType: 'Forecasted'
        contactEmails: alertEmailAddresses
        contactRoles: []
        contactGroups: []
        locale: 'en-us'
      }
    }
  }
}

output confirmedBillingCurrency string = confirmedBillingCurrency
