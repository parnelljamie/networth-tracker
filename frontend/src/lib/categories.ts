import {
  Banknote,
  CreditCard,
  Home,
  Landmark,
  Package,
  PiggyBank,
  TrendingDown,
  TrendingUp,
  Wallet,
  type LucideIcon,
} from "lucide-react"

export type Category =
  | "investment"
  | "pension"
  | "cash"
  | "property"
  | "mortgage"
  | "loan"
  | "credit_card"
  | "other_asset"
  | "other_liability"

export const CATEGORY_LABELS: Record<Category, string> = {
  investment: "Investments",
  pension: "Pensions",
  cash: "Cash",
  property: "Property",
  mortgage: "Mortgage",
  loan: "Loans",
  credit_card: "Credit cards",
  other_asset: "Other assets",
  other_liability: "Other liabilities",
}

// Chart rules (docs/05-ui.md): categorical colours assigned by entity, in this fixed order.
export const CATEGORY_COLORS: Record<Category, { light: string; dark: string }> = {
  investment: { light: "#2a78d6", dark: "#3987e5" },
  pension: { light: "#eb6834", dark: "#d95926" },
  cash: { light: "#1baf7a", dark: "#199e70" },
  property: { light: "#eda100", dark: "#c98500" },
  mortgage: { light: "#e87ba4", dark: "#d55181" },
  loan: { light: "#e87ba4", dark: "#d55181" },
  credit_card: { light: "#e87ba4", dark: "#d55181" },
  other_asset: { light: "#008300", dark: "#008300" },
  other_liability: { light: "#e87ba4", dark: "#d55181" },
}

export const CATEGORY_ICONS: Record<Category, LucideIcon> = {
  investment: TrendingUp,
  pension: PiggyBank,
  cash: Wallet,
  property: Home,
  mortgage: Landmark,
  loan: Banknote,
  credit_card: CreditCard,
  other_asset: Package,
  other_liability: TrendingDown,
}

// Grouping/display order used anywhere accounts are listed by category (Overview's Accounts
// card, the Person page's account list): assets first in chart-colour-slot order, then debts.
export const CATEGORY_GROUP_ORDER: Category[] = [
  "investment",
  "pension",
  "cash",
  "property",
  "other_asset",
  "mortgage",
  "loan",
  "credit_card",
  "other_liability",
]

export const LIABILITY_CATEGORIES: Category[] = ["mortgage", "loan", "credit_card", "other_liability"]
export const ASSET_CATEGORIES: Category[] = [
  "investment",
  "pension",
  "cash",
  "property",
  "other_asset",
]

export const WRAPPER_LABELS: Record<string, string> = {
  none: "No wrapper",
  isa: "ISA",
  lisa: "LISA",
  jisa: "JISA",
  gia: "GIA",
  sipp: "SIPP",
  workplace_pension: "Workplace pension",
  db_pension: "Defined benefit pension",
}

export const VALUATION_METHOD_LABELS: Record<string, string> = {
  holdings: "Holdings",
  balance: "Manual entry",
  model: "Modelled growth",
  amortising: "Auto-calculating",
  defined_benefit: "Scheme details",
}

// Category -> allowed wrappers and valuation methods, mirroring backend/app/services/account_service.py.
export const ALLOWED_WRAPPERS: Record<Category, string[]> = {
  investment: ["isa", "lisa", "jisa", "gia"],
  pension: ["sipp", "workplace_pension", "db_pension"],
  cash: ["none", "isa", "lisa", "jisa"],
  property: ["none"],
  mortgage: ["none"],
  loan: ["none"],
  credit_card: ["none"],
  other_asset: ["none"],
  other_liability: ["none"],
}

export const ALLOWED_METHODS: Record<Category, string[]> = {
  investment: ["holdings", "balance"],
  pension: ["holdings", "balance"],
  cash: ["balance"],
  property: ["model"],
  mortgage: ["amortising", "balance"],
  loan: ["amortising", "balance"],
  credit_card: ["balance"],
  other_asset: ["model", "balance"],
  other_liability: ["model", "balance", "amortising"],
}

export function methodsForWrapper(category: Category, wrapper: string): string[] {
  if (wrapper === "db_pension") return ["defined_benefit", "balance"]
  return ALLOWED_METHODS[category]
}
