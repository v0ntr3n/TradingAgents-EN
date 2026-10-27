import { ElMessageBox } from 'element-plus'
import type { Router } from 'vue-router'

import { useLicenseStore, type ProFeature } from '@/stores/license'

interface FeatureAccessOptions {
  title?: string
  message?: string
  redirectTo?: string
  confirmButtonText?: string
  cancelButtonText?: string
}

export async function ensureFeatureAccess(
  feature: ProFeature,
  router: Router,
  options: FeatureAccessOptions = {}
) {
  const licenseStore = useLicenseStore()

  if (!licenseStore.licenseInfo) {
    await licenseStore.verifyLicense()
  }

  if (licenseStore.hasFeature(feature)) {
    return true
  }

  try {
    await ElMessageBox.confirm(
      options.message || 'This function is exclusive for advanced students, please go to authorization management to complete the certification.',
      options.title || 'Limited functionality',
      {
        confirmButtonText: options.confirmButtonText || 'Go to authorization management',
        cancelButtonText: options.cancelButtonText || 'Talk to you later',
        type: 'warning'
      }
    )
    await router.push(options.redirectTo || '/settings/license')
  } catch {
    // No additional processing will be done when the user cancels
  }

  return false
}

export function ensureReportExportAccess(router: Router) {
  return ensureFeatureAccess('export_reports', router, {
    message: 'Report downloading and exporting are exclusive to advanced students. Please go to Authorization Management to complete the certification.'
  })
}