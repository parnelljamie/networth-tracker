import type { components } from "@/api/schema"
import { todayIso } from "@/lib/dates"

export type DbPensionDetails = components["schemas"]["DbPensionDetailsIn"]

/** Draft form state: amounts may be blank while the user is typing. */
export interface DbPensionDraft {
  scheme: string
  accruedAnnualPension: number | undefined
  accruedLumpSum: number | undefined
  accruedAsOf: string | undefined
  accrualDenominator: number | undefined // 57 means 1/57 of salary a year
  revaluationAboveCpi: number | undefined
  pensionableSalary: number | undefined
  salaryGrowthRate: number | undefined
  normalPensionAge: number | undefined
  isActiveMember: boolean
  capitalisationFactor: number | undefined
}

/** Teachers' Pension Scheme, 2015 career-average section. The pension age is the member's State
 *  Pension age: 68 for anyone born after 5 April 1978 under current law. */
export const TPS_PRESET = {
  scheme: "tps_2015",
  accrualDenominator: 57,
  revaluationAboveCpi: 0.016,
  normalPensionAge: 68,
  capitalisationFactor: 20,
} as const

export function emptyDbPensionDraft(): DbPensionDraft {
  return {
    ...TPS_PRESET,
    accruedAnnualPension: undefined,
    accruedLumpSum: 0,
    accruedAsOf: todayIso(),
    pensionableSalary: undefined,
    salaryGrowthRate: 0.025,
    isActiveMember: true,
  }
}

export function draftFromDetails(d: DbPensionDetails): DbPensionDraft {
  return {
    scheme: d.scheme ?? "custom",
    accruedAnnualPension: d.accrued_annual_pension_gbp,
    accruedLumpSum: d.accrued_lump_sum_gbp ?? 0,
    accruedAsOf: d.accrued_as_of,
    accrualDenominator: d.accrual_rate > 0 ? Math.round(1 / d.accrual_rate) : undefined,
    revaluationAboveCpi: d.revaluation_above_cpi ?? 0,
    pensionableSalary: d.pensionable_salary_gbp ?? 0,
    salaryGrowthRate: d.salary_growth_rate ?? 0,
    normalPensionAge: d.normal_pension_age,
    isActiveMember: d.is_active_member ?? true,
    capitalisationFactor: d.capitalisation_factor ?? 20,
  }
}

/** The payload for the API, or null while a required field is blank. */
export function detailsFromDraft(d: DbPensionDraft): DbPensionDetails | null {
  if (
    d.accruedAnnualPension === undefined ||
    !d.accruedAsOf ||
    !d.accrualDenominator ||
    d.normalPensionAge === undefined ||
    !d.capitalisationFactor
  ) {
    return null
  }
  return {
    scheme: d.scheme,
    accrued_annual_pension_gbp: d.accruedAnnualPension,
    accrued_lump_sum_gbp: d.accruedLumpSum ?? 0,
    accrued_as_of: d.accruedAsOf,
    accrual_rate: 1 / d.accrualDenominator,
    revaluation_above_cpi: d.revaluationAboveCpi ?? 0,
    pensionable_salary_gbp: d.pensionableSalary ?? 0,
    salary_growth_rate: d.salaryGrowthRate ?? 0,
    normal_pension_age: d.normalPensionAge,
    is_active_member: d.isActiveMember,
    capitalisation_factor: d.capitalisationFactor,
  }
}

export function numberOrUndefined(raw: string): number | undefined {
  return raw === "" ? undefined : Number(raw)
}
